# Mi Cartelera BA: cartelera de cines de Buenos Aires

App web con la cartelera de los próximos 10 días de cines de Buenos Aires. Se filtra por horarios y se puede cruzar, de forma opcional, con Google Calendar y con Letterboxd. Es para una clase y la usan otras personas, así que la cartelera tiene que funcionar completa sin login ni conexiones.
El plan aprobado, con la arquitectura y los hitos, está en `docs/plan.md`.

## Arquitectura
- **Ingest (Python, una vez por día):** un adaptador por cine lee la web oficial y el resultado se guarda en SQLite (`data/cartelera.db`). Desde el hito 5, `export` genera un JSON estático para el sitio.
- **Sitio (desde el hito 5):** HTML y JS sin build en `public/`, publicado en **Vercel** (`vercel.json`: `outputDirectory: public`).
  - Hay una sola función: el proxy del RSS de Letterboxd, en `api/letterboxd.mjs`. El parser está en `api/_letterboxd-rss.mjs`; los archivos que empiezan con `_` Vercel no los publica como función.
  - No hace falta una función de TMDB: el export ya trae lo necesario.
- **Publicación (hito 8):** el repo va a GitHub, el ingest diario corre en GitHub Actions y commitea el JSON, y Vercel se vuelve a publicar con cada push.
- **Datos personales:** todo lo personal se queda en el navegador:
  - filtros y usuario de Letterboxd → `localStorage`;
  - token de Google → solo en memoria;
  - zip de Letterboxd → se procesa en el navegador.

## Comandos
```
uv sync                                    # dependencias
uv run pytest -q                           # tests
uv run python -m cartelera ingest          # todos los cines con adaptador
uv run python -m cartelera ingest --cine gaumont [--sin-tmdb]   # al final cruza con TMDB si hay TMDB_API_KEY
uv run python -m cartelera enriquecer [--forzar] [--grabar tests/fixtures/tmdb/respuestas.json]
uv run python -m cartelera listar [--cine X] [--dias 10]
uv run python -m cartelera export                      # public/data/cartelera.json (próximos 10 días)
uv run python -m cartelera servir                      # sitio en http://localhost:8765 + /api/letterboxd + tests JS en /pruebas/js/
                                                       # (config "sitio" en .claude/launch.json)
uv run python -m cartelera fixture <cine> [--dias 7]   # guarda lo que publica el cine en tests/fixtures/<cine>/
uv run python -m cartelera extracciones pendientes     # PDFs/notas nuevos que esperan extracción
uv run python -m cartelera extracciones guardar <pendiente.txt> <resultado.json> --por "<quién>"
```
En Windows, si `uv` no aparece en una terminal nueva, hay que refrescar el PATH: `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.

## Esquema de una función (público)
`cine, direccion, fecha_hora, titulo, titulo_original (nullable), ciclo (nullable), url_entradas (nullable), modo_venta (online | boleteria | gratis), es_comercial (bool)`
- `fecha_hora` siempre en hora de Buenos Aires. En la DB va como texto ISO con offset (`2026-11-13T21:30:00-03:00`) y se ordena como texto.
- Los adaptadores devuelven `FuncionCruda` (`cartelera/schema.py`). El ingest completa `cine`, `direccion` y `es_comercial` desde `config/cines.yaml`.
- `director_fuente`, `anio_fuente` y `duracion_fuente` son pistas de la web del cine para cruzar con TMDB. No se muestran como dato verificado.

## Convenciones
- **Registro de cines:** solo en `config/cines.yaml`. Se usan los nombres a mostrar de la lista original y nada se hardcodea en la interfaz. `direccion: null` hasta confirmarla con la fuente oficial (`verificada: true`).
- **Adaptadores:** van en `cartelera/adapters/<id>.py`, exponen `ADAPTADOR` con `fetch(cliente, hoy, dias)` y `parse(crudo, hoy)`, y las dos funciones están separadas:
  - `fetch` solo usa la red y devuelve algo serializable a JSON;
  - `parse` es una función pura y se testea contra el fixture.
- **Antes de escribir un adaptador:**
  - inspeccionar el sitio y elegir el formato: JSON interno antes que HTML, HTML antes que PDF;
  - revisar robots.txt y los términos;
  - documentar todo en `docs/fuentes.md` y contárselo a la usuaria;
  - si el sitio lo prohíbe, consultar antes de seguir.
- **Fixture y tests:** cada cine tiene un fixture real en `tests/fixtures/<id>/` y un test `tests/test_<id>.py` con un "hoy" fijo.
- **Ingest:**
  - es idempotente: reemplaza las funciones futuras de cada cine en una transacción;
  - si un adaptador falla, conserva lo anterior, registra el error y sigue con el resto;
  - 0 funciones cuando antes había → estado `sin_funciones` y no se borra nada.
- **Trasnoche:** una hora antes de las 06:00 se pasa al día siguiente (`tiempo.combinar`), **siempre que la fuente publique el día de la grilla**. Si publica la fecha calendario real, como el catálogo de MALBA, se usa `datetime.combine`. Confirmalo con un caso de medianoche contra otra fuente del mismo cine.
- **Nunca inventar datos.** Si no hay un match confiable (TMDB, LLM), los campos quedan vacíos y marcados.
- **TMDB** (`cartelera/tmdb.py`, `cartelera/enriquecer.py`):
  - Cada función apunta a una fila de `peliculas`. La clave es título + título original + año + director de la fuente.
  - Para aceptar un match, el título normalizado tiene que coincidir con el original, una traducción o un título alternativo. Además tiene que coincidir una de estas:
    - el año (±1, o ±3 si también coincide el director);
    - si la fuente no trae año, el director;
    - si no trae ni año ni director, las tres señales: duración ±5, idioma original y estreno reciente (regla aprobada para el Lorca).
    - Si no, no se acepta.
  - Si las dos duraciones se conocen y difieren en más de 20 minutos, se descarta. Si sobreviven varios candidatos, queda `ambiguo`.
  - **Corroboración entre cines** (`enriquecer.corroborar`, sin pedidos a TMDB): una película `sin_match` o `ambiguo` en un cine se acepta si otro cine ya la confirmó con año o director, con el mismo título, y ese mismo `tmdb_id` fue candidato en su propia búsqueda, descartado por algo que no sea el año ni una diferencia de duración de más de 20 min. Caso de uso: el Lorca (sin año ni director) contra Multiplex (Minotauro, *El sonido al caer*). El motivo queda como `corroborada por otra fuente…`.
  - **Director en alfabeto latino:** si TMDB da el nombre en otro alfabeto (Андрей Звягинцев, 山崎貴), se usa el primer alias latino de `/person/{id}` (`also_known_as`). Si no hay o falla el pedido, queda como vino.
  - Estados posibles: `ok`, `sin_match`, `ambiguo` (con `match_motivo`) o `pendiente`.
  - Las resueltas no se vuelven a consultar. Las `sin_match` y `ambiguo` se reintentan cada 7 días.
  - Los tests reproducen respuestas grabadas sin usar la red. Si cambia el fixture de un cine, hay que volver a grabar con `enriquecer --forzar --grabar`.
  - El link a Letterboxd es `https://letterboxd.com/tmdb/{tmdb_id}/`, que redirige a la película. Lo verifiqué el 2026-11-13.
- **Extracción de textos libres o imágenes (Lugones, Lorca, Museo del Cine)** (`cartelera/extraccion.py`):
  - Se guarda con clave = hash del original (texto o bytes de la imagen), en `data/extracciones/<cine>/<hash>.{txt|jpg,json}`. Ese directorio **sí se commitea**: guarda el original junto al resultado.
  - Un texto nuevo queda en `pendientes/` y el cine conserva sus funciones anteriores.
  - **Con `ANTHROPIC_API_KEY`** (`cartelera/llm.py`):
    - El ingest extrae solo lo pendiente con `claude-opus-5-5`, con structured outputs (`messages.parse(output_format=...)`) y esfuerzo `high`, y después vuelve a leer el cine.
    - Si el modelo se niega, reintenta con `claude-opus-4-8`. Si no se puede, queda pendiente y nunca se inventa.
    - Hay un tope de `CARTELERA_MAX_EXTRACCIONES` por corrida (6 por defecto).
    - A mano: `uv run python -m cartelera extracciones procesar [--cine X]`.
  - **Sin clave:** Claude, en una sesión de Claude Code, lee el `.txt` o la imagen, arma el JSON `ResultadoExtraccion` siguiendo `extraccion.INSTRUCCIONES` y lo guarda con `extracciones guardar ... --por "claude-opus-5-5 (sesion de Claude Code, sin API)"`.
  - **Imágenes que no son grilla** (por ejemplo, una foto de la sala): se guardan con `peliculas: []` para que no queden pendientes.
  - **Validación:** el día de la semana tiene que coincidir con la fecha y la fecha caer dentro del período. Lo que no cumple se descarta y se reporta; nunca se corrige a mano.
  - **Título a mostrar:** en la interfaz va el **título del cine**, no el de TMDB. TMDB suele traer el título de España o de México ("Cayo Largo" en lugar de *Huracán de pasiones*).
- **Comportamiento con los sitios:** pausas entre pedidos y un User-Agent que identifica el proyecto (`adapters/base.py`). Una corrida por día.

## Sitio (`public/`)
- **Datos:** el sitio lee solo `data/cartelera.json`. Cada función trae `fecha`, `hora` y `dia_semana` ya calculados en hora de Buenos Aires, para que el navegador no haga cuentas de zona horaria. `inicio` (ISO) se usa para ocultar lo que ya empezó.
- **Datos sin match:** director, año, duración y Letterboxd salen **solo de TMDB con match `ok`**. Si no hay match, las celdas quedan vacías y se muestra la marca "sin datos de TMDB".
- **Título:** se muestra el del cine, pero **nunca todo en mayúsculas**. Si viene en mayúsculas (o Con Cada Palabra En Mayúscula, como en Multiplex) y TMDB tiene exactamente las mismas palabras, se usa la grafía de TMDB, que trae las tildes. Si no, va en formato título ("Tierra de Mi Padre"). Ver `export.titulo_a_mostrar` y `formato_titulo`.
- **Por película:** tocar el título (en la tabla o en "Para vos") abre un diálogo con todas las funciones que no empezaron de esa película, en todos los cines (comerciales incluidos), agrupadas por día. "Solo con mis filtros" lo limita a lo que muestra la tabla. Se agrupa por `tmdb_id` si las dos funciones lo tienen y, si no, por título normalizado; los datos de TMDB salen de cualquier función del grupo con match.
- **Filtro de horarios:** filtra por hora de inicio.
  - Presets: "Todos", "Después del trabajo" (lun a vie desde las 18) y "Fin de semana" (sáb y dom, todo el día). Además está "Personalizar".
  - Los presets y el personalizado se suman (unión); sin ninguno activo, se muestra todo.
- **Fin estimado:** debajo de la hora de inicio va "termina HH:MM": inicio + `duracion_aprox` (TMDB o el cine), redondeado al cuarto de hora más cercano (`horarios.finEstimado`). Sin duración conocida no se muestra.
- **Puntaje de Letterboxd:** se muestra **solo el tuyo**, de tu RSS o export. El promedio de Letterboxd no se usa: sus términos (6.11) prohíben scrapers, y su robots.txt bloquea a los bots de IA.
- **Logo:** una marquesina de cine en CSS (lamparitas con `mask`), con las fuentes Limelight y Bebas Neue de Google Fonts.
  - Arriba lleva una cresta art déco en SVG, embebida en `index.html` y generada con un script: abanico de rayos de colores, aguja y lamparitas que alternan.
  - El tablero tiene un tubo de neón rosa que parpadea cada tanto, y el cartel de letras negras va sobre paneles iluminados.
  - Abajo hay un alero con dos filas de luces que corren.
  - A los costados, carteles verticales "CINE" y tiras de luces, que se ocultan en celular.
  - Todas las animaciones se apagan si el sistema pide reducir el movimiento.
- **Estética de sala antigua** (`styles.css`):
  - El fondo es una cortina bordó, y los botones de horario y de cines tienen forma de entrada (`.entrada`, con muescas hechas con `mask`) y tipografía Limelight.
  - Los rótulos van en Bebas Neue dorada.
  - La tabla y las tarjetas de "Para vos" llevan la clase `.papel`: blanco con rayas negras y letra oscura. `.papel` redefine las mismas variables de color, así que todo lo de adentro se adapta solo; los colores nuevos van como variables, no fijos en cada regla.
- **Preferencias:** en localStorage, con prefijo `cartelera-ba:`, siempre a través de `js/almacen.js` (con try/catch).
- **Celular:** por debajo de 760 px, la tabla pasa a tarjetas (CSS).
- **Tests de la interfaz:** están en `tests/js/` y corren en el navegador con `cartelera servir`, en http://localhost:8765/pruebas/js/. Todos tienen que pasar; usan datos inventados de `tests/fixtures/letterboxd/`.
- **Google Calendar** (`js/calendario.js`, guía en `docs/google-calendar.md`):
  - Token de GIS solo en memoria y scope `calendar.freebusy`, sobre el calendario `primary`.
  - Sin `GOOGLE_CLIENT_ID` en `public/config.js`, el bloque no aparece.
  - Estados (internos `entra` / `justo` / `no-entra`), que en pantalla dicen "Libre", "Depende" (choca solo con el margen) y "Ocupado".
  - "Solo las que me entran" oculta las que no entran.
  - El fin de la función se calcula con `duracion_aprox`, o 120 min si no se conoce.
- **Letterboxd** (`js/gustos.js`):
  - El RSS se pide por el proxy: `api/letterboxd.mjs` en Vercel y `cartelera/letterboxd.py` en local, con la misma salida.
  - El zip o la carpeta se leen en el navegador: solo los CSV de la raíz, nunca los de `deleted/`, `orphaned/`, etc.
  - El cruce con la cartelera es por `tmdb_id` (RSS) o por título + año ±1 contra los títulos de TMDB en castellano, original e inglés (zip).
  - "Director que te gusta": el export publica la filmografía de cada director en cartelera y el navegador cruza ahí tus puntajes. Nada personal sale del navegador.
  - "Para vos" necesita al menos una señal de gusto (watchlist o director), porque la escasez sola no recomienda. Muestra una función por película, la más temprana.
  - Los pesos están en `config/pesos.json` y se publican en el export.

## Privacidad y secretos
- **Secretos:** en `.env` (`TMDB_API_KEY`, `ANTHROPIC_API_KEY`), que nunca se commitea. `.env.example` muestra las claves.
- **Exportación de Letterboxd:** las carpetas y zips `letterboxd-*` son datos personales. Están en `.gitignore` y nunca se copian a fixtures ni se publican.
- **Usuario de Letterboxd:** el de la autora no va como valor por defecto en ningún lado.
- **Tests de Letterboxd:** usan un fixture chico con datos inventados que respeta las columnas reales (ver el hito 7).

## Hitos
1. Gaumont de punta a punta en consola ✅
2. TMDB ✅
3. Lugones ✅ (y la skill `agregar-cine` en `.claude/skills/`)
4. Resto de la tanda 1: Lorca ✅ · MALBA ✅ (parser sin IA, por decisión de la usuaria: su robots.txt bloquea a los bots de IA) · Cosmos ✅ (2026-11-23; grilla sin fechas, jueves a miércoles: los jueves no se toma)
5. Interfaz con datos reales y filtro de horarios ✅ (`public/`: HTML + módulos JS sin build; `js/horarios.js` tiene la lógica del filtro)
6. Calendario ✅ (OAuth real probado por la usuaria en localhost el 2026-11-23)
7. Letterboxd y "Para vos" ✅ (probado con el RSS y el export reales de la usuaria, sin guardarlos)
8. Publicación ✅ https://mi-cartelera-ba.vercel.app (repo `mindelmaia-byte/mi-cartelera-ba`; guía en `docs/publicar.md`; workflow `.github/workflows/ingest.yml` probado el 2026-11-23; la base `data/cartelera.db` se commitea). **Antes de cambiar algo local: `git pull`**, porque el ingest commitea todos los días.
9. Tandas 4, 2 y 3: Multiplex Lavalle y Belgrano ✅ (un módulo, `adapters/multiplex.py`, y uno chico por complejo). Cinemark Palermo, Abasto y Dot ✅ (JSON con encabezado `country: AR`; la "Z" de la hora es hora local) · Showcase Belgrano ✅ (api.voyalcine.net, una consulta por película) · Cacodelphia ✅ (adro.studio; la "UTC" de la hora es hora local) · York, Munro y Lumiton ✅ (la agenda presencial de lumiton.ar; solo eventos `tipo-cine`). Museo del Cine sin programación vigente el 2026-11-23.

Al final de cada hito se frena para que la usuaria pruebe.
