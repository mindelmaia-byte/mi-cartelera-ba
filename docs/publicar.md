# Publicar Mi Cartelera BA (GitHub + Vercel)

**Cómo queda armado:**
- **El código** vive en GitHub.
- **Todos los días a las 06:00** (hora de Buenos Aires), GitHub Actions corre el ingest, actualiza `public/data/cartelera.json` y hace un commit.
- **Vercel** detecta el commit y vuelve a publicar el sitio solo.

Todo es gratis.

## 1. Crear el repo en GitHub

1. Entrá a https://github.com (o creá una cuenta) → **+** arriba a la derecha → **New repository**.
2. **Repository name:** `mi-cartelera-ba`.
3. **Público o privado:** las dos opciones funcionan con Vercel y Actions.
   - Si es privado y querés que tu profesora vea el código: **Settings → Collaborators → Add people**.
   - En ningún caso se suben tus datos personales: `.env` y tu export de Letterboxd están en `.gitignore`.
4. **No** marques "Add a README", ".gitignore" ni "license": el repo tiene que nacer vacío.
5. **Create repository**. Copiá la URL que aparece, del tipo `https://github.com/TU-USUARIO/mi-cartelera-ba.git`.

## 2. Subir el código

En la terminal de la app, dentro de la carpeta del proyecto, con la URL del paso anterior:

```bash
git remote add origin https://github.com/TU-USUARIO/mi-cartelera-ba.git
```
```bash
git branch -M main
```
```bash
git push -u origin main
```

La primera vez se abre una ventana para iniciar sesión en GitHub (Git Credential Manager). Iniciá sesión y autorizá. Cuando termine, recargá la página del repo y vas a ver los archivos.

## 3. Cargar la clave de TMDB en GitHub

1. En el repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. **Name:** `TMDB_API_KEY`. **Secret:** la misma clave que tenés en `.env`. **Add secret**.
3. *(Opcional, cuando la tengas)* otro secret `ANTHROPIC_API_KEY`, para que los PDF y las imágenes nuevas se extraigan solos.

## 4. Probar el ingest automático

1. En el repo → pestaña **Actions**. Si pregunta, tocá **I understand my workflows, go ahead and enable them**.
2. Elegí **Ingest diario** → **Run workflow** → **Run workflow**.
3. Tarda unos 2 minutos. Tiene que terminar en verde y dejar un commit "Ingest diario AAAA-MM-DD". Si un cine falla, aparece un aviso amarillo, pero no corta el resto.

## 5. Publicar en Vercel

1. Entrá a https://vercel.com → **Sign Up** → **Continue with GitHub**. El plan es **Hobby**, que es gratis.
2. **Add New… → Project** → buscá `mi-cartelera-ba` → **Import**. Si no aparece, tocá **Adjust GitHub App Permissions** y dale acceso a ese repo.
3. En la configuración:
   - **Framework Preset:** **Other**.
   - **Root Directory:** `./`, sin cambios.
   - **Build and Output Settings:** no toques nada, porque `vercel.json` ya indica que se publica la carpeta `public/`.
   - **Environment Variables:** ninguna. El proxy de Letterboxd no necesita claves.
4. **Deploy**. En un minuto te da una URL del tipo `https://mi-cartelera-ba.vercel.app`.
   - Para ver la dirección **principal** (la de producción): **Settings → Domains**.
   - Las URLs largas con letras y números son las de *preview*: ahí Google Calendar no va a andar.

## 6. Autorizar la URL en Google

1. https://console.cloud.google.com → proyecto **Mi Cartelera BA** → **Google Auth Platform → Clientes** → `Mi Cartelera BA web`.
2. En **Orígenes autorizados de JavaScript** → **Agregar URI** → la URL principal de Vercel, por ejemplo `https://mi-cartelera-ba.vercel.app`, sin barra al final.
3. **Guardar**. El cambio puede tardar unos minutos en aplicarse.
4. Revisá que tu profesora esté en **Público → Usuarios de prueba**.

## 7. Probar

- **Cartelera:** abrí la URL de Vercel. Tiene que cargar sin conectar nada.
- **Letterboxd:** cargá un usuario. Prueba el proxy `api/letterboxd` en Vercel.
- **Calendar:** conectalo con tu cuenta y después con otra que esté en Usuarios de prueba (la de tu profesora).
- **Celular:** abrí la URL también desde el teléfono.

## Después de publicar

- **Antes de cambiar algo en tu compu**, traé lo que commiteó el ingest:
  ```bash
  git pull
  ```
- **Lorca y Lugones sin `ANTHROPIC_API_KEY`:** lo nuevo queda en `data/extracciones/*/pendientes/`. Hacé `git pull` y pedile a Claude Code que procese las extracciones pendientes (está en la skill `agregar-cine`). Después, `git push`.
