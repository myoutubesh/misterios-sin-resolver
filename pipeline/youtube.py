"""Conexión con YouTube (Data API v3 + Analytics API) usando OAuth.

Las credenciales salen de variables de entorno (GitHub Secrets). Nunca se escriben en el código.
"""
import datetime as dt
import os
import random
import time
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import db
from .config import CATEGORIA_YT, HORA_PUBLICACION, PRIVACIDAD, ZONA_HORARIA

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def credenciales_listas():
    return all(os.getenv(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def _creds():
    return Credentials(token=None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                       client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                       token_uri="https://oauth2.googleapis.com/token")


def servicio(nombre="youtube", version="v3"):
    return build(nombre, version, credentials=_creds(), cache_discovery=False)


# ---------- evitar duplicados ----------
def subidas_recientes(yt, n=50):
    """Títulos e ids de los últimos videos del canal (requiere permiso youtube.readonly)."""
    try:
        canal = yt.channels().list(part="contentDetails", mine=True).execute()
        lista = canal["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        r = yt.playlistItems().list(part="snippet", playlistId=lista, maxResults=min(n, 50)).execute()
        return [(i["snippet"]["title"], i["snippet"]["resourceId"]["videoId"]) for i in r.get("items", [])]
    except HttpError as e:
        print(f"[youtube] no pude leer subidas recientes ({e.status_code}); sigo")
        return []


# ---------- programación ----------
def proximos_horarios(n=2):
    """Los n próximos horarios de publicación y si ya tienen video: [(iso_utc, ocupado), ...]."""
    if not HORA_PUBLICACION:
        return []
    zona = ZoneInfo(ZONA_HORARIA)
    ocupados = {v.get("publicar_en") for v in db.videos() if v.get("publicar_en")}
    ahora = dt.datetime.now(zona)
    horas = sorted((h.strip() for h in HORA_PUBLICACION.split(",") if h.strip()),
                   key=lambda h: tuple(map(int, h.split(":"))))
    salida = []
    for dia in range(0, 3):
        fecha = (ahora + dt.timedelta(days=dia)).date()
        for h in horas:
            hh, mm = map(int, h.split(":"))
            momento = dt.datetime(fecha.year, fecha.month, fecha.day, hh, mm, tzinfo=zona)
            if momento < ahora + dt.timedelta(minutes=20):
                continue
            iso = momento.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            salida.append((iso, iso in ocupados))
            if len(salida) == n:
                return salida
    return salida


def proxima_fecha():
    """Si YT_HORA_PUBLICACION = '12:00,18:30', devuelve el próximo horario libre (UTC ISO)."""
    if not HORA_PUBLICACION:
        return None
    zona = ZoneInfo(ZONA_HORARIA)
    ocupados = {v.get("publicar_en") for v in db.videos() if v.get("publicar_en")}
    ahora = dt.datetime.now(zona)
    horas = sorted((h.strip() for h in HORA_PUBLICACION.split(",") if h.strip()),
                   key=lambda h: tuple(map(int, h.split(":"))))
    for dia in range(0, 14):
        fecha = (ahora + dt.timedelta(days=dia)).date()
        for h in horas:
            hh, mm = map(int, h.split(":"))
            momento = dt.datetime(fecha.year, fecha.month, fecha.day, hh, mm, tzinfo=zona)
            if momento < ahora + dt.timedelta(minutes=20):
                continue
            iso = momento.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            if iso not in ocupados:
                return iso
    return None


# ---------- subida ----------
def subir(video, meta, miniatura=None):
    yt = servicio()
    for titulo, vid in subidas_recientes(yt):
        if titulo.strip().lower() == meta["titulo"].strip().lower():
            print(f"[youtube] ya existe un video con ese título ({vid}); no lo subo otra vez")
            return {"youtube_id": vid, "estado": "duplicado_evitado"}

    publicar_en = proxima_fecha()
    status = {"privacyStatus": "private" if publicar_en else PRIVACIDAD, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True, "embeddable": True}
    if publicar_en:
        status["publishAt"] = publicar_en
    body = {"snippet": {"title": meta["titulo"], "description": meta["descripcion"], "tags": meta["tags"],
                        "categoryId": CATEGORIA_YT, "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": status}

    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, fallos = None, 0
    while resp is None:
        try:
            estado, resp = req.next_chunk()
            if estado:
                print(f"[youtube] subiendo {int(estado.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and fallos < 6:
                fallos += 1
                espera = 2 ** fallos + random.random()
                print(f"[youtube] error {e.resp.status}, reintento en {espera:.0f}s")
                time.sleep(espera)
            else:
                raise
    vid = resp["id"]
    st = resp.get("status", {})
    print(f"[youtube] listo: https://youtu.be/{vid} (privacidad: {st.get('privacyStatus')}"
          f"{', se publica ' + publicar_en if publicar_en else ''})")

    if miniatura:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura), mimetype="image/jpeg")).execute()
            print("[youtube] miniatura puesta")
        except HttpError as e:
            print(f"[youtube] no pude poner la miniatura ({e.status_code}). ¿Canal verificado con teléfono?")

    return {"youtube_id": vid, "estado": "programado" if publicar_en else
            ("publicado" if st.get("privacyStatus") == "public" else "subido"),
            "privacidad": st.get("privacyStatus"), "publicar_en": publicar_en,
            "url": f"https://youtu.be/{vid}"}
