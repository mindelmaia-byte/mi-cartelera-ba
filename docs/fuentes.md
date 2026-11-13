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

## Cosmos: sin adaptador todavía

- **Revisado:** 2026-11-13
- **Sitio oficial:** https://cosmos.uba.ar (cinecosmos.uba.ar redirige ahí). **Ese día respondía 503 "Sitio en mantenimiento"**, incluido robots.txt.
- **Otras fuentes:** www.uba.ar/cosmos es una página vacía ("seguinos!!!!"). Las demás fuentes que aparecen (La Nación, agregadores, X) no son la web oficial del cine.
- **Pendiente:** reintentar cuando vuelva el sitio. Según búsquedas anteriores, publicaba horarios por día de la semana en `?c=main&a=Detalle&idPelicula=...`.

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
