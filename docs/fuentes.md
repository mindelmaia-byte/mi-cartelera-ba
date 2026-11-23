# Fuentes por cine

Para cada cine: cómo publica la programación, qué dicen robots.txt y los términos, y qué lee el adaptador.
Se completa **antes** de escribir cada adaptador.

## Gaumont: `cartelera/adapters/gaumont.py`

- **Revisado:** 2026-11-13
- **Sitio oficial:** https://www.cinegaumont.ar (venta de entradas en la plataforma Cinexo, de Nexo Soluciones; está hecho con Next.js).
- **Formato:** JSON interno. La página pide la grilla de cada día a
  `https://apifront.cinexo.com.ar/mobile/consultas/peliculas/PeliculasConFuncionesYHorarios?idComplejo=372001&fecha=DD/MM/YYYY`.
  El JSON trae dos listas:
  - `data.datos`: todas las películas del complejo, con código, nombre, duración, director, elenco y fecha de estreno.
  - `data.funciones`: las funciones de ese día, con `codPelicula`, `hora`, `formato`, `subtitulada` y `trasnoche`.
- **Ritmo de publicación:** la grilla es semanal, de jueves a miércoles, y la nueva sale los martes. Los días sin grilla todavía devuelven `funciones: []`. Las preventas aparecen en el día que corresponde.
- **robots.txt:** no existe ni en `www.cinegaumont.ar` ni en `apifront.cinexo.com.ar` (los dos responden 404). Eso significa que no hay restricciones declaradas.
- **Términos y condiciones** (https://www.cinegaumont.ar/terminos-y-condiciones): cubren la privacidad de la app y la compra de entradas. No mencionan acceso automatizado, scraping ni reproducción de contenidos.
- **Uso que hacemos:** 10 pedidos por día (uno por fecha), con una pausa de 0,5 s entre pedidos y un User-Agent que identifica el proyecto como educativo. Guardamos solo título, horario, director, duración y el link a la página de la película. No guardamos imágenes ni sinopsis.
- **Campos:**
  - `modo_venta = online`
  - `url_entradas`: la página de la película (`/es-AR/programacion/{codigo}`), donde se elige la función y se compra.
  - `titulo_original` y `ciclo`: la fuente no los publica, quedan en null.
  - Director y duración se guardan como pistas (`*_fuente`) para el cruce con TMDB.
- **Detalles:**
  - Los títulos vienen casi siempre en mayúsculas y a veces con una coma sin espacio después ("RETRATO,ELOGIO AL DUELO"). Agregamos el espacio y no tocamos nada más.
  - El campo `trasnoche` vino siempre en "0". Por las dudas, cualquier función antes de las 06:00 se pasa al día siguiente (regla general en `tiempo.combinar`).
  - La dirección "Av. Rivadavia 1635" sale del propio JSON (`dataEmpresa.direccion`).

## Sala Lugones: `cartelera/adapters/lugones.py`

- **Revisado:** 2026-11-13
- **Sitio oficial:** https://complejoteatral.gob.ar (WordPress del Complejo Teatral de Buenos Aires).
- **Formato:** HTML para descubrir los ciclos, PDF para la programación.
  - **Descubrimiento:** la página https://complejoteatral.gob.ar/sala/sala-leopoldo-lugones/ tiene una tarjeta por ciclo (`div.col_50`). Cada tarjeta trae la categoría ("cine"), el nombre del ciclo (h2), las fechas y tres links:
    - "Comprar localidades" → entradasba.buenosaires.gob.ar, que es la venta online;
    - "+ info" → la página de la producción;
    - "Descargar programa" → `/programa/<slug>/`, que redirige al PDF del ciclo, en `wp-content/uploads`.
  - **Ciclos sin PDF:** los que todavía no tienen PDF (se publica cerca del inicio) se reportan como aviso.
  - **Contenido del PDF:** cada película tiene su bloque de funciones ("Jueves 12 / A las 21 horas", sin mes) **antes** de la ficha: título, (título original; país; año), "Dirección:" y duración "(93'; DCP)". El mes sale del texto introductorio ("Del jueves 12 al miércoles 25 de noviembre...").
  - **API REST:** existe, pero el tipo `produccion` no está expuesto, así que no hay JSON con las funciones.
- **robots.txt:** solo bloquea `/wp-admin/` y publica un sitemap. La sala y los PDF se pueden leer.
- **Términos:** el sitio no tiene una página de términos de uso, solo un mail de contacto. Es información pública de un organismo de la Ciudad.
- **Uso que hacemos:** un pedido a la página de la sala y uno por PDF vigente (hoy son 4), con 1 s de pausa entre cada uno, una vez por día.
- **Estructuración:**
  - El texto del PDF se estructura con el esquema de `cartelera/extraccion.py` y se valida que el día de la semana coincida con la fecha y que la fecha caiga dentro del período.
  - El texto original y el resultado se guardan en `data/extracciones/lugones/<hash>.{txt,json}`. Si el texto no cambia, no se vuelve a extraer.
  - **Por ahora, sin crédito de API:** la extracción la hace Claude en una sesión de Claude Code. Un PDF nuevo queda en `data/extracciones/lugones/pendientes/` y el ingest lo reporta como aviso.
- **Campos:**
  - `ciclo` = nombre del ciclo (el título del PDF y de la tarjeta). Si el "ciclo" es una sola película con el mismo nombre (un estreno exclusivo), queda en null.
  - `url_entradas` = el link de entradasba de la tarjeta, que es el mismo para todo el ciclo; `modo_venta = online`.
  - `titulo_original`, año, director y duración salen de la ficha del PDF.
- **Dirección:** "Av. Corrientes 1530 (Teatro San Martín)", tomada del texto de los programas.

## Lorca: `cartelera/adapters/lorca.py`

- **Revisado:** 2026-11-13
- **Sitio oficial:** https://cinelorca.wixsite.com/cine-lorca, de "Cine Lorca S.A." (sitio Wix). No hay un dominio propio: probé cinelorca.com.ar, .com y .ar y ninguno existe.
- **Formato:** **una imagen** por semana en la sección "HORARIOS" (`/current-production`).
  - La imagen dice "Programación válida desde el 12/11 al 18/11 2026". Los horarios son los mismos todos los días.
  - De cada película trae sala, duración, calificación e idioma (ING/SUBT, ESP, etc.). **No trae ni director ni año.**
  - La URL de la imagen (`static.wixstatic.com/media/<id>~mv2.jpg`) viene en el HTML del servidor.
- **robots.txt** (cinelorca.wixsite.com): `Allow: /`, salvo `?lightbox=`. No bloquea a bots de IA.
- **Términos:** el sitio no tiene página de términos.
- **Uso que hacemos:** un pedido a la página y uno a la imagen, una vez por día.
- **Estructuración:**
  - Se hace igual que en la Lugones, pero sobre la imagen. La imagen original se guarda en `data/extracciones/lorca/<hash>.jpg`, junto al resultado.
  - La grilla se expande a una función por día del período y por horario.
  - Hoy la extracción la hace Claude en la sesión, leyendo la imagen.
- **Campos:**
  - `modo_venta = boleteria`, porque no hay venta online; la imagen solo lista los precios de boletería.
  - `url_entradas = null`.
  - De las pistas para TMDB solo hay duración.
- **TMDB:** como no hay año ni director, se usa la regla de tres señales que aprobó la usuaria: duración ±5 min, idioma original (el de la grilla, pasado a ISO 639-1) y estreno de los últimos 2 años. Con esa regla cruzaron 4 de 6.
- **Dirección:** "Av. Corrientes 1428", tal como figura en la imagen oficial.

## Cosmos: `cartelera/adapters/cosmos.py`

- **Revisado:** 2026-11-23. El 2026-11-13 el sitio estaba en mantenimiento (503); el 23 ya respondía.
- **Sitio oficial:** https://cosmos.uba.ar (cinecosmos.uba.ar redirige ahí). Es HTML armado en el servidor, sin JSON interno.
- **Formato:** la home tiene una sección "Cartelera" con una tarjeta por película: título, "Dirección: …", "País / NNNm" y un pie con los días y horarios de la semana, por ejemplo `Ju Vi Sá Do Lu Ma Mi | 14:50 - 19:00`.
  - "14:50 - 19:00" son **dos funciones**, no un rango: la página `/hoy` muestra lo mismo como "14:50, 19:00", y la película dura 126 min.
  - La ficha `/pelicula?idPelicula=N` agrega el año, que usamos como pista para TMDB.
- **Fechas:** la grilla **no tiene fechas**. Los días son los de la semana de estrenos, de jueves a miércoles. Por eso:
  - la cartelera de Cosmos cubre desde hoy hasta el miércoles de esa semana y no se extiende más;
  - **los jueves no se toma la grilla**: puede seguir siendo la de la semana que terminó, y atribuirla a la nueva sería inventar. Se registra un aviso y el viernes se lee la nueva;
  - como la fuente publica el día de la grilla, se aplica la regla de trasnoche (`tiempo.combinar`).
  - Si el pie trae algo que no sean días y horas (por ejemplo, "sala 2"), esa película no se carga y queda un aviso, en lugar de adivinar.
- **robots.txt:** no existe (la URL devuelve la home). No hay restricciones declaradas.
- **Términos:** el sitio no tiene página de términos.
- **Uso que hacemos:** 1 pedido a la home y 1 por película para el año (6 a 8 por día), con 1 s de pausa y el User-Agent del proyecto. No guardamos sinopsis ni imágenes.
- **Campos:** `modo_venta = boleteria` (el sitio solo publica los precios de boletería), `url_entradas` null, director, año y duración como pistas para TMDB.

## MALBA: `cartelera/adapters/malba.py` (parser sin IA)

- **Revisado:** 2026-11-13
- **robots.txt de malba.org.ar:** **bloquea explícitamente a bots de IA**: `GPTBot`, `ChatGPT-User`, `ClaudeBot`, `anthropic-ai`, `CCBot`, `Google-Extended`, entre otros, con `Disallow: /`. A `*` solo le bloquea `/wp-admin/`.
- **Decisión de la usuaria (2026-11-13):** parser determinístico, sin IA. Así queda:
  - Nada de MALBA pasa por una extracción con Claude.
  - El ingest lee con el User-Agent del proyecto, que entra en `*`.
  - No se vuelve a inspeccionar malba.org.ar con el navegador del asistente.
- **Fuente 1, las funciones:** el catálogo JSON de la **boletería oficial**, `https://ticketsmalba.liit.ar/api/catalog`. Es la plataforma Liit, enlazada desde cada "Comprar entradas".
  - Los `items` con `vertical == "cine"` traen `title`, `sourceId` (id de película) y `sessions` (`date`, `time`, `sourceId` de la función, `sourceRoom`).
  - **La fecha es la calendario real**: el Bazofi anuncia "VIERNES 13 — 24:00" y el catálogo dice `2026-11-14 00:00`, así que acá **no** se aplica la regla de trasnoche.
  - El catálogo también trae precios y ocupación, que no guardamos.
  - **robots.txt de liit.ar:** es la plantilla de "content signals" de Cloudflare, **sin ninguna señal ni directiva**, o sea que no restringe nada.
- **Fuente 2, las pistas para TMDB:** las páginas `/evento/<slug>/` listadas en https://malba.org.ar/cine/, después del link a la grilla mensual. De cada una se usa:
  - el h1 (título bien escrito);
  - la "Ficha técnica" ("Dirección: …" / "Dirección y guion: …", y "País, AAAA. NN′");
  - el link de compra, cuyo `m=<id>` cruza la ficha con el catálogo. Hay dos boleterías, la nueva `ticketsmalba.liit.ar` y la vieja `malba.liit.com.ar/decidir`.
  - Los festivales y cineclubes (Bazofi, Nocturna) tienen varias películas en una misma página: de su bloque "Programación" ("19:00 / La prisionera / , de Henri-Georges Clouzot") sale el director, y se cruza por título.
- **Uso que hacemos:** 1 pedido al catálogo, 1 a /cine/ y unos 12 a eventos, con 1,5 s de pausa, una vez por día.
- **Campos:**
  - `modo_venta = online` y `url_entradas = https://ticketsmalba.liit.ar/?cine=1&m=<película>&e=<función>`.
  - `ciclo` sale del prefijo del título del catálogo ("nocturna: …" → "Nocturna").
- **Otros datos:** la API REST de WordPress responde 401. Hay un PDF mensual con la grilla, que no se usa.
- **Dirección:** "Av. Figueroa Alcorta 3415", tal como figura en el sitio oficial.

## Multiplex Lavalle y Multiplex Belgrano: `cartelera/adapters/multiplex.py`

- **Revisado:** 2026-11-23
- **Sitio oficial:** https://multiplex.com.ar (WordPress con Elementor y JetEngine). La venta está en ventas.cinemultiplex.com.ar.
- **Formato:** la home trae **toda la programación embebida** en el HTML, sin pedidos extra: cada película es un `<div class='funcion-item' data-funciones='[...]'>` con un JSON de funciones de todos los complejos y de todo el mes:
  `{"complejo": "184", "dia": "11.23.2026", "dia_real": "11.24.2026", "hora": "00:10", "formato": "2D", "idioma": "Subtitulada", "tech_code": "1", "pelicula_id": "240", "id": "228416"}`.
  - Complejos: 184 = Lavalle, 182 = Belgrano (también 180 Canning, 187 Pilar y 190 San Juan, que no son de CABA y se ignoran).
  - Fechas en formato MM.DD.AAAA. `dia` es el día de la grilla y `dia_real` la fecha calendario real (difieren en la trasnoche). Usamos `dia_real` con `datetime.combine`, **sin** correr la fecha.
  - La API REST de WordPress (`/wp-json/wp/v2/peliculas`) existe pero no trae horarios.
- **Ficha de cada película** (`/peliculas/<slug>/`): duración en minutos y fecha de estreno en la Argentina. Las usamos como pistas para TMDB (el año de estreno como `anio_fuente`).
- **robots.txt** (multiplex.com.ar): `User-agent: * / Disallow:` (todo permitido, bloque de Yoast). En ventas.cinemultiplex.com.ar solo trae el texto de las *content signals* de Cloudflare, sin ninguna señal definida ni `Disallow`.
- **Términos y condiciones** (https://multiplex.com.ar/terminos-y-condiciones/): tratan la compra de entradas. No mencionan robots, scraping ni acceso automatizado.
- **Uso que hacemos:** por complejo, 1 pedido a la home y 1 por película con funciones (unos 15), con 1 s de pausa y el User-Agent del proyecto. Guardamos título, horario, duración, estreno y el link de compra. No guardamos sinopsis ni imágenes.
- **Campos:**
  - `modo_venta = online`
  - `url_entradas`: el link de compra de esa función, armado igual que en el JS de la home: `https://ventas.cinemultiplex.com.ar/funcion?df={complejo}-{pelicula}-{funcion}-{AAAAMMDD}-{tech}`.
  - `titulo_original`, `ciclo` y director: la fuente no los publica.
  - Formato (2D, 3D, 4D, Comfort Plus) e idioma (subtitulada o castellano) vienen por función, pero el esquema no tiene dónde ponerlos y no se muestran.
- **Detalles:** los títulos vienen Con Cada Palabra En Mayúscula ("Tierra De Mi Padre"). El export los trata como los títulos en mayúsculas: grafía de TMDB si tiene las mismas palabras y, si no, formato título.

## Museo del Cine: sin adaptador todavía

- **Revisado:** 2026-11-23
- **Fuente:** las noticias de https://buenosaires.gob.ar/gcaba_historico/cultura/museos/museodelcine. La más reciente era "Octubre en nuestro auditorio" (del 1 al 15 de octubre, publicada el 22/10). No había programación vigente para noviembre, así que un adaptador hoy devolvería 0 funciones.
- **Pendiente:** cuando publiquen la próxima quincena, sumarlo con la estrategia de extracción (como Lugones), `modo_venta = gratis`.


## York, Munro y Lumiton: `cartelera/adapters/agenda_vicente_lopez.py`

- **Revisado:** 2026-11-23
- **Sitio oficial:** https://lumiton.ar (Municipio de Vicente López, WordPress). La **agenda presencial** (https://lumiton.ar/agenda-presencial/) reúne las tres salas: Cine York (Juan Bautista Alberdi 895, Olivos), Centro Cultural Munro (Vélez Sarsfield 4650, Munro) y Lumiton (Sargento Cabral 2354, Munro). Las direcciones salen de las fichas de los eventos y del pie del sitio.
- **Formato:** HTML. Cada evento es un `<article>` con `data-date="AAAA-MM-DD"`, `data-locations='["cine-york"]'`, la hora ("20:30hs"), el título, el link a la ficha y clases de tipo (`tipo-proyecciones`, `tipo-cine`). La agenda tiene una sola página (la `/page/2/` repite lo mismo) y cada evento es una sola función.
  - **Solo se toman los eventos con `tipo-cine`.** Las charlas, talleres y visitas guiadas no llevan ese tipo. El 2026-11-23, lo único de Lumiton era una charla, así que esa sala quedó con 0 funciones.
  - `data-date` es la fecha del evento, la misma que muestra la ficha. No hay funciones de trasnoche, así que se usa `datetime.combine`.
- **API REST:** `/wp-json/wp/v2/evento?include=<ids>` trae los campos ACF `director`, `ano` y `duracion`, que usamos como pistas para TMDB. No trae fecha ni hora. Solo se usan si tienen el formato esperado: "87 min" y "1969" sí; "duración total aprox. 110 min" y "2022 - 2026" (programas de cortos) no.
- **robots.txt:** responde 200 vacío. No hay restricciones declaradas.
- **Términos:** no hay página de términos. El pie solo pide no filmar ni fotografiar lo que se proyecta.
- **Uso que hacemos:** por sala, 1 pedido a la agenda y 1 a la API, con 1 s de pausa y el User-Agent del proyecto.
- **Campos:** `modo_venta = gratis` ("Entrada no arancelada. Acceso por orden de llegada"), `url_entradas` null y `fuente_url` = la ficha del evento. El formato de proyección que viene pegado al título ("… EN 35 MM") pasa a `ciclo` ("En 35 mm").
- **TMDB el 2026-11-23:** 9 ok y 4 sin match: dos programas de cortos, *Algo ha cambiado…* (no está en TMDB con ese título) y *Subí que te llevo* (la agenda dice 1990 y la película de Cavallotti es de 1980; la regla no acepta esa diferencia).

## Cinemark Palermo, Abasto y Dot: `cartelera/adapters/cinemark.py`

- **Revisado:** 2026-11-23
- **Sitio oficial:** https://www.cinemark.com.ar (Next.js). Cada complejo (`/cartelera/palermo`) pide los datos a un JSON interno en `bff.cinemark.com.ar`:
  - `GET /api/cinema/showtimes?theater=733`: las funciones (`movieName`, `corporateId`, `language`, `sessionFormat`, `sessionDateTime`, `sessionDisplayDate`, `isLateNightSession`).
  - `GET /api/cinema/movies?theater=733`: las películas (`title` completo, `slug`, `runTime`, `openingDate`).
  - `GET /api/cinema/theaters`: los complejos. 733 = Palermo (Beruti 3399), 103 = Abasto (Agüero 665, Abasto Shopping), 111 = DOT (Vedia 3626, Shopping DOT). Las direcciones salen de ahí.
  - **Hace falta el encabezado `country: AR`**, como lo manda el sitio. Sin él, responde 500 "Country undefined not implemented".
- **Hora:** `sessionDateTime` trae una "Z" (UTC), pero es la hora **local**: la página muestra 16:35 para `16:35:00.000Z`. Además ya es la fecha calendario real: la trasnoche del 15/12 a las 00:00 figura como `2026-12-16T00:00` con `sessionDisplayDate` 2026-12-15. Se toma tal cual, sin convertir ni correr la fecha.
- **Títulos:** `movieName` puede venir cortado ("LOS JUEGOS DEL HAMBRE: AMANECER"). El título completo sale de `/movies`, por `corporateId`.
- **robots.txt** (www.cinemark.com.ar): `User-Agent: * / Allow: /`. bff.cinemark.com.ar no tiene (502).
- **Términos** (https://www.cinemark.com.ar/terminos-condiciones): tratan compras, Cinemark Club y bases de sorteos. No mencionan acceso automatizado ni scraping.
- **Uso que hacemos:** 2 pedidos por complejo y por día (6 en total), con 1 s de pausa y el User-Agent del proyecto. El fixture guarda solo la ventana de días pedida.
- **Campos:** `modo_venta = online`. `url_entradas` = la página de la película (`/pelicula/{slug}`): los horarios del sitio no son links, la compra es un flujo interactivo. El año de estreno y la duración van como pistas para TMDB.
- **No incluidos:** Cinemark Caballito y Puerto Madero también son de CABA, pero no están en la lista original.

## Showcase Belgrano: `cartelera/adapters/showcase.py`

- **Revisado:** 2026-11-23
- **Sitio oficial:** https://www.todoshowcase.com (institucional). La boletería es https://entradas.todoshowcase.com (plataforma Voy al Cine). Dirección: Monroe 1655, de la página del complejo.
- **Formato:** no hay listado por complejo.
  1. La home enlaza cada película como `entradas.todoshowcase.com/showcase/pelicula?filmid=N` (unas 30).
  2. Por película, un JSON: `https://api.voyalcine.net/films/{filmid}/tree/showcase` → `days` → complejos (`id`, `name`, `ewaveId`) → formatos → `performances` (`showTime`). Belgrano es `id` 14.
  3. La ficha HTML de la boletería trae título original, director y duración (`<li><strong>Director:</strong> …`). Solo se pide para las películas que dan en Belgrano.
- **Ritmo:** el 2026-11-23, Belgrano tenía funciones hasta el miércoles 25 (grilla semanal).
- **Trasnoche:** ese día no había funciones antes de las 06:00, así que no se pudo confirmar si `days` es el día de la grilla o la fecha real. Se aplica la regla general (`tiempo.combinar`). **Revisarlo cuando aparezca un caso.**
- **robots.txt:** no existe en ninguno de los tres hosts (www.todoshowcase.com devuelve la home; entradas.todoshowcase.com y api.voyalcine.net, 404).
- **Términos:** el sitio solo tiene una declaración de privacidad (`/site/privacidad`), que no habla de acceso automatizado.
- **Uso que hacemos:** 1 pedido a la home, 1 por película (unos 30) y 1 ficha por película con funciones en Belgrano (unas 13), con 0,5 s de pausa.
- **Campos:** `modo_venta = online`, `url_entradas` = la ficha de la boletería con `house_id` del complejo. `titulo_original` solo si es distinto del título (normalizado). Director y duración como pistas para TMDB; no publica el año.

## Cacodelphia: sin adaptador

- **Revisado:** 2026-11-23
- **No tiene web oficial con la programación.** cacodelphia.com es la productora Cacodelphia Studios (sin cartelera), y los dominios del cine que probamos no existen. La programación sale en Instagram (@cinearte.cacodelphia) y en agregadores de terceros (IMDb, Locate Cinemas).
- Instagram no permite la lectura automática y la regla del proyecto es no usar agregadores, así que queda pendiente hasta que publique en una web propia.
