# Configurar Google Calendar (modo testing)

La cartelera funciona completa sin esto. Esta guía sirve para mostrar, en cada función, si "entra" en tu agenda.

**Cómo funciona:**
- La app pide un **token en el navegador**, con Google Identity Services, y usa solo el scope `https://www.googleapis.com/auth/calendar.freebusy` ("Ver tu disponibilidad en tus calendarios"). Lo verifiqué contra la documentación de `freebusy.query` el 2026-11-13; es el más chico de los cuatro que acepta.
- Solo consulta el **calendario principal** y solo recibe bloques ocupados (inicio y fin), sin títulos ni detalles.
- No usa refresh tokens. El token vive en la memoria de la pestaña y vence a la hora. No pasa nada por ningún servidor propio.

Necesitás una cuenta de Google. Lleva unos 10 minutos.

## 1. Crear el proyecto

1. Entrá a https://console.cloud.google.com/ con tu cuenta.
2. En el selector de proyectos (arriba a la izquierda), elegí **Proyecto nuevo**.
3. Nombre: `Mi Cartelera BA`. **Crear**, y asegurate de que quede seleccionado.

## 2. Activar la API de Google Calendar

1. Menú ☰ → **APIs y servicios** → **Biblioteca**.
2. Buscá **Google Calendar API**, abrila y tocá **Habilitar**.

## 3. Pantalla de consentimiento (Google Auth Platform)

1. Menú ☰ → **APIs y servicios** → **Pantalla de consentimiento de OAuth**. En consolas nuevas se llama **Google Auth Platform**. Tocá **Comenzar**.
2. **Información de la app:** nombre `Mi Cartelera BA` y tu mail como correo de asistencia.
3. **Público:** elegí **Externo**.
4. **Información de contacto:** tu mail.
5. Aceptá la política de datos de usuario de Google y tocá **Crear**.

La app queda en estado **Prueba** (testing). Así tiene que quedar: no hace falta publicarla ni pasar la verificación de Google.

## 4. Declarar el scope

1. En Google Auth Platform → **Acceso a los datos** → **Agregar o quitar permisos**.
2. Abajo, en "Agregar permisos manualmente", pegá:
   ```
   https://www.googleapis.com/auth/calendar.freebusy
   ```
3. **Agregar a la tabla** → **Actualizar** → **Guardar**.

## 5. Agregar usuarios de prueba

En modo prueba, **solo pueden conectar su calendario las cuentas que agregues acá**. Cualquier otra recibe `access_denied`, aunque la cartelera le funcione igual.

1. Google Auth Platform → **Público** → **Usuarios de prueba** → **Agregar usuarios**.
2. Agregá tu mail, el de tu profesora y los de las personas que lo van a probar (máximo 100).
3. **Guardar**.

## 6. Crear el ID de cliente

1. Google Auth Platform → **Clientes** → **Crear cliente**.
2. Tipo de aplicación: **Aplicación web**. Nombre: `Mi Cartelera BA web`.
3. **Orígenes autorizados de JavaScript:** agregá
   - `http://localhost:8765`, para probar en tu compu;
   - más adelante, la URL pública, por ejemplo `https://cartelera-ba.pages.dev` (hito 8).
4. **URIs de redireccionamiento autorizados:** dejalo vacío, porque el flujo de token no los usa.
5. **Crear**. Copiá el **ID de cliente**, que termina en `.apps.googleusercontent.com`.

El ID de cliente **no es secreto**: va en el código del sitio. El "secreto del cliente" no se usa; no lo copies a ningún lado.

## 7. Ponerlo en la app

En `public/config.js`:
```js
export const GOOGLE_CLIENT_ID = "1234567890-abc...apps.googleusercontent.com";
```

## 8. Probar

1. Levantá el sitio:
   ```bash
   uv run python -m http.server 8765 --directory public
   ```
2. Abrí http://localhost:8765 y tocá **Conectar Google Calendar**.
3. Google va a mostrar **"Google no verificó esta app"**. Es normal en modo prueba: tocá **Continuar**.
4. Aceptá el permiso "Ver tu disponibilidad en tus calendarios".
5. Aparece "Google Calendar conectado", y en la tabla, la columna **Calendario** con "entra", "justo" o "no entra", más el bloque ocupado que molesta.

**Qué significa cada estado:**
- **entra:** no se superpone con nada, contando los márgenes de traslado (por defecto 30 min antes y 15 después; se cambian ahí mismo).
- **justo:** la película no se superpone con nada, pero el margen de traslado sí.
- **no entra:** la película se superpone con un bloque ocupado.
- **"Solo las que me entran":** oculta las que no entran y deja las justas.
- Si no conocemos la duración de la película, se supone de 120 min y se aclara al pasar el mouse.

**"+ agendar"** abre Google Calendar con la función ya cargada: título, cine, dirección y horario. No usa permisos de escritura; el evento lo guardás vos.

**Desconectar** revoca el token y borra de la memoria los bloques ocupados. El token también vence solo, a la hora; para volver a cargar la disponibilidad, se conecta de nuevo.

## Problemas comunes

- **`access_denied` / "La app está en prueba":** esa cuenta no está en Usuarios de prueba (paso 5).
- **`redirect_uri_mismatch` o `origin_mismatch`:** el origen exacto (protocolo, host y puerto) no está en "Orígenes autorizados" (paso 6). `http://localhost:8765` y `http://127.0.0.1:8765` son orígenes distintos.
- **El popup no aparece:** el navegador lo bloqueó. Permití popups para el sitio.
- **No aparece el botón:** `GOOGLE_CLIENT_ID` está vacío en `public/config.js`.
