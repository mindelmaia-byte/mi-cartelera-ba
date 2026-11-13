---
name: agregar-cine
description: Agrega un cine nuevo a la cartelera, de punta a punta. Inspecciona cómo publica la programación, revisa robots.txt y términos y se los reporta a la usuaria; después escribe el adaptador, el fixture y el test, completa el registro, documenta la fuente y corre el ingest real. Usala siempre que haya que sumar o rehacer un cine (por ejemplo "agregá Cosmos", "seguimos con la tanda 2" o "el adaptador de MALBA se rompió"). También sirve para procesar un PDF o una nota pendiente de extracción.
---

# Agregar un cine

Hecha a partir de Gaumont (JSON interno) y la Sala Lugones (HTML + PDF + extracción estructurada).
Antes de empezar, leé `CLAUDE.md` (esquema, comandos y convenciones). Cada paso se hace en orden y con un cine por vez.

## 1. Inspeccionar el sitio, sin escribir código todavía

Usá el navegador integrado (`mcp__Claude_Browser__*`) sobre la web **oficial** del cine.

1. **Encontrar dónde está la programación.** Puede estar en la home, en "programación", en "cartelera" o en la página de una sala. Si el cine depende de otro organismo (INCAA, CTBA, GCBA, una universidad), la fuente oficial puede ser el sitio de ese organismo.
2. **Buscar un JSON interno**, que es lo preferido. Recargá la página y listá lo que pidió:
   ```js
   performance.getEntriesByType('resource').filter(e => ['fetch','xmlhttprequest'].includes(e.initiatorType)).map(e => e.name)
   ```
   - `read_network_requests` no siempre muestra los fetch del cliente; el comando de arriba sí.
   - Si aparece una API, probala **fuera del navegador** con PowerShell o httpx. Fijate si necesita encabezados y si hay un parámetro por fecha, como en Gaumont: `PeliculasConFuncionesYHorarios?idComplejo=...&fecha=DD/MM/YYYY`.
   - Si el sitio es WordPress, mirá `/wp-json/wp/v2/types` (la Lugones no exponía las producciones) y `/wp-json/wp/v2/media?mime_type=application/pdf`.
   - Si es Next.js, los datos pueden estar en `self.__next_f` o venir de una API aparte.
3. **Si no hay JSON:** HTML estable (con selectores concretos) antes que PDF. Si hay un PDF o un texto libre con fechas incompletas, usá la extracción estructurada (paso 4b).
   - **Grilla publicada como imagen** (Lorca): usá la extracción estructurada sobre la imagen, con `extraccion.cargar(cine, bytes)` y `guardar_pendiente(..., ext=".jpg")`. En el fixture, la imagen va en base64. Ver `adapters/lorca.py`.
   - Si la imagen o el texto no traen ni año ni director, avisale a la usuaria que TMDB no va a poder confirmar ningún match.
4. **robots.txt:** pedilo en cada host que vas a leer, incluido el host de la API. Un 404 significa que no hay restricciones declaradas.
   - **Fijate si bloquea a bots de IA**: `ClaudeBot`, `anthropic-ai`, `GPTBot`, etc. MALBA lo hace. En ese caso, aunque `*` esté permitido, **no sigas accediendo al sitio y consultá** a la usuaria.
   - Si el sitio oficial está caído (Cosmos devolvía 503 por mantenimiento), no lo reemplaces por un agregador de terceros. Documentalo en `docs/fuentes.md` y dejalo pendiente.
5. **Términos:** buscá "términos", "legal" o "condiciones" en el footer y leé lo que diga sobre acceso automático, scraping o reproducción.
6. **Dirección:** confirmala con la fuente oficial (`verificada: true` en el registro).
7. **Reportarle a la usuaria antes de escribir el adaptador:** cómo publica (formato y URL), qué dicen robots.txt y los términos, cuántos pedidos por día vamos a hacer y qué campos se pueden llenar. **Si robots.txt o los términos lo prohíben, frená y consultá.**

## 2. Registro y documentación

- En `config/cines.yaml`: `adaptador: <id>`, más la dirección y `verificada: true`. El nombre a mostrar no se toca.
- En `docs/fuentes.md`: una sección nueva con el mismo formato que las existentes (fecha de revisión, sitio, formato, robots, términos, uso que hacemos, campos y detalles).

## 3. Adaptador `cartelera/adapters/<id>.py`

Tomá como modelo `gaumont.py` si hay JSON, o `lugones.py` si hay HTML + PDF o texto libre.

- La clase tiene `fetch(cliente, hoy, dias)` y `parse(crudo, hoy)`, y al final del módulo va `ADAPTADOR = Clase()`.
- `fetch` solo usa la red y devuelve algo **serializable a JSON**. Ese resultado es el fixture, así que incluí también el HTML que se usa para descubrir (como `html_sala` en la Lugones). Poné `PAUSA_SEGUNDOS` entre pedidos y usá el cliente que recibís, que ya trae el User-Agent del proyecto.
- `parse` es una función pura y devuelve `list[FuncionCruda]`:
  - `fecha_hora` con zona horaria, usando `tiempo.combinar(dia, hora)`. Una hora antes de las 06:00 pasa al día siguiente.
    - **Verificá qué significa la fecha de una función de medianoche.** El catálogo de MALBA pone "Viernes 13 a las 24:00" como `14/11 00:00`, que ya es la fecha real; ahí se usa `datetime.combine` y no `combinar`.
    - Buscá un caso de medianoche y comparalo con otra publicación del mismo cine.
  - Si la boletería es otra plataforma, como Cinexo o Liit, buscá su JSON. Suele ser mejor fuente que la página del cine.
  - Si el catálogo no trae director ni año, sacalos de la ficha de cada película (MALBA) y cruzalos por un id estable (`m=` del link de compra), no solo por el título.
  - `modo_venta`: `online` si hay link de compra, `boleteria` si solo se vende en el lugar, `gratis` si es con entrada libre.
  - `url_entradas`: la página donde se compra. Si no existe, null.
  - `fuente_url`: de dónde salió el dato.
  - Las pistas para TMDB van en `director_fuente`, `anio_fuente` y `duracion_fuente`. Son muy valiosas: sin año ni director, TMDB no acepta el match.
  - Limpiá solo lo obvio: espacios, o una coma sin espacio como en Gaumont. **No inventes campos.**
- Los problemas parciales que no invalidan el cine (un ciclo sin programa, un PDF pendiente) van a `self.avisos` (se reinicia en cada `parse`), y el ingest los muestra. Si el sitio cambió y no hay nada que leer, levantá una excepción.
- En la tanda 3 (funciones ocasionales) hay que filtrar en `parse` qué es una proyección y qué no (charlas, talleres) y dejar escrito el criterio.

## 4a. Fixture y test

```bash
uv run python -m cartelera fixture <id> --dias 7
```
- Guarda `tests/fixtures/<id>/crudo-<fecha>.json`. Revisá que **no tenga datos personales ni claves**.
- Escribí `tests/test_<id>.py` con un `HOY` fijo, igual a la fecha del fixture. Como mínimo tiene que cubrir:
  - la cantidad por día o el total;
  - una función concreta con todos sus campos, incluido el offset -03:00;
  - el `modo_venta` y la `url_entradas`;
  - un caso borde del formato (trasnoche, película sin datos, ciclo).
- Corré `uv run pytest -q`.

## 4b. Si hay texto libre (PDF o nota): extracción estructurada

- En `parse`, llamá a `extraccion.cargar(cine, texto)`. Si devuelve `None`, llamá a `extraccion.guardar_pendiente(...)` y sumá un aviso.
- Para procesar los pendientes (hoy sin API, lo hace Claude en la sesión):
  1. `uv run python -m cartelera extracciones pendientes`
  2. Leé **todo** el `.txt`, o la imagen con Read, y armá el JSON `ResultadoExtraccion` siguiendo `extraccion.INSTRUCCIONES`. Si la grilla es semanal con los mismos horarios todos los días, conviene generar el JSON con un script chico en el scratchpad (ver el caso del Lorca):
     - el día de la semana tal como aparece en el texto;
     - la fecha completa, con el mes deducido de la introducción;
     - "A las 15 y 21 horas" son dos funciones;
     - lo que no está en el texto va en null.
  3. Dejá el JSON en el scratchpad y guardalo con:
     ```bash
     uv run python -m cartelera extracciones guardar data/extracciones/<id>/pendientes/<hash>.txt <json> --por "claude-opus-5-5 (sesion de Claude Code, sin API)"
     ```
  4. El comando valida el día de la semana y el período, y reporta lo que descarta. **Si descarta algo, releé el texto: el error suele estar en la extracción.** Si el texto mismo está mal (el día no coincide con la fecha), dejalo descartado y contáselo a la usuaria.
- Los `data/extracciones/<id>/*.{txt,json}` se commitean. Los tests usan esas extracciones (ver `tests/test_lugones.py`).

## 5. Ingest real y TMDB

```bash
uv run python -m cartelera ingest --cine <id>
```
```bash
uv run python -m cartelera listar --cine <id>
```
- Revisá los avisos, la cantidad de funciones y que las fechas tengan sentido.
- Revisá cada película con `match_estado != 'ok'`:
  - Buscá a mano en TMDB y confirmá si es un negativo real.
  - Si es un falso negativo, mejorá la regla en `cartelera/tmdb.py` **sin aflojar** la exigencia de título + año/director, y agregá un test.
  - Revisá también los `ok` sospechosos, como un año muy distinto o un director que no corresponde.
- Si cambió el fixture o la regla, volvé a grabar las respuestas de TMDB:
  1. `uv run python -m cartelera ingest --dias 12 --sin-tmdb`
  2. Borrá `tests/fixtures/tmdb/respuestas.json`.
  3. `uv run python -m cartelera enriquecer --forzar --grabar tests/fixtures/tmdb/respuestas.json`
  4. `uv run pytest -q`

## 6. Cierre

- Corré `uv run pytest -q` y verificá que pase todo.
- Si aprendiste algo nuevo sobre el proceso, actualizá esta skill o CLAUDE.md.
- Reportale a la usuaria cómo publica el cine, qué dicen robots.txt y los términos, cuántas funciones y películas hay, el cruce con TMDB (cuántas ok y cuáles sin match y por qué) y los avisos. Frená si es el final de un hito.
