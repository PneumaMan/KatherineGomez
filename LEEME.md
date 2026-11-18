# LEEME — Cómo funciona el blog

Esta guía explica, en palabras sencillas, cómo publicar un artículo nuevo, cómo corregir uno que ya está publicado y cómo mantener todo ordenado para evitar errores.

---

## La idea en una frase

**Katherine escribe en Google Docs → un script convierte el documento en una página del sitio → el equipo lo revisa y lo pone en línea.**

Katherine no necesita tocar código. El documento de Google es el "original" de cada artículo; la página del sitio es solo una copia generada a partir de él.

## Quién hace qué

| Paso | Quién | Qué hace |
|---|---|---|
| 1. Escribir | Katherine | Escribe el artículo en un Google Doc y lo comparte. |
| 2. Publicar | Equipo técnico (o Katherine, si tiene acceso) | Ejecuta el script con el enlace del documento. Se crea una propuesta de cambio (*pull request*). |
| 3. Revisar | Katherine + equipo | Miran la vista previa que genera GitHub/Azure en la propuesta. |
| 4. Aprobar | PneumaMan | Aprueba y fusiona la propuesta. El artículo queda en línea en el sitio. |

Nada aparece en el sitio público hasta que PneumaMan aprueba.

---

## 1. Escribir un artículo nuevo

**Regla de oro: un documento de Google = un artículo.** No pongas varios artículos en el mismo documento.

1. Crea un Google Doc nuevo (dentro de la carpeta del blog, ver "Mantenerse organizada" más abajo).
2. **Título:** en la primera línea. Ideal: aplícale el estilo **Título** (menú *Formato → Estilos de párrafo → Título*). Si no, el script toma la primera línea como título.
3. **Resumen (opcional):** en la segunda línea, con el estilo **Subtítulo**. Se muestra debajo del título y en la tarjeta de la página del blog. Si no hay subtítulo, se usa el primer párrafo.
4. **Secciones:** para los subtítulos dentro del texto puedes:
   - usar el estilo **Encabezado 1** o **Encabezado 2**, o
   - escribir una línea corta **toda en negrita** (sin punto ni dos puntos al final). El script la convierte en subtítulo.
5. Puedes usar con tranquilidad: **negrita**, *cursiva*, enlaces, listas con viñetas o números, tablas y notas al pie.
6. **Imágenes (opcional):** insértalas en su propia línea, no en medio de un párrafo. La **primera imagen** será la foto de portada en la tarjeta del blog. Si no hay imágenes, la tarjeta muestra el logo.
   - Para describir la imagen (ayuda a personas con discapacidad visual y a Google): clic derecho sobre la imagen → *Texto alternativo*.
7. Los **comentarios** del documento **no** se publican. Puedes usarlos libremente para notas y revisiones.

### Compartir el documento

En el documento: **Compartir → Acceso general → "Cualquier persona con el enlace" → Lector**. Copia el enlace y envíalo al equipo (o úsalo tú misma en el paso siguiente).

> ¿Prefieres no compartirlo con enlace? Descárgalo con **Archivo → Descargar → Página web (.html, comprimido)** y envía el archivo `.zip`.

---

## 2. Publicar el artículo

En la carpeta del sitio, en la Terminal:

```
python3 tools/publicar.py "ENLACE-DEL-DOCUMENTO" --pr
```

El script:

1. descarga el documento,
2. crea la página del artículo en la carpeta `blog/`,
3. actualiza la página principal del blog (las tarjetas),
4. actualiza los botones **Anterior / Siguiente** de todos los artículos,
5. con `--pr`: guarda el cambio y lo sube a GitHub. Al final muestra un enlace: ábrelo y pulsa **Create pull request**.

**¿Solo quieres ver cómo queda, sin subir nada?** Ejecuta el mismo comando **sin** `--pr` y abre la página que indica en el navegador.

**¿Quieres elegir la fecha?** Agrega `--fecha AAAA-MM-DD`, por ejemplo `--fecha 2026-12-01`. Si no, se usa la fecha de hoy.

---

## 3. Corregir un artículo ya publicado

1. Edita **el mismo** Google Doc (no crees uno nuevo).
2. Ejecuta **el mismo comando con el mismo enlace**:
   ```
   python3 tools/publicar.py "ENLACE-DEL-MISMO-DOCUMENTO" --pr
   ```
3. El script reconoce el documento y **actualiza** el artículo existente. Se conservan su dirección web y su fecha.

Cosas que conviene saber:

- **Cambiar el título no cambia la dirección web** del artículo. Es a propósito: así no se rompen los enlaces que ya se hayan compartido en redes.
- Si borras una imagen del documento, también desaparece del sitio al volver a publicar.
- **Nunca edites a mano los archivos `.html` de la carpeta `blog/`.** Se sobrescriben cada vez que se publica. Toda corrección se hace en el Google Doc.

---

## 4. Otras acciones

| Quiero… | Comando |
|---|---|
| Ver la lista de artículos publicados | `python3 tools/publicar.py --lista` |
| Eliminar un artículo | `python3 tools/publicar.py --borrar NOMBRE-EN-LA-LISTA` y luego crear la propuesta de cambio |
| Regenerar todas las páginas (tras un cambio de diseño) | `python3 tools/publicar.py --reconstruir` |

El "nombre en la lista" es la dirección del artículo, por ejemplo `como-acompanar-a-alguien-en-duelo`.

---

## 5. Mantenerse organizada

Una carpeta en Google Drive, con esta estructura:

```
Blog – Katherine Gómez/
├── 1. Borradores/        ← artículos en proceso
├── 2. Listos para publicar/
└── 3. Publicados/        ← no borrar: son los originales del sitio
```

- **Nombra los documentos con fecha y título:** `2026-12-01 – Cómo acompañar a alguien en duelo`. Así quedan ordenados solos.
- Mueve el documento de carpeta según avanza. Mover un documento de carpeta **no** cambia su enlace.
- **No borres ni dupliques los documentos publicados.** Si haces una copia, la copia tiene otro enlace y el script la trataría como un artículo **nuevo** (quedaría duplicado).
- Lleva, si quieres, una nota con el enlace de cada documento publicado (o pídele al equipo la lista con `--lista`).

---

## 6. Lista de revisión antes de publicar

- [ ] El título está en la primera línea.
- [ ] El documento está compartido como "Cualquier persona con el enlace → Lector".
- [ ] Revisé ortografía y tildes (el sitio publica exactamente lo que está en el documento).
- [ ] Las imágenes están en su propia línea y tengo permiso para usarlas.
- [ ] Los enlaces funcionan.
- [ ] Es un documento **nuevo** si es un artículo nuevo, o **el mismo** documento si es una corrección.
- [ ] Revisé la vista previa en la propuesta de cambio, también desde el celular.

---

## 7. Problemas frecuentes

| Mensaje o situación | Qué significa | Solución |
|---|---|---|
| *"No pude descargar el documento"* | El documento no está compartido con enlace. | Compartir → "Cualquier persona con el enlace" → Lector. O usar el `.zip`. |
| *"No reconozco esto como un enlace de Google Docs"* | El enlace está incompleto o no es de un documento. | Copia el enlace completo desde el botón **Compartir**. |
| *"La fecha debe tener el formato AAAA-MM-DD"* | Fecha mal escrita. | Ejemplo correcto: `2026-12-01`. |
| El artículo salió **duplicado** | Se publicó una copia del documento en vez del original. | Borrar el duplicado con `--borrar` y en adelante usar siempre el documento original. |
| Un subtítulo salió como texto normal | La línea no es corta, no está toda en negrita, o termina en punto o dos puntos. | Aplicar el estilo **Encabezado 1**. |
| El orden de los artículos no es el esperado | Se ordenan por fecha, del más nuevo al más antiguo. | Volver a publicar con `--fecha` para fijar la fecha correcta. |
| Una corrección no aparece en el sitio | Se volvió a publicar pero la propuesta aún no está aprobada. | Esperar la aprobación de PneumaMan. |

---

## 8. Ideas para nuevos artículos

En la carpeta `ideas/` hay un **reporte de ideas**: `ideas/REPORTE.md`. Se lee directamente en GitHub (abre el archivo y se ve con formato).

**Qué contiene:** lo que la gente en Colombia escribe en Google, YouTube y DuckDuckGo sobre el duelo y temas cercanos, organizado así:

- **Ideas de artículos:** preguntas reales convertidas en posibles títulos, con sus variantes.
- **Las búsquedas más fuertes:** las frases que más se repiten.
- **Búsquedas locales:** lo que se busca mencionando Manizales o Colombia.
- **Lo nuevo:** búsquedas que no estaban en el reporte anterior.
- **Calendario editorial:** fechas del año para preparar artículos (Día de la Madre, 2 de noviembre, Navidad…) y los meses con más interés.
- Una marca ✅ cuando ya existe un artículo sobre ese tema.

**Cómo usarlo:** no es una lista de tareas. Es inspiración: elige las preguntas que conectan con tu experiencia y con lo que tus pacientes te preguntan. Usar las mismas palabras que la gente busca en el título ayuda a que Google muestre el artículo.

**Actualizarlo (PneumaMan), una vez al mes es suficiente:**

```
python3 tools/ideas.py
```

Tarda unos 5 a 8 minutos y reemplaza el reporte. Luego se sube con un pull request, como cualquier otro cambio. Para una versión más rápida: `python3 tools/ideas.py --rapido`.

**Cambiar los temas que se investigan:** edita `ideas/temas.json` (las "semillas" son las frases de partida; "excluir" quita resultados que no tienen que ver, como películas o juegos). Si solo cambiaste "excluir" o "local", no hace falta buscar de nuevo: `python3 tools/ideas.py --reescribir` rehace el reporte en segundos con los datos guardados.

**Límites honestos:** el reporte muestra *qué* se busca, no *cuántas personas* lo buscan. Facebook e Instagram no publican datos de búsqueda. Para cifras reales, cuando el blog lleve unas semanas en línea, conviene conectar el sitio a Google Search Console (gratis).

---

## Para el equipo técnico

- **Dónde está todo:** `blog/` (páginas generadas, `blog.css`, `posts.json`, `img/`), `tools/publicar.py` (publicación) y `tools/ideas.py` + `ideas/` (reporte de ideas). Ambos scripts solo usan Python 3, sin instalar nada.
- **Fuentes del reporte de ideas:** autocompletado público de Google, YouTube y DuckDuckGo (región Colombia), RSS de tendencias diarias de Google Trends (CO) y la API de visitas de Wikimedia. No requieren claves. Son servicios no oficiales para este uso: el script consulta despacio (0,5 s entre consultas) y, si una fuente bloquea o falla, la omite y lo indica en el reporte. Usarlo con moderación (mensual).
- **`blog/posts.json`** es el registro de artículos (título, fecha, resumen, portada, id del Google Doc). Lo mantiene el script; no editarlo a mano salvo emergencia.
- **El texto de cada artículo** vive dentro de su página, entre los comentarios `<!-- contenido:inicio -->` y `<!-- contenido:fin -->`. `--reconstruir` reaprovecha ese texto y vuelve a generar todo lo demás (cabecera, pie, Anterior/Siguiente).
- **Cambiar el diseño:** colores y tipografía en `blog/blog.css`; la estructura (cabecera, pie, tarjeta, botones) en las funciones `cabecera`, `PIE`, `pagina_post` y `pagina_indice` de `tools/publicar.py`. Después ejecutar `--reconstruir`.
- **Despliegue:** al fusionar en `main`, los workflows de `.github/workflows/` publican en Azure. Cada pull request genera también una vista previa de Azure Static Web Apps.
