# Cartelera de cines de Buenos Aires: arquitectura y stack

## Contexto
App web para una clase: cartelera de los próximos 10 días de unos 40 cines de Buenos Aires. Se filtra por horarios y se puede cruzar con Google Calendar (disponibilidad) y con Letterboxd (gustos) para recomendar funciones. La usan varias personas, incluida la profesora, así que la cartelera tiene que funcionar completa sin login ni conexiones. Calendario y Letterboxd son capas opcionales e independientes. La carpeta del proyecto hoy solo tiene la exportación personal de Letterboxd (carpeta y zip). No hay código ni repositorio git.

Lo que encontré en la exportación (solo leí encabezados): `watchlist.csv` y `watched.csv` = `Date,Name,Year,Letterboxd URI`; `ratings.csv` agrega `Rating`; `diary.csv` agrega `Rating,Rewatch,Tags,Watched Date`; los CSV de `lists/` tienen una línea de cabecera extra ("Letterboxd list export v7"). **No trae tmdb_id**, así que el cruce va por título y año.

## Idea central
**La parte pesada pasa una vez por día, fuera del navegador. Lo personal pasa dentro del navegador.**

```
GitHub Actions (cron diario)
  └─ python -m cartelera ingest  → SQLite (data/cartelera.db)
  └─ python -m cartelera export  → public/data/cartelera.json (próximos 10 días + última actualización por cine)
  └─ commit al repo → Cloudflare Pages se vuelve a publicar solo

Cloudflare Pages (gratis)
  ├─ public/  sitio estático: HTML + JS sin build + CSS (tema oscuro)
  └─ functions/ (2 funciones chicas en JS)
       /api/letterboxd?user=  → lee el RSS público y lo devuelve como JSON (el RSS no permite CORS)
       /api/tmdb/resolve      → título+año → tmdb_id y director, en lote, con caché (la key de TMDB queda en el servidor)

Navegador
  filtro de horarios, cines elegidos, usuario de Letterboxd → localStorage
  Google Calendar: token de GIS solo en memoria; freeBusy se consulta desde el navegador
  zip de Letterboxd: se lee en el navegador con JSZip; nunca se sube al servidor
  puntaje de "Para vos": se calcula en el navegador con config/pesos.json
```

Por qué así: es la opción gratuita más simple que cumple todo. No hay un servidor siempre prendido y SQLite no se pierde: los planes gratis de Render o Fly no tienen disco persistente, y acá la base vive en el repo. Ningún dato personal pasa por un servidor propio: el RSS y TMDB pasan por las funciones, pero no se guardan. La cartelera es un JSON estático, así que abre rápido y no depende de nada.

## Stack
- **Ingest**: Python 3.12 con `uv`, `httpx`, `selectolax` (HTML), `pypdf` (PDF), `pydantic` (esquema), `anthropic` (SDK oficial), `sqlite3` de la biblioteca estándar, `pytest`. CLI con `argparse`.
- **Frontend**: HTML + módulos ES de JS sin paso de build. JSZip desde cdnjs. Sin framework.
- **Funciones**: Cloudflare Pages Functions (JS, unas 50 líneas cada una).
- **LLM**: `claude-opus-5-5` con structured outputs (`client.messages.parse` y un modelo Pydantic estricto), `fallbacks: "default"` ante rechazos, y caché por hash del texto: si el PDF o la nota no cambió, no se vuelve a llamar. Son pocas llamadas por día, así que el costo es mínimo.
- **Secretos**: `.env` local (`TMDB_API_KEY`, `ANTHROPIC_API_KEY`), secrets de GitHub Actions y variable de entorno de Cloudflare (solo TMDB). El Google Client ID es público y va en `public/config.js`.

## Estructura
```
config/cines.yaml          registro: id, nombre a mostrar, direccion, tanda, es_comercial, adaptador
config/pesos.json          pesos de la recomendación (se copia a public/ al exportar)
cartelera/
  schema.py                Funcion (pydantic): cine, direccion, fecha_hora, titulo, titulo_original?,
                           ciclo?, url_entradas?, modo_venta (online|boleteria|gratis), es_comercial
  db.py                    tablas y reemplazo idempotente
  ingest.py / export.py / enrich_tmdb.py / cli.py
  llm_extract.py           extracción común para Lugones y Museo del Cine + validación del día de la semana
  adapters/base.py         interfaz: fetch() -> fuentes crudas ; parse(crudo, hoy) -> list[Funcion]
  adapters/gaumont.py ...  uno por cine
tests/fixtures/<cine>/     HTML/JSON/texto guardados ; tests/fixtures/letterboxd/ con datos inventados
docs/fuentes.md            por cine: formato, robots.txt, términos, URL
docs/google-calendar.md    guía paso a paso de Google Cloud (hito 6)
functions/api/...          funciones de Cloudflare
public/                    index.html, app.js, módulos, styles.css, data/
.claude/skills/agregar-cine/SKILL.md   (al final del hito 3)
CLAUDE.md, .env.example, .gitignore    (.gitignore incluye .env y letterboxd-*/ y letterboxd-*.zip)
```

## SQLite
- `cines`: datos del YAML + `ultima_actualizacion`, `ultimo_estado`, `ultimo_error`.
- `funciones`: el esquema pedido + `pelicula_id` + `fuente_url`. Fechas en hora de Buenos Aires (`-03:00`).
- `peliculas`: clave por título normalizado + título original + año aproximado. Campos `tmdb_id`, `director`, `anio`, `duracion_min`, `letterboxd_url` (`https://letterboxd.com/tmdb/{id}`, a verificar), `match_estado` (ok | sin_match | ambiguo), `match_motivo`.
- `extracciones_llm`: cine, url, hash del texto, **texto original**, JSON resultante, modelo, fecha, errores de validación.
- `ingest_runs`: fecha, cine, cantidad de funciones, error.

**Ingest idempotente**: cada adaptador corre por separado y con su propio try. Si sale bien, en una transacción se borran las funciones futuras de ese cine, se insertan las nuevas y se actualiza `ultima_actualizacion`. Si falla, se conservan las funciones anteriores, se guarda el error y se sigue con el próximo cine. Al final se imprime un resumen (ok o error por cine). Correrlo dos veces deja el mismo resultado.

## Enriquecimiento con TMDB
Se busca con título original y año cuando existen, si no con el título en castellano (`language=es-AR`). Para aceptar un resultado hacen falta las dos condiciones: el título normalizado coincide (original o traducido) **y** el año está a ±1 o, si no hay año, el director coincide. Con duración, director y año de los créditos del detalle. Si hay ambigüedad o no hay match, los campos quedan vacíos con `match_estado` y se ve una marca en la interfaz. Nunca se completa con datos adivinados. Hay caché por película para no volver a consultar.

## Lugones y Museo del Cine (LLM)
1. Descubrimiento: Lugones lee la página de cine de complejoteatral.gob.ar y busca los PDF vigentes. Museo del Cine lee la página del museo en buenosaires.gob.ar y busca las notas del mes o de la quincena vigente.
2. Se extrae el texto: `pypdf` para el PDF, selectolax para el cuerpo de la nota.
3. Se llama a Claude con un esquema estricto: `{periodo_desde, periodo_hasta, peliculas:[{titulo, titulo_original?, pais?, anio?, director?, ciclo?, funciones:[{dia_semana_texto, fecha (YYYY-MM-DD), hora (HH:MM)}]}]}`. El mes sale del texto introductorio del PDF. En el Museo, el ciclo es lo que sigue a la barra "|".
4. Validación en Python: el día de la semana de `fecha` tiene que coincidir con `dia_semana_texto` y la fecha tiene que caer dentro del período. Lo que no pasa se descarta y se reporta; no se corrige "a mano".
5. Se guardan el texto original y el resultado. En Lugones el ciclo es el título del PDF. En el Museo, `modo_venta=gratis` sin url de entradas, y la interfaz muestra "gratis, se retira en el lugar".

## Interfaz (de arriba hacia abajo)
1. Google Calendar opcional: botón Conectar/Desconectar con estado visible y márgenes configurables (30 min antes, 15 después).
2. Filtro de horarios: chips "Todos", "Lun a jue desde las 18", "Vie, sáb y dom", "Personalizar" (días + rango horario por día). Los presets se suman (unión), filtra por hora de inicio y se guarda en localStorage.
3. Selector de 10 días con la cantidad de funciones por día, contando ya el filtro.
4. Chips de cines con el toggle "+ comerciales". La tanda 4 viene apagada por defecto.
5. "Para vos": visible solo con Letterboxd cargado. Las 5 funciones con mayor puntaje que pasan el filtro (y el calendario, si está conectado), cada una con su motivo.
6. Tabla ordenable: hora, cine (con la dirección debajo), película, ciclo, director, año, duración, entradas, Letterboxd, calendario (entra / justo / no entra, con el bloque ocupado), vista ("vista hace poco" / "vista", con la fecha al pasar el mouse). El toggle "solo las que me entran" aparece solo con el calendario conectado. Cada fila tiene un link prearmado de Google Calendar (`calendar.google.com/calendar/render?action=TEMPLATE...`).
7. Onboarding: una pantalla al primer ingreso con los pasos opcionales (Letterboxd, zip, Calendar), todos salteables.
8. Pie con la última actualización por cine y los que fallaron.

**Calendario**: token client de GIS, scope de solo disponibilidad (hoy creo que es `https://www.googleapis.com/auth/calendar.freebusy`; **lo verifico contra la documentación al empezar el hito 6**). El token queda solo en memoria y se consulta `freeBusy` sobre `primary` para los 10 días. Sin refresh tokens y sin escribir nada en el servidor.

**Letterboxd**: el RSS de `letterboxd.com/{user}/rss/` (verifico los campos en el hito 7; espero `letterboxd:watchedDate`, `letterboxd:memberRating`, `letterboxd:filmTitle`, `letterboxd:filmYear`, `tmdb:movieId`, y solo las últimas ~50 entradas). El zip o la carpeta se procesan en el navegador. El zip se lee con JSZip. Para la carpeta descomprimida, un `<input webkitdirectory>` toma los mismos CSV, y en el desarrollo un script de Python lee la carpeta local para probar. El cruce con la cartelera se hace por tmdb_id (RSS) o por título normalizado y año ±1 (zip), y si no alcanza, con `/api/tmdb/resolve`. Para "director que me gusta" se resuelven los directores de las películas con 4★ o más, con caché en localStorage.

**Puntaje** (`config/pesos.json`, sin LLM): watchlist (+), director con 2+ películas con 4★ o más (+), escasez: pocas funciones en los 10 días (+, escalonado), vista hace poco (−; umbral de 6 meses configurable). "Vista" nunca oculta una función.

## Hitos (freno al final de cada uno para que pruebes)
0. Base: `git init`, `.gitignore` (con la carpeta y el zip de Letterboxd), `CLAUDE.md`, `.env.example`, `config/cines.yaml` con los 41 cines, esquema y DB.
1. **Gaumont de punta a punta en consola**: inspeccionar el sitio (formato, robots.txt, términos → `docs/fuentes.md`), elegir JSON interno si existe, fixture, test, `ingest` y una vista en consola.
2. **TMDB**: enriquecimiento, marca de "sin match", tests con respuestas grabadas.
3. **Lugones**: descubrimiento de PDF, extracción con LLM, validación, tests sobre el texto fijado; después la skill `agregar-cine`.
4. **Resto de la tanda 1** (Cosmos, Lorca, MALBA) usando la skill.
5. **Interfaz con datos reales y filtro de horarios**: `export`, sitio estático, prueba local con `python -m http.server`.
6. **Calendario** y la guía `docs/google-calendar.md`.
7. **Letterboxd y "Para vos"** (RSS de prueba con tu usuario solo en desarrollo, sin dejarlo como valor por defecto; tests con el fixture inventado).
8. **Publicar**: repo en GitHub, Cloudflare Pages, Action diaria, prueba desde otra cuenta de Google agregada como usuaria de prueba.
9. **Tandas 4, 2 y 3**, en ese orden. Museo del Cine entra en la tanda 2 con la estrategia LLM. En la tanda 3 hay que filtrar qué es cine.

Antes de escribir cada adaptador te cuento cómo publica el sitio y qué dicen su robots.txt y sus términos. Si un sitio lo prohíbe, te consulto antes de seguir.

## Verificación
- `uv run pytest`: el parser de cada cine contra su fixture con un "hoy" fijo, la validación del día de la semana, la idempotencia (correr el ingest dos veces da lo mismo), un adaptador que falla sin cortar el resto, el importador de Letterboxd con el fixture inventado (en zip y en carpeta) y el puntaje.
- `uv run python -m cartelera ingest` real y después `export`; revisar el resumen y el JSON.
- Abrir el sitio en el navegador del panel: filtros, orden, onboarding, ancho de celular, todo sin conexiones.
- Hitos 6 y 7: probar con tu cuenta. Hito 8: probar desde otra cuenta de Google en la URL publicada.
