"""Ajustes del canal. Las claves NUNCA van aquí: se leen de variables de entorno (GitHub Secrets)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
DOCS = ROOT / "docs"

CANAL = os.getenv("CANAL_NOMBRE", "Misterios Sin Resolver")

# ---------- IA de texto (se usa la primera que tenga clave) ----------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODELO = os.getenv("CLAUDE_MODELO", "claude-opus-5-5")
CLAUDE_ESFUERZO = os.getenv("CLAUDE_ESFUERZO", "medium")       # low | medium | high
CLAUDE_VERIFICAR = os.getenv("CLAUDE_VERIFICAR", "1") == "1"   # verificación con búsqueda web
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Si ninguno existe para tu clave, ia.py busca solo el modelo "flash" más nuevo disponible
GEMINI_MODELOS = [m.strip() for m in (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash,gemini-flash-latest").split(",")
                  if m.strip()]
POLLINATIONS_TOKEN = os.getenv("POLLINATIONS_TOKEN", "").strip()
# Pollinations escribe peor e inventa datos: por defecto NO se publica un guion escrito solo por él
PUBLICAR_CON_RESPALDO = os.getenv("PUBLICAR_CON_RESPALDO", "0") == "1"

# Precios por millón de tokens (entrada, salida) para calcular el costo real de cada video
PRECIOS = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
PRECIO_BUSQUEDA_WEB = 0.01  # ≈ $10 por 1,000 búsquedas

# ---------- Voz ----------
VOZ = os.getenv("VOZ", "es-MX-JorgeNeural")
VOZ_RATE = os.getenv("VOZ_RATE", "+4%")
VOZ_PITCH = os.getenv("VOZ_PITCH", "-6Hz")
VOZ_RATE_LARGO = os.getenv("VOZ_RATE_LARGO", "-2%")

# ---------- Visuales ----------
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()   # alternativa gratis a Pexels
IMG_MODELO = os.getenv("IMG_MODELO", "flux")
ESTILO_BASE = "no text, no letters, no watermark, no logo"

# ---------- Video ----------
FPS = 30
PAUSA_ESCENA = 0.30
VOLUMEN_MUSICA = float(os.getenv("VOLUMEN_MUSICA", "0.22"))

# ---------- Publicación ----------
PRIVACIDAD = os.getenv("YT_PRIVACIDAD", "public")       # public | unlisted | private
CATEGORIA_YT = os.getenv("YT_CATEGORIA", "24")          # 24 = Entretenimiento
# Si se define (p. ej. "18:30"), los videos se suben privados y YouTube los publica a esa hora (Ciudad de México)
# Cuota de YouTube: 10,000 unidades al día y cada subida cuesta 1,600 → máximo 6 subidas por día de cuota
# (el día de la cuota va de medianoche a medianoche, hora del Pacífico). Los shorts dejan 1 lugar libre los días
# que hay video largo, así que quedan 5 shorts + 1 largo.
LIMITE_SUBIDAS_DIA = int(os.getenv("LIMITE_SUBIDAS_DIA", os.getenv("LIMITE_SHORTS_DIA", "6")))
# Días con video largo (0 = lunes … 6 = domingo, según el día de cuota del Pacífico). Por defecto: todos.
LARGO_DIAS = {int(x) for x in os.getenv("LARGO_DIAS", "0,1,2,3,4,5,6").split(",") if x.strip().isdigit()}
# Probabilidad de que el video largo del día sea una LISTA ("7 leyendas de México") en vez de un caso a fondo
PROB_LISTA = float(os.getenv("PROB_LISTA", "0.45"))
HORA_PUBLICACION = os.getenv("YT_HORA_PUBLICACION", "")
ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Mexico_City")

# Reddit: probabilidad de sacar el tema de lo más comentado de la semana (0 = nunca)
REDDIT_PROB = float(os.getenv("REDDIT_PROB", "0.4"))
REDDIT_SUBS = [x.strip() for x in os.getenv(
    "REDDIT_SUBS", "UnresolvedMysteries,Cryptozoology"
).split(",") if x.strip()]
USER_AGENT = "misterios-sin-resolver-bot/1.0 (+https://github.com)"
