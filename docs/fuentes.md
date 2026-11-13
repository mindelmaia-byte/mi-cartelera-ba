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
