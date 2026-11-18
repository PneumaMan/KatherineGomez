#!/usr/bin/env python3
"""Genera un reporte de ideas para el blog a partir de lo que la gente busca en Colombia.

Uso:
  python3 tools/ideas.py            reporte completo (≈ 5–8 minutos)
  python3 tools/ideas.py --rapido   versión corta (≈ 2–3 minutos), sin la expansión a–z
  python3 tools/ideas.py --reescribir  rehace el reporte con los datos de la última consulta (sin buscar
                                       de nuevo), útil después de editar "excluir" o "local" en temas.json

Resultado:
  ideas/REPORTE.md                  el reporte para leer (se ve bien en GitHub)
  ideas/historial/AAAA-MM-DD.json   datos crudos, para comparar con el próximo reporte

Fuentes (públicas, sin claves ni cuentas):
  - Autocompletado de Google (Colombia, español)
  - Autocompletado de YouTube (Colombia, español)
  - Autocompletado de DuckDuckGo (Colombia, español)
  - Tendencias del día de Google Trends en Colombia
  - Visitas mensuales a artículos de Wikipedia en español

Los temas se configuran en ideas/temas.json. Solo usa la biblioteca estándar de Python 3.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "ideas")
TEMAS = os.path.join(CARPETA, "temas.json")
HISTORIAL = os.path.join(CARPETA, "historial")
REPORTE = os.path.join(CARPETA, "REPORTE.md")
POSTS = os.path.join(RAIZ, "blog", "posts.json")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
PAUSA = 0.5  # segundos entre consultas, para no saturar los servicios
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]
PALABRAS_PREGUNTA = ("como ", "que ", "por que ", "porque ", "cuanto ", "cuando ", "donde ", "cual ", "cuales ",
                     "quien ", "es normal ", "se puede ", "puedo ", "para que ", "es malo ")
VACIAS = set("de la el los las un una unos unas y o en por para con sin mi mis tu tus su sus al del a que "
             "se es lo como cuando".split())

FUENTES = {
    "google": "Google",
    "youtube": "YouTube",
    "duckduckgo": "DuckDuckGo",
}
# Google es la referencia principal en Colombia; DuckDuckGo es el menos local
PESOS = {"google": 1.0, "youtube": 0.8, "duckduckgo": 0.5}


def normalizar(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", s)).strip()


class Consultor:
    def __init__(self):
        self.fallos = {k: 0 for k in FUENTES}
        self.desactivadas = {}
        self.consultas = 0

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})
        with urllib.request.urlopen(req, timeout=20) as r:
            datos = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
        try:
            return datos.decode(charset)
        except (LookupError, UnicodeDecodeError):
            return datos.decode("latin-1")

    def sugerencias(self, fuente, consulta):
        if fuente in self.desactivadas:
            return []
        q = urllib.parse.quote(consulta)
        if fuente == "google":
            url = "https://suggestqueries.google.com/complete/search?client=firefox&hl=es&gl=co&q=" + q
        elif fuente == "youtube":
            url = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=es&gl=co&q=" + q
        else:
            url = "https://duckduckgo.com/ac/?kl=co-es&q=" + q
        time.sleep(PAUSA)
        self.consultas += 1
        try:
            datos = json.loads(self._get(url))
            self.fallos[fuente] = 0
        except urllib.error.HTTPError as e:
            return self._fallo(fuente, "respondió con error %s" % e.code, bloqueo=e.code in (403, 429))
        except Exception as e:  # red caída, respuesta inválida, etc.
            return self._fallo(fuente, str(e))
        if fuente == "duckduckgo":
            return [d.get("phrase", "") for d in datos if isinstance(d, dict)]
        return datos[1] if isinstance(datos, list) and len(datos) > 1 else []

    def _fallo(self, fuente, motivo, bloqueo=False):
        self.fallos[fuente] += 1
        if bloqueo or self.fallos[fuente] >= 5:
            self.desactivadas[fuente] = motivo
            print("\n  ! %s dejó de responder (%s); se omite en este reporte." % (FUENTES[fuente], motivo))
        return []

    def json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "kathe-blog-ideas/1.0 (reporte de temas)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def texto(self, url):
        return self._get(url)


# --------------------------------------------------------------------------- #
#  Recolección
# --------------------------------------------------------------------------- #

def recolectar(cfg, consultor, rapido):
    resultados = {}
    excluir = [normalizar(x) for x in cfg.get("excluir", [])]
    relacionadas = [normalizar(x) for x in cfg.get("relacionadas", [])]
    semillas = cfg["semillas"]
    preguntas = cfg.get("preguntas", [])
    letras = [] if rapido else list("abcdefghijklmnopqrstuvwxyz")

    plan = []
    for semilla in semillas:
        consultas = [semilla] + ["%s %s" % (p, semilla) for p in preguntas]
        for c in consultas:
            for fuente in FUENTES:
                plan.append((semilla, fuente, c))
        for l in letras:
            plan.append((semilla, "google", "%s %s" % (semilla, l)))

    total = len(plan)
    for i, (semilla, fuente, consulta) in enumerate(plan, 1):
        print("\r  Consultando %d/%d · %-11s · %-45s" % (i, total, FUENTES[fuente], consulta[:45]), end="", flush=True)
        lista = consultor.sugerencias(fuente, consulta)
        cq = normalizar(consulta)
        for pos, texto in enumerate(lista):
            texto = re.sub(r"\s+", " ", texto).strip()
            clave = normalizar(texto)
            if not clave or clave == cq or clave == normalizar(semilla):
                continue
            if any(x and x in clave for x in excluir):
                continue
            if relacionadas and not any(x and x in clave for x in relacionadas):
                continue  # no tiene que ver con los temas del blog
            r = resultados.setdefault(clave, {"texto": texto, "fuentes": set(), "semillas": set(), "puntos": 0.0, "veces": 0})
            if any(ch in texto for ch in "áéíóúñ") and not any(ch in r["texto"] for ch in "áéíóúñ"):
                r["texto"] = texto  # preferir la versión con tildes
            r["fuentes"].add(fuente)
            r["semillas"].add(semilla)
            r["veces"] += 1
            r["puntos"] += max(0.1, 1 - pos / 10) * PESOS[fuente]
    print()
    for r in resultados.values():
        r["puntaje"] = round(r["puntos"] * (1 + 0.5 * (len(r["fuentes"]) - 1)), 2)
    return resultados


def wikipedia(cfg, consultor):
    hoy = date.today()
    fin = date(hoy.year, hoy.month, 1)
    inicio = date(fin.year - 2, fin.month, 1)
    salida = {}
    for nombre, articulo in cfg.get("wikipedia", {}).items():
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/es.wikipedia/all-access/user/%s/monthly/%s/%s"
               % (urllib.parse.quote(articulo), inicio.strftime("%Y%m%d"), fin.strftime("%Y%m%d")))
        try:
            items = consultor.json(url).get("items", [])
        except Exception:
            continue
        serie = [(i["timestamp"][:6], i["views"]) for i in items]
        if serie and serie[-1][0] == fin.strftime("%Y%m"):
            serie = serie[:-1]  # el mes en curso está incompleto
        if len(serie) >= 6:
            salida[nombre] = serie
        time.sleep(PAUSA)
    return salida


def tendencias(cfg, consultor):
    try:
        xml = consultor.texto("https://trends.google.com/trending/rss?geo=CO")
        raiz = ET.fromstring(xml)
    except Exception:
        return None
    ns = {"ht": "https://trends.google.com/trending/rss"}
    claves = [normalizar(x) for x in cfg.get("relacionadas", [])]
    encontradas = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        trafico = item.findtext("ht:approx_traffic", default="", namespaces=ns)
        noticias = " ".join((n.findtext("ht:news_item_title", default="", namespaces=ns) or "")
                            for n in item.findall("ht:news_item", ns))
        if any(c in normalizar(titulo) for c in claves):  # solo el título: evita noticias de crónica roja
            encontradas.append({"titulo": titulo, "trafico": trafico, "contexto": noticias[:160]})
    return encontradas


# --------------------------------------------------------------------------- #
#  Análisis
# --------------------------------------------------------------------------- #

def es_pregunta(clave):
    return clave.startswith(PALABRAS_PREGUNTA)


def es_local(clave, cfg):
    return any(re.search(r"\b%s\b" % re.escape(normalizar(l)), clave) for l in cfg.get("local", []))


def palabras(clave):
    return {w for w in clave.split() if w not in VACIAS and len(w) > 2}


def cubierto(clave, posts):
    p = palabras(clave)
    if not p:
        return None
    for post in posts:
        t = palabras(normalizar(post["titulo"]))
        if t and len(p & t) / len(p) >= 0.6:
            return post["titulo"]
    return None


def titulo_sugerido(texto):
    t = texto.strip().rstrip("?¿ ")
    reemplazos = [("como ", "cómo "), ("que ", "qué "), ("por que ", "por qué "), ("porque ", "por qué "),
                  ("cuanto ", "cuánto "), ("cuando ", "cuándo "), ("donde ", "dónde "), ("cual ", "cuál "),
                  ("quien ", "quién "), ("para que ", "para qué ")]
    bajo = t.lower()
    for a, b in reemplazos:
        if bajo.startswith(a):
            t = b + t[len(a):]
            break
    for a, b in TILDES.items():
        t = re.sub(r"\b%s\b" % a, b, t)
    return "¿%s?" % (t[0].upper() + t[1:])


TILDES = {"despues": "después", "separacion": "separación", "depresion": "depresión", "psicologo": "psicólogo",
          "psicologa": "psicóloga", "estrategica": "estratégica", "migracion": "migración", "emocion": "emoción",
          "perdida de": "pérdida de", "la perdida": "la pérdida", "una perdida": "una pérdida", "dificil": "difícil",
          "jovenes": "jóvenes", "dias": "días"}


RELLENO = {"tiempo", "proceso", "5", "cinco", "realmente", "normalmente", "exactamente", "persona", "alguien"}


def agrupar(lista):
    """Agrupa frases casi iguales ("cuánto dura el duelo" / "cuánto tiempo dura un duelo")."""
    grupos = []
    for k, r in lista:
        p = palabras(k) | ({k.split()[0]} if k.split() else set())
        for g in grupos:
            extra = (p ^ g["p"])
            if p and g["p"] and ((p <= g["p"] or g["p"] <= p) and extra <= RELLENO
                                 or len(p & g["p"]) / len(p | g["p"]) > 0.8):
                g["variantes"].append(r["texto"])
                g["fuentes"] |= r["fuentes"]
                break
        else:
            grupos.append({"k": k, "r": r, "p": p, "variantes": [], "fuentes": set(r["fuentes"])})
    return grupos


def historial_anterior(hoy):
    archivos = sorted(f for f in glob.glob(os.path.join(HISTORIAL, "*.json")) if os.path.basename(f) < hoy + ".json")
    if not archivos:
        return None, set()
    with open(archivos[-1], encoding="utf-8") as f:
        datos = json.load(f)
    return os.path.basename(archivos[-1])[:-5], {d["clave"] for d in datos.get("busquedas", [])}


def barras(valores):
    bloques = "▁▂▃▄▅▆▇█"
    lo, hi = min(valores), max(valores)
    if hi == lo:
        return bloques[3] * len(valores)
    return "".join(bloques[int((v - lo) / (hi - lo) * (len(bloques) - 1))] for v in valores)


# --------------------------------------------------------------------------- #
#  Reporte
# --------------------------------------------------------------------------- #

def fuentes_txt(r):
    return " · ".join(FUENTES[f] for f in FUENTES if f in r["fuentes"])


def celda(s):
    return s.replace("|", "\\|")


def escribir_reporte(cfg, res, wiki, trends, consultor, rapido, posts, hoy=None):
    reescrito = hoy is not None
    hoy = hoy or date.today().isoformat()
    anterior_fecha, anteriores = historial_anterior(hoy)
    filas = sorted(res.items(), key=lambda kv: -kv[1]["puntaje"])
    for clave, r in filas:
        r["cubierto"] = cubierto(clave, posts)

    preguntas = [(k, r) for k, r in filas if es_pregunta(k)]
    locales = [(k, r) for k, r in filas if es_local(k, cfg)]
    nuevas = [(k, r) for k, r in filas if anteriores and k not in anteriores]
    activas = [FUENTES[f] for f in FUENTES if f not in consultor.desactivadas]

    L = []
    w = L.append
    w("# Ideas para el blog")
    w("")
    w("Reporte generado el **%s** a partir de lo que la gente busca en internet en Colombia." % fecha_larga(hoy))
    w("")
    w("> **Cómo leerlo:** cada frase es algo que personas reales escriben en el buscador. No es necesario usarlas todas: "
      "sirven de inspiración para elegir temas y títulos. Las que aparecen en varias fuentes y con puntaje más alto "
      "son las que más se repiten.")
    w("")
    w("- **Búsquedas encontradas:** %d (a partir de %d temas de partida)" % (len(res), len(cfg["semillas"])))
    w("- **Fuentes consultadas:** %s, Google Trends y Wikipedia" % ", ".join(activas))
    if consultor.desactivadas:
        w("- **No respondieron esta vez:** %s" % ", ".join("%s (%s)" % (FUENTES[f], m) for f, m in consultor.desactivadas.items()))
    if rapido:
        w("- Versión **rápida** (sin la expansión a–z). Para un reporte más completo: `python3 tools/ideas.py`")
    w("")
    w("**Contenido:** [Ideas de artículos](#ideas-de-artículos) · [Las búsquedas más fuertes](#las-búsquedas-más-fuertes) · "
      "[Búsquedas locales](#búsquedas-locales) · [Lo nuevo](#lo-nuevo-desde-el-reporte-anterior) · "
      "[Calendario](#calendario-editorial) · [Por tema](#búsquedas-por-tema) · [Sobre los datos](#sobre-estos-datos)")
    w("")

    # Ideas de artículos
    w("## Ideas de artículos")
    w("")
    w("Preguntas que la gente hace. Cada una puede ser el título de un artículo (o una sección dentro de uno).")
    w("")
    w("| # | Título posible | También se busca como | Se busca en | ¿Ya hay un artículo? |")
    w("|---|---|---|---|---|")
    grupos = agrupar(preguntas)
    elegidos = [g for g in grupos if not g["r"]["cubierto"]][:25] + [g for g in grupos if g["r"]["cubierto"]][:5]
    for i, g in enumerate(elegidos, 1):
        r = g["r"]
        w("| %d | %s | %s | %s | %s |" % (
            i, celda(titulo_sugerido(r["texto"])), celda(" · ".join(g["variantes"][:2])) or "—",
            fuentes_txt({"fuentes": g["fuentes"]}),
            celda("Sí: «%s»" % r["cubierto"]) if r["cubierto"] else "—"))
    if not preguntas:
        w("| — | No se encontraron preguntas esta vez. | | | |")
    w("")

    # Más fuertes
    w("## Las búsquedas más fuertes")
    w("")
    w("Las 30 frases que más se repiten entre todas las fuentes. El puntaje sube cuando la frase aparece en las primeras "
      "posiciones y en varias fuentes a la vez (no es un número de personas).")
    w("")
    w("| # | Búsqueda | Puntaje | Se busca en |")
    w("|---|---|---|---|")
    for i, (k, r) in enumerate(filas[:30], 1):
        w("| %d | %s%s | %s | %s |" % (i, celda(r["texto"]), " ✅" if r["cubierto"] else "", r["puntaje"], fuentes_txt(r)))
    w("")
    w("✅ = ya hay un artículo publicado sobre esto.")
    w("")

    # Locales
    w("## Búsquedas locales")
    w("")
    w("Búsquedas que mencionan Manizales, Caldas, Colombia u otras ciudades del país. Útiles para que el blog aparezca cuando "
      "alguien de la región busca ayuda.")
    w("")
    if locales:
        for k, r in locales[:20]:
            w("- %s  _(%s)_" % (r["texto"], fuentes_txt(r)))
    else:
        w("_No aparecieron búsquedas locales esta vez._")
    w("")

    # Nuevas
    w("## Lo nuevo desde el reporte anterior")
    w("")
    if anterior_fecha is None:
        w("_Este es el primer reporte. La próxima vez aquí aparecerán las búsquedas que no estaban antes._")
    elif nuevas:
        w("Búsquedas que no aparecían en el reporte del %s:" % fecha_larga(anterior_fecha))
        w("")
        for k, r in nuevas[:20]:
            w("- %s" % r["texto"])
    else:
        w("_No hay búsquedas nuevas respecto al reporte del %s._" % fecha_larga(anterior_fecha))
    w("")

    # Calendario
    w("## Calendario editorial")
    w("")
    w("### Fechas del año que invitan a escribir")
    w("")
    mes_actual = date.today().month
    proximas = sorted(cfg.get("fechas", []), key=lambda f: (f["mes"] - mes_actual) % 12)
    w("Ordenadas a partir de este mes. Conviene publicar 2 a 3 semanas antes de cada fecha.")
    w("")
    w("| Fecha | Idea |")
    w("|---|---|")
    for f in proximas:
        w("| %s | %s |" % (celda(f["fecha"]), celda(f["tema"])))
    w("")
    if wiki:
        w("### ¿En qué meses hay más interés?")
        w("")
        w("Visitas mensuales a artículos de Wikipedia en español (todos los países hispanohablantes, no solo Colombia). "
          "Las barras muestran los últimos 12 meses; los meses más altos son buenos momentos para publicar sobre ese tema.")
        w("")
        w("| Tema | Últimos 12 meses | Meses con más interés |")
        w("|---|---|---|")
        for nombre, serie in wiki.items():
            ult = serie[-12:]
            vals = [v for _, v in ult]
            top = sorted(ult, key=lambda x: -x[1])[:3]
            w("| %s | `%s` %s–%s | %s |" % (
                nombre, barras(vals), mes_corto(ult[0][0]), mes_corto(ult[-1][0]),
                ", ".join(MESES_LARGOS[int(m[4:]) - 1] for m, _ in top)))
        w("")
    w("### Tendencias de hoy en Colombia")
    w("")
    if trends is None:
        w("_Google Trends no respondió esta vez._")
    elif trends:
        w("Temas en tendencia hoy en Google Colombia relacionados con el duelo o la pérdida (útiles para un artículo oportuno, "
          "siempre con respeto):")
        w("")
        for t in trends:
            w("- **%s** %s — %s" % (t["titulo"], "(%s búsquedas)" % t["trafico"] if t["trafico"] else "", t["contexto"]))
    else:
        w("_Hoy no hay tendencias en Colombia relacionadas con estos temas._")
    w("")

    # Por tema
    w("## Búsquedas por tema")
    w("")
    w("Haz clic en cada tema para ver lo que se busca a partir de esa frase.")
    w("")
    for semilla in cfg["semillas"]:
        del_tema = [(k, r) for k, r in filas if semilla in r["semillas"]][:20]
        w("<details><summary><b>%s</b> (%d)</summary>" % (semilla, len(del_tema)))
        w("")
        for k, r in del_tema:
            w("- %s%s" % (r["texto"], " ✅" if r["cubierto"] else ""))
        if not del_tema:
            w("- _Sin resultados._")
        w("")
        w("</details>")
        w("")

    # Sobre los datos
    w("## Sobre estos datos")
    w("")
    w("- **Qué muestran:** las sugerencias que Google, YouTube y DuckDuckGo ofrecen mientras alguien escribe, configuradas "
      "para Colombia y en español. Esas sugerencias salen de búsquedas reales y frecuentes.")
    w("- **Qué no muestran:** cuántas personas buscan cada frase. Los buscadores no publican esos números de forma gratuita.")
    w("- **Facebook e Instagram (Meta)** no publican datos de búsqueda, por eso no aparecen aquí.")
    w("- **Para tener cifras reales más adelante:** cuando el blog lleve unas semanas en línea, conectar el sitio a "
      "**Google Search Console** (gratis) muestra exactamente qué búsquedas traen visitas al sitio de Katherine. "
      "El **Planificador de palabras clave de Google Ads** da volúmenes aproximados por mes.")
    w("- **Cómo actualizar:** `python3 tools/ideas.py`. Los temas de partida se cambian en `ideas/temas.json`.")
    w("")

    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    if reescrito:
        return len(preguntas), len(locales), len(nuevas)
    os.makedirs(HISTORIAL, exist_ok=True)
    with open(os.path.join(HISTORIAL, hoy + ".json"), "w", encoding="utf-8") as f:
        json.dump({
            "fecha": hoy,
            "generado": datetime.now().isoformat(timespec="seconds"),
            "fuentes_omitidas": consultor.desactivadas,
            "busquedas": [{"clave": k, "texto": r["texto"], "puntaje": r["puntaje"], "fuentes": sorted(r["fuentes"]),
                           "semillas": sorted(r["semillas"])} for k, r in filas],
            "wikipedia": wiki,
            "tendencias": trends,
        }, f, ensure_ascii=False, indent=1)
    return len(preguntas), len(locales), len(nuevas)


def fecha_larga(iso):
    d = date.fromisoformat(iso)
    return "%d de %s de %d" % (d.day, MESES_LARGOS[d.month - 1], d.year)


def mes_corto(aaaamm):
    return "%s %s" % (MESES[int(aaaamm[4:]) - 1], aaaamm[2:4])


def desde_historial(cfg):
    archivos = sorted(glob.glob(os.path.join(HISTORIAL, "*.json")))
    if not archivos:
        sys.exit("Error: todavía no hay datos guardados. Ejecuta primero: python3 tools/ideas.py")
    with open(archivos[-1], encoding="utf-8") as f:
        datos = json.load(f)
    excluir = [normalizar(x) for x in cfg.get("excluir", [])]
    relacionadas = [normalizar(x) for x in cfg.get("relacionadas", [])]
    res = {}
    for d in datos["busquedas"]:
        k = d["clave"]
        if any(x and x in k for x in excluir) or (relacionadas and not any(x and x in k for x in relacionadas)):
            continue
        res[k] = {"texto": d["texto"], "fuentes": set(d["fuentes"]), "semillas": set(d["semillas"]), "puntaje": d["puntaje"]}
    consultor = Consultor()
    consultor.desactivadas = datos.get("fuentes_omitidas", {})
    return res, datos.get("wikipedia", {}), datos.get("tendencias"), consultor, datos["fecha"]


def main():
    ap = argparse.ArgumentParser(description="Reporte de ideas para el blog con búsquedas en Colombia.")
    ap.add_argument("--rapido", action="store_true", help="versión corta, sin la expansión a–z")
    ap.add_argument("--reescribir", action="store_true", help="rehacer el reporte con los últimos datos, sin buscar de nuevo")
    a = ap.parse_args()

    try:
        with open(TEMAS, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        sys.exit("Error: no encuentro %s" % TEMAS)
    except json.JSONDecodeError as e:
        sys.exit("Error: ideas/temas.json tiene un error de formato en la línea %d (revisa comas y comillas)." % e.lineno)
    if not cfg.get("semillas"):
        sys.exit("Error: ideas/temas.json no tiene 'semillas'.")

    posts = []
    if os.path.exists(POSTS):
        with open(POSTS, encoding="utf-8") as f:
            posts = json.load(f)

    if a.reescribir:
        res, wiki, trends, consultor, fecha = desde_historial(cfg)
        n_preg, n_loc, n_nuevas = escribir_reporte(cfg, res, wiki, trends, consultor, False, posts, fecha)
        print("Reporte reescrito con los datos del %s: %d búsquedas, %d preguntas, %d locales." % (fecha, len(res), n_preg, n_loc))
        return

    consultor = Consultor()
    print("1/3 Buscando sugerencias en Google, YouTube y DuckDuckGo…")
    res = recolectar(cfg, consultor, a.rapido)
    if len(consultor.desactivadas) == len(FUENTES):
        sys.exit("Error: ninguna fuente respondió. ¿Hay conexión a internet? Intenta de nuevo más tarde.")
    print("2/3 Revisando Wikipedia y Google Trends…")
    wiki = wikipedia(cfg, consultor)
    trends = tendencias(cfg, consultor)
    print("3/3 Escribiendo el reporte…")
    n_preg, n_loc, n_nuevas = escribir_reporte(cfg, res, wiki, trends, consultor, a.rapido, posts)
    print("\nListo: %d búsquedas, %d preguntas, %d locales, %d nuevas." % (len(res), n_preg, n_loc, n_nuevas))
    print("  Reporte: ideas/REPORTE.md")


if __name__ == "__main__":
    main()
