#!/usr/bin/env python3
"""Publica posts del blog a partir de documentos de Google Docs.

Uso:
  python3 tools/publicar.py <enlace-de-google-doc | archivo.zip>   publica o actualiza un post
  python3 tools/publicar.py <enlace> --fecha 2026-11-18              fija la fecha del post
  python3 tools/publicar.py <enlace> --pr                            además crea rama, commit y push para el PR
  python3 tools/publicar.py --reconstruir                            regenera todas las páginas
  python3 tools/publicar.py --borrar <slug>                          elimina un post
  python3 tools/publicar.py --lista                                  muestra los posts publicados

El documento debe estar compartido como "Cualquier persona con el enlace puede ver",
o bien descargarse desde Google Docs con Archivo > Descargar > Página web (.html, comprimido)
y pasar la ruta del .zip.

Solo usa la biblioteca estándar de Python 3 (no hay que instalar nada).
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime
from html.parser import HTMLParser
from io import BytesIO

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG = os.path.join(RAIZ, "blog")
POSTS_JSON = os.path.join(BLOG, "posts.json")
IMG_DIR = os.path.join(BLOG, "img")

CALENDLY = "https://calendly.com/katherinegomez/50min"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
VACIOS = {"img", "br", "hr", "meta", "link", "input", "col", "area", "base", "wbr"}
INICIO, FIN = "<!-- contenido:inicio -->", "<!-- contenido:fin -->"


class ErrorPublicacion(Exception):
    pass


# --------------------------------------------------------------------------- #
#  Lectura del HTML exportado por Google Docs
# --------------------------------------------------------------------------- #

class Nodo:
    def __init__(self, tag, attrs=None, padre=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.hijos = []
        self.padre = padre

    def clases(self):
        return (self.attrs.get("class") or "").split()


class Arbol(HTMLParser):
    """Construye un árbol simple a partir del HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("#raiz")
        self.actual = self.raiz
        self.css = ""
        self._en_style = False

    def handle_starttag(self, tag, attrs):
        nodo = Nodo(tag, attrs, self.actual)
        self.actual.hijos.append(nodo)
        if tag == "style":
            self._en_style = True
        if tag not in VACIOS:
            self.actual = nodo

    def handle_startendtag(self, tag, attrs):
        self.actual.hijos.append(Nodo(tag, attrs, self.actual))

    def handle_endtag(self, tag):
        if tag == "style":
            self._en_style = False
        nodo = self.actual
        while nodo is not self.raiz and nodo.tag != tag:
            nodo = nodo.padre
        if nodo is not self.raiz:
            self.actual = nodo.padre

    def handle_data(self, data):
        if self._en_style:
            self.css += data
        else:
            self.actual.hijos.append(data)


def buscar(nodo, tag):
    for h in nodo.hijos:
        if isinstance(h, Nodo):
            if h.tag == tag:
                return h
            r = buscar(h, tag)
            if r:
                return r
    return None


def texto_plano(nodo):
    if isinstance(nodo, str):
        return nodo
    if nodo.tag in ("style", "script"):
        return ""
    return "".join(texto_plano(h) for h in nodo.hijos)


def limpiar_espacios(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def esc(s):
    return html.escape(s, quote=True)


def limpiar_enlace(href):
    """Google envuelve los enlaces en https://www.google.com/url?q=..."""
    p = urllib.parse.urlparse(href)
    if p.netloc.endswith("google.com") and p.path == "/url":
        q = urllib.parse.parse_qs(p.query).get("q")
        if q:
            return q[0]
    return href


class Conversor:
    """Convierte el <body> de Google Docs en HTML limpio para el blog."""

    def __init__(self, css, slug, zip_archivo):
        self.estilos = {m.group(1): m.group(2) for m in re.finditer(r"\.([\w-]+)\{([^}]*)\}", css)}
        self.slug = slug
        self.zip = zip_archivo
        self.imagenes = []  # (nombre_en_zip, nombre_destino)
        self.portada = None

    # -- estilos -------------------------------------------------------------
    def props(self, nodo):
        return ";".join(self.estilos.get(c, "") for c in nodo.clases()) + ";" + nodo.attrs.get("style", "")

    def es_negrita(self, nodo):
        return re.search(r"font-weight:\s*(bold|[6-9]00)", self.props(nodo)) is not None

    def es_cursiva(self, nodo):
        return re.search(r"font-style:\s*italic", self.props(nodo)) is not None

    # -- conversión ----------------------------------------------------------
    def hijos(self, nodo, en_titulo=False):
        return "".join(self.render(h, en_titulo) for h in nodo.hijos)

    def contiene_comentario(self, nodo):
        for h in nodo.hijos:
            if isinstance(h, Nodo):
                if h.tag == "a" and h.attrs.get("id", "").startswith("cmnt"):
                    return True
                if self.contiene_comentario(h):
                    return True
        return False

    def render(self, nodo, en_titulo=False):
        if isinstance(nodo, str):
            return html.escape(nodo.replace("\xa0", " "), quote=False)
        t = nodo.tag
        if t in ("script", "style", "head", "title", "meta", "link"):
            return ""

        if t == "a":
            href = nodo.attrs.get("href", "")
            ident = nodo.attrs.get("id", "")
            if href.startswith("#cmnt") or ident.startswith("cmnt"):
                return ""  # comentarios del documento
            interior = self.hijos(nodo, en_titulo)
            if href.startswith("#ftnt"):  # notas al pie
                return '<a href="%s" id="%s">%s</a>' % (esc(href), esc(ident), interior)
            if not href or href.startswith("#"):
                return interior
            href = limpiar_enlace(href)
            if href.startswith("http"):
                return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (esc(href), interior)
            return '<a href="%s">%s</a>' % (esc(href), interior)

        if t == "div" and self.contiene_comentario(nodo):
            return ""

        if t == "span":
            interior = self.hijos(nodo, en_titulo)
            if en_titulo or not interior.strip() or "<img" in interior:
                return interior
            if self.es_cursiva(nodo):
                interior = "<em>%s</em>" % interior
            if self.es_negrita(nodo):
                interior = "<strong>%s</strong>" % interior
            return interior

        if t == "img":
            return self.imagen(nodo)
        if t == "br":
            return "<br>"
        if t == "hr":
            return "<hr>"

        if t in ("ul", "ol"):
            interior = self.hijos(nodo)
            if not interior.strip():
                return ""
            inicio = nodo.attrs.get("start")
            extra = ' start="%s"' % esc(inicio) if t == "ol" and inicio and inicio != "1" else ""
            return "<%s%s>%s</%s>\n" % (t, extra, interior, t)
        if t == "li":
            return "<li>%s</li>" % self.hijos(nodo)

        if re.fullmatch(r"h[1-6]", t):
            texto = limpiar_espacios(texto_plano(nodo))
            if not texto:
                return ""
            nivel = {"h1": "h2", "h2": "h3"}.get(t, "h4")
            return "<%s>%s</%s>\n" % (nivel, html.escape(texto, quote=False), nivel)

        if t == "p":
            interior = self.hijos(nodo).strip()
            texto = limpiar_espacios(texto_plano(nodo))
            if not texto and "<img" not in interior:
                return ""
            if not texto:
                return "<figure>%s</figure>\n" % interior
            interior = re.sub(r"(\s*<br>)+$", "", interior)
            # Una línea corta, toda en negrita, se usa como subtítulo (muchos escriben así en vez de usar "Encabezado")
            m = re.fullmatch(r"(?:<strong>(?:(?!</?strong>)[^<])*</strong>\s*)+", interior)
            if m and len(texto) <= 90 and not texto.endswith((":", ".", ",")):
                return "<h2>%s</h2>\n" % html.escape(texto, quote=False)
            return "<p>%s</p>\n" % interior

        if t == "table":
            return '<div class="kg-tabla"><table>%s</table></div>\n' % self.hijos(nodo)
        if t in ("tbody", "thead", "tr", "td", "th", "sup", "sub"):
            return "<%s>%s</%s>" % (t, self.hijos(nodo), t)

        return self.hijos(nodo, en_titulo)

    def imagen(self, nodo):
        src = nodo.attrs.get("src", "")
        if self.zip is None or src not in self.zip.namelist():
            return ""
        nombre = os.path.basename(src)
        self.imagenes.append((src, nombre))
        ruta = "img/%s/%s" % (self.slug, nombre)
        if self.portada is None:
            self.portada = ruta
        alt = limpiar_espacios(nodo.attrs.get("alt", "") or nodo.attrs.get("title", ""))
        return '<img src="%s" alt="%s" loading="lazy">' % (esc(ruta), esc(alt))


def extraer_titulo(body):
    """Devuelve (titulo, subtitulo, nodos_a_omitir).

    Usa el estilo "Título" de Google Docs; si no existe, el primer Encabezado 1;
    si tampoco, el primer párrafo con texto.
    """
    bloques = [h for h in body.hijos if isinstance(h, Nodo)]
    titulo = subtitulo = None
    omitir = set()
    for b in bloques:
        if titulo is None and "title" in b.clases():
            titulo = b
        elif subtitulo is None and "subtitle" in b.clases():
            subtitulo = b
    if titulo is None:
        titulo = next((b for b in bloques if b.tag == "h1" and limpiar_espacios(texto_plano(b))), None)
    if titulo is None:
        titulo = next((b for b in bloques if b.tag == "p" and limpiar_espacios(texto_plano(b))), None)
    if titulo is None:
        raise ErrorPublicacion("El documento está vacío: no encontré un título.")
    omitir.add(id(titulo))
    if subtitulo is not None:
        omitir.add(id(subtitulo))
    sub = limpiar_espacios(texto_plano(subtitulo)) if subtitulo is not None else ""
    return limpiar_espacios(texto_plano(titulo)), sub, omitir


# --------------------------------------------------------------------------- #
#  Descarga
# --------------------------------------------------------------------------- #

def obtener_zip(fuente):
    """Devuelve (bytes_del_zip, doc_id o None)."""
    if os.path.isfile(fuente):
        with open(fuente, "rb") as f:
            datos = f.read()
        if not datos.startswith(b"PK"):
            raise ErrorPublicacion("El archivo no es un .zip. En Google Docs usa Archivo > Descargar > Página web (.html, comprimido).")
        return datos, None

    m = re.search(r"/document/(?:u/\d+/)?d/([\w-]+)", fuente) or re.fullmatch(r"([\w-]{25,})", fuente.strip())
    if not m:
        raise ErrorPublicacion("No reconozco esto como un enlace de Google Docs ni como un archivo .zip:\n  %s" % fuente)
    doc_id = m.group(1)
    url = "https://docs.google.com/document/d/%s/export?format=zip" % doc_id
    peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (publicar-blog)"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            datos = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            datos = b""
        else:
            raise ErrorPublicacion("Google respondió con un error %s al descargar el documento." % e.code)
    except urllib.error.URLError as e:
        raise ErrorPublicacion("No pude conectarme a Google Docs (%s). ¿Hay conexión a internet?" % e.reason)
    if not datos.startswith(b"PK"):
        raise ErrorPublicacion(
            "No pude descargar el documento. Revisa que esté compartido como\n"
            "  \"Cualquier persona con el enlace\" → \"Lector\"\n"
            "o descárgalo con Archivo > Descargar > Página web (.html, comprimido) y usa la ruta del .zip.")
    return datos, doc_id


# --------------------------------------------------------------------------- #
#  Registro de posts
# --------------------------------------------------------------------------- #

def cargar_posts():
    if not os.path.exists(POSTS_JSON):
        return []
    with open(POSTS_JSON, encoding="utf-8") as f:
        return json.load(f)


def guardar_posts(posts):
    os.makedirs(BLOG, exist_ok=True)
    with open(POSTS_JSON, "w", encoding="utf-8") as f:
        json.dump(ordenar(posts), f, ensure_ascii=False, indent=2)
        f.write("\n")


def ordenar(posts):
    """Del más reciente al más antiguo."""
    return sorted(posts, key=lambda p: (p["fecha"], p.get("creado", "")), reverse=True)


def crear_slug(titulo):
    s = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:70].rstrip("-") or "post")


def slug_libre(base, posts):
    usados = {p["slug"] for p in posts} | {"index"}
    slug, n = base, 2
    while slug in usados:
        slug, n = "%s-%d" % (base, n), n + 1
    return slug


def fecha_es(iso):
    d = date.fromisoformat(iso)
    return "%d de %s de %d" % (d.day, MESES[d.month - 1], d.year)


def minutos(palabras):
    return max(1, round(palabras / 200))


# --------------------------------------------------------------------------- #
#  Plantillas
# --------------------------------------------------------------------------- #

def cabecera(titulo, descripcion):
    return """<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{titulo}</title>
    <meta name="description" content="{desc}">
    <meta property="og:title" content="{titulo}">
    <meta property="og:description" content="{desc}">
    <meta property="og:type" content="article">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css">
    <link rel="stylesheet" href="blog.css">
</head>
<body>
    <header class="kg-header">
        <a href="../index.html" class="kg-marca" aria-label="Inicio">
            <img src="../img/Logo-imagen-grande-PhotoRoom.png" alt="Katherine Gómez">
        </a>
        <nav class="kg-menu">
            <a href="../index.html">Inicio</a>
            <a href="index.html">Blog</a>
            <a href="{calendly}" target="_blank" rel="noopener noreferrer" class="kg-boton">Agenda una cita</a>
        </nav>
    </header>
""".format(titulo=esc(titulo), desc=esc(descripcion), calendly=CALENDLY)


PIE = """
    <footer class="kg-pie">
        <div class="kg-redes">
            <a href="https://www.facebook.com/profile.php?id=100066684762388" target="_blank" rel="noopener noreferrer" aria-label="Facebook"><i class="bi bi-facebook"></i></a>
            <a href="https://www.instagram.com/katherinegomezdaza/" target="_blank" rel="noopener noreferrer" aria-label="Instagram"><i class="bi bi-instagram"></i></a>
            <a href="https://www.linkedin.com/in/katherine-g%C3%B3mez-daza-527262221" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"><i class="bi bi-linkedin"></i></a>
            <a href="https://api.whatsapp.com/send?phone=+573122812428" target="_blank" rel="noopener noreferrer" aria-label="WhatsApp"><i class="bi bi-whatsapp"></i></a>
        </div>
        <p>(+57) 312 281 2428 · katherinegomezd8@gmail.com</p>
        <p>Av. Santander # 62-39, Edificio Capitalia, Consultorio 301b · Manizales, Colombia</p>
    </footer>
</body>
</html>
"""


def pagina_post(post, contenido, anterior, siguiente):
    meta = '<time datetime="%s">%s</time> · %d min de lectura' % (
        post["fecha"], fecha_es(post["fecha"]), minutos(post.get("palabras", 0)))
    entradilla = '\n        <p class="kg-entradilla">%s</p>' % esc(post["subtitulo"]) if post.get("subtitulo") else ""

    def enlace(p, clase, etiqueta):
        if not p:
            return '<span class="%s kg-vacio"></span>' % clase
        return '<a href="%s.html" class="%s"><span class="kg-etiqueta">%s</span><span class="kg-titulo-nav">%s</span></a>' % (
            esc(p["slug"]), clase, etiqueta, esc(p["titulo"]))

    return cabecera("%s · Katherine Gómez" % post["titulo"], post.get("resumen", "")) + """
    <main class="kg-articulo">
        <a class="kg-volver" href="index.html"><i class="bi bi-arrow-left"></i> Todas las publicaciones</a>
        <h1>{titulo}</h1>
        <p class="kg-meta">{meta}</p>{entradilla}
        <article class="kg-contenido">
{inicio}
{contenido}
{fin}
        </article>

        <aside class="kg-cta">
            <p>¿Te identificas con lo que acabas de leer? Conversemos.</p>
            <a href="{calendly}" target="_blank" rel="noopener noreferrer" class="kg-boton">Quiero verte en consulta</a>
        </aside>

        <nav class="kg-navposts" aria-label="Más publicaciones">
            {ant}
            {sig}
        </nav>
    </main>
""".format(titulo=esc(post["titulo"]), meta=meta, entradilla=entradilla, inicio=INICIO, fin=FIN,
           contenido=contenido.strip(), calendly=CALENDLY,
           ant=enlace(anterior, "kg-anterior", '<i class="bi bi-arrow-left"></i> Anterior'),
           sig=enlace(siguiente, "kg-siguiente", 'Siguiente <i class="bi bi-arrow-right"></i>')) + PIE


def pagina_indice(posts):
    tarjetas = []
    for p in posts:
        if p.get("portada"):
            imagen = '<img src="%s" alt="" loading="lazy">' % esc(p["portada"])
        else:
            imagen = '<img src="../img/Logo-imagen-grande-PhotoRoom.png" alt="" class="kg-sin-portada" loading="lazy">'
        tarjetas.append("""            <a class="kg-tarjeta" href="{slug}.html">
                <div class="kg-tarjeta-img">{imagen}</div>
                <div class="kg-tarjeta-cuerpo">
                    <p class="kg-meta"><time datetime="{fecha}">{fecha_es}</time> · {min} min</p>
                    <h2>{titulo}</h2>
                    <p>{resumen}</p>
                    <span class="kg-leer">Leer <i class="bi bi-arrow-right"></i></span>
                </div>
            </a>""".format(slug=esc(p["slug"]), imagen=imagen, fecha=p["fecha"], fecha_es=fecha_es(p["fecha"]),
                           min=minutos(p.get("palabras", 0)), titulo=esc(p["titulo"]), resumen=esc(p.get("resumen", ""))))
    if tarjetas:
        cuerpo = '        <div class="kg-tarjetas">\n%s\n        </div>' % "\n".join(tarjetas)
    else:
        cuerpo = '        <p class="kg-sin-posts">Muy pronto compartiré aquí mis primeras publicaciones.</p>'
    descripcion = "Reflexiones de Katherine Gómez sobre el duelo, la pérdida y el camino para sanar."
    return cabecera("Blog · Katherine Gómez", descripcion) + """
    <main class="kg-blog">
        <section class="kg-intro">
            <h1>Blog</h1>
            <p>Reflexiones sobre el duelo, la pérdida y el camino para sanar.</p>
        </section>
{cuerpo}
    </main>
""".format(cuerpo=cuerpo) + PIE


# --------------------------------------------------------------------------- #
#  Generación
# --------------------------------------------------------------------------- #

def leer_contenido(slug):
    ruta = os.path.join(BLOG, slug + ".html")
    if not os.path.exists(ruta):
        raise ErrorPublicacion("Falta la página %s; vuelve a publicar ese documento." % ruta)
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    try:
        return texto.split(INICIO, 1)[1].split(FIN, 1)[0]
    except IndexError:
        raise ErrorPublicacion("No encuentro el contenido dentro de %s." % ruta)


def generar(posts, nuevos=None):
    """Escribe todas las páginas de posts (para actualizar anterior/siguiente) y el índice."""
    nuevos = nuevos or {}
    posts = ordenar(posts)
    contenidos = {p["slug"]: nuevos.get(p["slug"]) or leer_contenido(p["slug"]) for p in posts}
    for i, p in enumerate(posts):
        mas_nuevo = posts[i - 1] if i > 0 else None
        mas_antiguo = posts[i + 1] if i + 1 < len(posts) else None
        with open(os.path.join(BLOG, p["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(pagina_post(p, contenidos[p["slug"]], mas_antiguo, mas_nuevo))
    with open(os.path.join(BLOG, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina_indice(posts))


def publicar(fuente, fecha=None):
    datos, doc_id = obtener_zip(fuente)
    archivo = zipfile.ZipFile(BytesIO(datos))
    html_nombre = next((n for n in archivo.namelist() if n.lower().endswith(".html")), None)
    if not html_nombre:
        raise ErrorPublicacion("El .zip no contiene el HTML del documento.")
    arbol = Arbol()
    arbol.feed(archivo.read(html_nombre).decode("utf-8", "replace"))
    body = buscar(arbol.raiz, "body") or arbol.raiz

    titulo, subtitulo, omitir = extraer_titulo(body)
    posts = cargar_posts()
    existente = None
    if doc_id:
        existente = next((p for p in posts if p.get("doc_id") == doc_id), None)
    if existente is None:
        existente = next((p for p in posts if p["slug"] == crear_slug(titulo) and not (doc_id and p.get("doc_id"))), None)
    slug = existente["slug"] if existente else slug_libre(crear_slug(titulo), posts)

    conv = Conversor(arbol.css, slug, archivo)
    contenido = "".join(conv.render(b) for b in body.hijos if not (isinstance(b, Nodo) and id(b) in omitir))
    texto = limpiar_espacios(re.sub(r"<[^>]+>", " ", contenido))
    if not texto:
        raise ErrorPublicacion("El documento solo tiene título; no hay texto para publicar.")

    if subtitulo:
        resumen = subtitulo
    else:
        primer_p = re.search(r"<p>(.*?)</p>", contenido, re.S)
        resumen = limpiar_espacios(html.unescape(re.sub(r"<[^>]+>", "", primer_p.group(1)))) if primer_p else texto
    if len(resumen) > 180:
        resumen = resumen[:177].rsplit(" ", 1)[0] + "…"

    # Imágenes: se reemplazan por completo en cada publicación
    carpeta = os.path.join(IMG_DIR, slug)
    shutil.rmtree(carpeta, ignore_errors=True)
    if conv.imagenes:
        os.makedirs(carpeta)
        for origen, destino in conv.imagenes:
            ruta = os.path.join(carpeta, destino)
            with open(ruta, "wb") as f:
                f.write(archivo.read(origen))
            reducir_imagen(ruta)

    post = existente or {"slug": slug, "creado": datetime.now().isoformat(timespec="seconds")}
    post.update({
        "titulo": titulo,
        "subtitulo": subtitulo,
        "resumen": resumen,
        "fecha": fecha or (existente or {}).get("fecha") or date.today().isoformat(),
        "portada": conv.portada,
        "palabras": len(texto.split()),
        "doc_id": doc_id or (existente or {}).get("doc_id"),
    })
    if existente is None:
        posts.append(post)
    generar(posts, {slug: contenido})
    guardar_posts(posts)
    return post, existente is not None


def reducir_imagen(ruta, maximo=1600):
    """En macOS reduce las fotos grandes con `sips` (incluido en el sistema). En otros sistemas no hace nada."""
    if not shutil.which("sips") or not ruta.lower().endswith((".jpg", ".jpeg", ".png")):
        return
    info = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", ruta], capture_output=True, text=True).stdout
    medidas = [int(n) for n in re.findall(r"pixel(?:Width|Height):\s*(\d+)", info)]
    if medidas and max(medidas) > maximo:
        subprocess.run(["sips", "--resampleHeightWidthMax", str(maximo), ruta], capture_output=True)


def borrar(slug):
    posts = cargar_posts()
    if not any(p["slug"] == slug for p in posts):
        raise ErrorPublicacion("No existe un post con el slug '%s'. Usa --lista para verlos." % slug)
    posts = [p for p in posts if p["slug"] != slug]
    ruta = os.path.join(BLOG, slug + ".html")
    if os.path.exists(ruta):
        os.remove(ruta)
    shutil.rmtree(os.path.join(IMG_DIR, slug), ignore_errors=True)
    generar(posts)
    guardar_posts(posts)


# --------------------------------------------------------------------------- #
#  Git / Pull request
# --------------------------------------------------------------------------- #

def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=RAIZ, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorPublicacion("git %s falló:\n%s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return r.stdout.strip()


def preparar_pr(post, actualizado):
    rama = git("rev-parse", "--abbrev-ref", "HEAD")
    if rama in ("main", "master"):
        rama = "blog/%s" % post["slug"]
        git("checkout", "-b", rama)
    git("add", "blog")
    if not git("status", "--porcelain", "--", "blog"):
        print("No hay cambios que subir.")
        return
    verbo = "Actualiza" if actualizado else "Publica"
    git("commit", "-m", "Blog: %s «%s»" % (verbo.lower(), post["titulo"]))
    git("push", "-u", "origin", rama)
    remoto = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remoto)
    if m:
        print("\nAbre el pull request aquí:\n  https://github.com/%s/compare/main...%s?expand=1"
              % (m.group(1), urllib.parse.quote(rama)))


# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description="Publica posts del blog desde Google Docs.")
    ap.add_argument("fuente", nargs="?", help="enlace de Google Docs o archivo .zip exportado")
    ap.add_argument("--fecha", help="fecha del post (AAAA-MM-DD); por defecto hoy, o la que ya tenía")
    ap.add_argument("--pr", action="store_true", help="crear rama, commit y push para abrir un pull request")
    ap.add_argument("--reconstruir", action="store_true", help="regenerar todas las páginas")
    ap.add_argument("--borrar", metavar="SLUG", help="eliminar un post")
    ap.add_argument("--lista", action="store_true", help="mostrar los posts publicados")
    a = ap.parse_args()

    try:
        if a.fecha:
            try:
                date.fromisoformat(a.fecha)
            except ValueError:
                raise ErrorPublicacion("La fecha debe tener el formato AAAA-MM-DD, por ejemplo 2026-11-18.")
        if a.lista:
            for p in ordenar(cargar_posts()):
                print("%s  %-45s  %s" % (p["fecha"], p["slug"], p["titulo"]))
        elif a.borrar:
            borrar(a.borrar)
            print("Post '%s' eliminado." % a.borrar)
        elif a.reconstruir:
            generar(cargar_posts())
            print("Blog regenerado.")
        elif a.fuente:
            post, actualizado = publicar(a.fuente, a.fecha)
            print("%s: «%s»" % ("Actualizado" if actualizado else "Publicado", post["titulo"]))
            print("  Página: blog/%s.html" % post["slug"])
            print("  Vista previa: abre %s en el navegador" % os.path.join(BLOG, post["slug"] + ".html"))
            if a.pr:
                preparar_pr(post, actualizado)
        else:
            ap.print_help()
    except ErrorPublicacion as e:
        print("Error: %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
