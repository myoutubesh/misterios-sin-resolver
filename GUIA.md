# Misterios Sin Resolver: guía de configuración y mantenimiento

Esta guía es para hacer **una sola vez** (de 60 a 90 minutos). Después el sistema trabaja solo en la nube: investiga, escribe, narra, edita y publica sin que tengas Claude abierto ni la PC encendida.

> Antes de empezar, lee [ARQUITECTURA.md](ARQUITECTURA.md): ahí están las herramientas, los costos y las limitaciones.

## Qué hace cada día

| Cuándo (hora CDMX) | Qué pasa |
|---|---|
| 5:00 | Actualiza estadísticas, aprende qué funciona y refresca el panel |
| 8:00 y 17:00 | Crea y publica (o programa) un short |
| Martes y viernes 10:00 | Crea y publica (o programa) un video largo de unos 10 minutos con miniatura |
| Si algo falla | Reintenta una vez. Si vuelve a fallar, GitHub te manda un correo y el error aparece en el panel |

---

## Paso 1. Canal de YouTube (10 min)

1. youtube.com → tu foto → **Crear un canal**. Mejor un **canal de marca** (*Configuración → Agregar o administrar canales → Crear canal*).
2. Nombre: **Misterios Sin Resolver**.
3. **Verifica el canal con tu teléfono** en youtube.com/verify. Sin esto YouTube no deja poner miniaturas personalizadas.
4. Opcional: foto de perfil y banner (puedes hacerlos gratis en Canva).

## Paso 2. La IA que escribe los guiones (5 min). Elige UNA opción

El sistema **no publica** guiones escritos solo con el respaldo gratuito (Pollinations), porque en las pruebas inventó datos. Necesitas al menos una de estas dos claves:

**Opción A: Claude API (recomendada: mejor calidad y verificación con búsqueda web)**
1. Entra a **console.anthropic.com** y crea una cuenta.
2. *Settings → Billing*: agrega saldo (por ejemplo $10). En *Limits* pon un **límite de gasto mensual** para no llevarte sorpresas.
3. *Settings → API Keys → Create Key*. Copia la clave (empieza con `sk-ant-`). Solo se muestra una vez.
4. Modelo: por defecto se usa `claude-opus-5-5` (la mejor calidad, unos $28 al mes). Para gastar menos, crea la variable `CLAUDE_MODELO` en el Paso 7 con `claude-sonnet-5-5` (unos $15 al mes) o `claude-haiku-5-5` (unos $3 al mes).

**Opción B: Gemini (gratis, con límites)**
1. Entra a **aistudio.google.com/apikey** → *Create API key*.
2. Ten en cuenta que el plan gratis tiene pocos pedidos al día (revisa tu límite en AI Studio) y que Google puede usar esos datos para mejorar sus productos.

Puedes poner las dos: el sistema usa Claude primero y Gemini si Claude falla.

## Paso 3. Clips de video reales: Pexels (3 min, gratis)

1. Crea una cuenta en **pexels.com** → entra a **pexels.com/api** → *Your API Key*.
2. Copia la clave. Con ella, los videos mezclan imágenes IA con clips reales de archivo, así se ven menos "hechos en serie" y se generan mucho más rápido.

## Paso 4. Imágenes más rápidas: Pollinations (opcional, 3 min, gratis)

Sin cuenta, Pollinations da 1 imagen cada 45 segundos. Con registro gratis (nivel *Seed*) la espera baja mucho:
**enter.pollinations.ai** → regístrate → copia tu token.

## Paso 5. Permiso para publicar en tu canal (20 min)

1. Entra a **console.cloud.google.com** → arriba, **Crear proyecto** → nombre "misterios-sin-resolver".
2. Menú ☰ → **APIs y servicios → Biblioteca**. Busca y **habilita** estas dos:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
3. **APIs y servicios → Pantalla de consentimiento de OAuth** (puede llamarse "Google Auth Platform"):
   - Tipo: **Externo**. Nombre de la app: "Misterios bot". Correo de asistencia: el tuyo.
   - En **Público** agrega tu correo como usuario de prueba.
   - Pulsa **Publicar app** para dejarla **En producción**. ⚠️ Si se queda "En prueba", el permiso caduca cada 7 días y la subida deja de funcionar. No hace falta verificar la app.
4. **Credenciales → Crear credenciales → ID de cliente de OAuth → App de escritorio** → **Descargar JSON**.
5. Cambia el nombre del archivo a `client_secret.json` y ponlo en la carpeta `misterios-shorts`.
6. Abre una terminal en la carpeta `misterios-shorts` y ejecuta:
   ```
   .venv\Scripts\python obtener_token.py
   ```
   *(En otra PC, antes crea el entorno: `python -m venv .venv` y luego `.venv\Scripts\pip install -r requirements.txt`.)*
7. Se abre el navegador. Elige **la cuenta del canal**. Si sale "Google no verificó esta app", pulsa *Configuración avanzada → Ir a Misterios bot* y acepta los 3 permisos.
8. La terminal muestra `YT_CLIENT_ID`, `YT_CLIENT_SECRET` y `YT_REFRESH_TOKEN`. Los vas a pegar en GitHub en el Paso 7.

## Paso 6. Auditoría de la API de YouTube (5 min de llenar; Google tarda días o semanas)

YouTube deja en **privado** los videos subidos por proyectos nuevos de Google Cloud hasta que pasan una revisión gratuita.

1. Llena el formulario **"YouTube API Services - Audit and Quota Extension Form"**: support.google.com/youtube/contact/yt_api_form
2. Describe el uso: *"Herramienta interna que publica contenido original en mi propio canal [enlace]. Uso youtube.upload para subir, youtube.readonly para evitar duplicados y yt-analytics.readonly para ver estadísticas de mi canal. No accede a datos de otros usuarios."*

**Mientras esperas la aprobación,** el sistema genera y sube todo igual, pero los videos quedan en privado. Puedes descargarlos (pestaña *Actions* → la ejecución → *Artifacts*) y subirlos a mano desde la app de YouTube. El título y la descripción están en `meta.json`.

## Paso 7. Ponerlo en la nube: GitHub (20 min)

1. Crea una cuenta en **github.com**.
2. **New repository** → nombre `misterios-sin-resolver`.
   - **Public (recomendado):** los minutos de GitHub Actions son ilimitados y el panel se puede ver como página web. Tus claves **no** se ven.
   - **Private:** nadie ve el código ni el panel, pero solo tienes 2,000 minutos al mes, que no alcanzan para shorts y videos largos a la vez.
3. Instala Git (acepta la ventana de permisos de Windows):
   ```
   winget install --id Git.Git -e
   ```
   Cierra y vuelve a abrir la terminal en la carpeta `misterios-shorts`, y ejecuta una por una:
   ```
   git init
   git config user.name "TU_USUARIO"
   git config user.email "TU_USUARIO@users.noreply.github.com"
   git add .
   git commit -m "Sistema Misterios Sin Resolver"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/misterios-sin-resolver.git
   git push -u origin main
   ```
   La primera vez se abre una ventana para iniciar sesión en GitHub. Los archivos secretos (`client_secret.json`, `token_youtube.txt`) y los videos **no** se suben: están en `.gitignore`.
4. En el repositorio: **Settings → Secrets and variables → Actions**.
   Pestaña **Secrets → New repository secret**, uno por uno:

   | Nombre | Valor | ¿Obligatorio? |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | clave del Paso 2A | esta o la de Gemini |
   | `GEMINI_API_KEY` | clave del Paso 2B | esta o la de Claude |
   | `PEXELS_API_KEY` | clave del Paso 3 | muy recomendado |
   | `POLLINATIONS_TOKEN` | token del Paso 4 | opcional |
   | `YT_CLIENT_ID` | del Paso 5 | sí |
   | `YT_CLIENT_SECRET` | del Paso 5 | sí |
   | `YT_REFRESH_TOKEN` | del Paso 5 | sí |

   Pestaña **Variables → New repository variable** (todas opcionales):

   | Nombre | Ejemplo | Para qué |
   |---|---|---|
   | `CLAUDE_MODELO` | `claude-sonnet-5-5` | Modelo de Claude (por defecto `claude-opus-5-5`) |
   | `YT_HORA_PUBLICACION_SHORTS` | `12:00,19:00` | Horarios en que YouTube publica los shorts (hora CDMX). Si la dejas vacía, se publican al terminar |
   | `YT_HORA_PUBLICACION_LARGOS` | `18:00` | Lo mismo para videos largos |
   | `YT_PRIVACIDAD` | `public` | `public`, `unlisted` o `private` (si no programas hora) |
   | `CANAL_NOMBRE` | `Misterios Sin Resolver` | Nombre que la IA usa en los guiones |

5. **Panel web** (solo con repo público): **Settings → Pages → Source: Deploy from a branch → Branch: `main`, carpeta `/docs`** → Save. En unos minutos el panel queda en `https://TU_USUARIO.github.io/misterios-sin-resolver/`. En un repo privado, abre `PANEL.md` en GitHub.
6. **Prueba:** pestaña **Actions** → si te lo pide, pulsa *"I understand… enable them"*. Luego:
   - *Shorts diarios* → **Run workflow** con "¿Subir a YouTube?" **desmarcado**. Cuando termine (en verde ✅), descarga el video en *Artifacts* y míralo.
   - *Videos largos* → **Run workflow** con **Modo prueba** marcado.
   - Si los dos se ven bien, lanza *Shorts diarios* otra vez con la subida activada y comprueba que aparece en YouTube Studio.

Listo. Desde ese momento todo corre solo.

---

## Mantenimiento (lo único que tienes que vigilar)

- **Correo de GitHub "Run failed":** abre el panel o la ejecución en *Actions* para ver el error (tabla de abajo). Un fallo aislado no es grave: la siguiente ejecución sigue normal.
- **Una vez por semana:** mira el panel y 2 o 3 videos publicados. La IA verifica los datos, pero no es infalible. Si un video tiene un error, bórralo en YouTube Studio.
- **Una vez al mes:** revisa el gasto en console.anthropic.com (el panel también muestra el costo de cada video).
- **Pausar el canal:** *Actions* → elige el workflow → **⋯ → Disable workflow**.
- **Agregar o quitar temas:** edita `data/temas.json` en GitHub (botón ✏️). Son títulos de Wikipedia en inglés, agrupados por categoría.
- **Cambiar la frecuencia:** edita las líneas `cron` en `.github/workflows/shorts.yml` (hora UTC = hora CDMX + 6). Para 3 shorts al día, agrega una tercera línea `- cron: "0 18 * * *"` (hay un ejemplo en el archivo).
- **Usar tu propia música:** sube archivos `.mp3` libres de derechos a `assets/music/` (por ejemplo, de la Biblioteca de audio de YouTube). Si la carpeta está vacía, se genera música ambiental original.
- **Cambiar voz:** variable `VOZ` (`es-MX-JorgeNeural`, `es-MX-DaliaNeural`, `es-US-AlonsoNeural`, `es-ES-AlvaroNeural`).

### Problemas comunes

| Mensaje de error | Qué hacer |
|---|---|
| `invalid_grant` o `Token has been expired or revoked` | La app quedó "En prueba" o quitaste el permiso. Pásala a producción (Paso 5.3) y repite el Paso 5.6 y el 7.4 con el nuevo `YT_REFRESH_TOKEN` |
| `Guion escrito solo por el respaldo gratuito` | No hay clave de Claude ni de Gemini, o se agotaron. Revisa los Secrets y el saldo |
| `quotaExceeded` | Se pasó la cuota diaria de YouTube. Se resuelve solo al día siguiente; si se repite, baja la cantidad de shorts |
| `credit balance is too low` | Recarga saldo en console.anthropic.com |
| Videos en privado aunque pusiste `public` | Falta la aprobación de la auditoría (Paso 6) |
| `No pude poner la miniatura` | Verifica el canal con tu teléfono (Paso 1.3) |
| `No encontré un tema nuevo` | Agrega temas en `data/temas.json` |

### Probar en tu PC (opcional)

```
.venv\Scripts\python -m pipeline.main short --no-subir
.venv\Scripts\python -m pipeline.main largo --prueba --no-subir
.venv\Scripts\python -m pipeline.main short --no-subir --tema "Mary Celeste"
.venv\Scripts\python -m pipeline.main panel
```
Los videos quedan en `out/`. Para usar tus claves en la PC, defínelas antes en la terminal: `$env:ANTHROPIC_API_KEY="sk-ant-..."`.

## Estructura del proyecto

```
pipeline/
  investigacion.py  elige el tema (Wikipedia + popularidad + aprendizajes)
  ia.py             Claude / Gemini / Pollinations, con cálculo de costo
  guion.py          guiones de shorts y largos, editor y verificación
  voz.py            narración y tiempos por palabra
  visuales.py       imágenes IA, clips de Pexels y estilos visuales
  montaje.py        edición con FFmpeg (cámara, subtítulos, música, efectos)
  miniatura.py      miniaturas de videos largos
  youtube.py        subida, programación, duplicados
  estadisticas.py   métricas y aprendizajes
  panel.py          panel web y PANEL.md
  db.py             registros en data/*.json
  main.py           punto de entrada
data/               temas, videos, ejecuciones, estadísticas y aprendizajes
docs/index.html     panel de control
.github/workflows/  programación en la nube
```
