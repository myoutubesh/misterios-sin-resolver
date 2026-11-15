"""Ejecútalo UNA vez en tu PC para autorizar tu canal de YouTube (OAuth seguro de Google).

1. Pon el archivo client_secret.json (de Google Cloud) en esta carpeta.
2. .venv\\Scripts\\python obtener_token.py
3. Se abre el navegador: elige la cuenta/canal y acepta los permisos.
4. Copia los 3 valores que imprime a los "Secrets" de GitHub.

Permisos que pide: subir videos, leer tu canal (para evitar duplicados y ver estadísticas)
y leer YouTube Analytics. No puede borrar videos ni cambiar la configuración del canal.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
aqui = Path(__file__).parent
secreto = aqui / "client_secret.json"
if not secreto.exists():
    raise SystemExit("Falta client_secret.json en esta carpeta (ver GUIA.md, paso 4).")

flow = InstalledAppFlow.from_client_secrets_file(str(secreto), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
cliente = json.loads(secreto.read_text()).get("installed") or json.loads(secreto.read_text()).get("web")

print("\n=== Copia estos 3 valores en GitHub → Settings → Secrets and variables → Actions ===\n")
print("YT_CLIENT_ID     =", cliente["client_id"])
print("YT_CLIENT_SECRET =", cliente["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
(aqui / "token_youtube.txt").write_text(
    f"YT_CLIENT_ID={cliente['client_id']}\nYT_CLIENT_SECRET={cliente['client_secret']}\n"
    f"YT_REFRESH_TOKEN={creds.refresh_token}\n", encoding="utf-8")
print("\nTambién quedaron en token_youtube.txt. No lo compartas ni lo subas a GitHub (ya está en .gitignore).")
print("Cuando los hayas copiado a GitHub, puedes borrar ese archivo.")
