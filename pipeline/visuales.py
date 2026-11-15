"""Visuales de cada escena: imágenes IA (Pollinations) y clips reales de archivo (Pexels).

Cada video elige al azar un ESTILO (paleta, tipo de imagen, color de subtítulos, gradación), para
que los videos del canal no se vean todos iguales.
"""
import random
import time
import urllib.parse

import requests

from .config import ESTILO_BASE, IMG_MODELO, PEXELS_API_KEY, POLLINATIONS_TOKEN, USER_AGENT
from .ia import esperar_limite

ESTILOS = [
    {"nombre": "noche_turquesa",
     "img": "dark cinematic digital painting, eerie atmosphere, muted colors, cold teal shadows and one warm light source, volumetric fog, chiaroscuro",
     "grade": "eq=contrast=1.06:saturation=0.88", "acento": "&H0035D8FF&", "caja": "&H001A12A8&"},
    {"nombre": "archivo_antiguo",
     "img": "vintage archival photograph, 1960s documentary film still, sepia tones, film scratches, heavy grain, realistic",
     "grade": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,eq=contrast=1.08",
     "acento": "&H004DB8FF&", "caja": "&H00203040&"},
    {"nombre": "luna_fria",
     "img": "cold moonlit cinematic photograph, realistic, 35mm film, blue hour, mist, desolate, high detail",
     "grade": "colorbalance=bs=.12:ms=.06:hs=-.04,eq=saturation=0.75:contrast=1.05", "acento": "&H00FFE08A&",
     "caja": "&H00603010&"},
    {"nombre": "grabado",
     "img": "dark engraving illustration, old book woodcut etching style, black ink cross-hatching, aged paper, ominous",
     "grade": "eq=saturation=0.35:contrast=1.15", "acento": "&H002E2EE6&", "caja": "&H00101010&"},
    {"nombre": "carmesi",
     "img": "dark horror cinematic still, deep black shadows, single crimson accent light, fog, unsettling, photorealistic",
     "grade": "eq=contrast=1.1:saturation=0.9", "acento": "&H003C3CFF&", "caja": "&H00101070&"},
]


def elegir_estilo():
    return random.choice(ESTILOS)


# ---------- Pollinations ----------
def imagen_ia(prompt, destino, semilla, vertical, estilo):
    texto = f"{prompt}. {estilo['img']}, {ESTILO_BASE}"
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(texto, safe="")
    w, h = (864, 1536) if vertical else (1536, 864)
    params = {"width": w, "height": h, "model": IMG_MODELO, "seed": semilla, "nologo": "true",
              "private": "true", "enhance": "false"}
    headers = {"User-Agent": USER_AGENT}
    if POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {POLLINATIONS_TOKEN}"
    fallos = 0
    while fallos < 5:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image") and len(r.content) > 20000:
                destino.write_bytes(r.content)
                return True
            espera = esperar_limite(r)
            if espera:
                print(f"[visual] límite gratis de Pollinations, espero {espera}s")
                time.sleep(espera)
                continue
            print(f"[visual] Pollinations {r.status_code} ({len(r.content)} bytes)")
        except requests.RequestException as e:
            print(f"[visual] error: {e}")
        fallos += 1
        time.sleep(10 * fallos)
        params["seed"] = semilla + fallos
    return False


# ---------- Pexels ----------
def clip_pexels(consulta, destino, vertical, usados):
    if not PEXELS_API_KEY:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search", timeout=30,
                         headers={"Authorization": PEXELS_API_KEY},
                         params={"query": consulta, "orientation": "portrait" if vertical else "landscape",
                                 "size": "medium", "per_page": 15})
        if not r.ok:
            print(f"[visual] Pexels {r.status_code}")
            return None
        videos = [v for v in r.json().get("videos", []) if v["id"] not in usados and v.get("duration", 0) >= 4]
        random.shuffle(videos)
        for v in videos[:5]:
            archivos = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")]
            if not archivos:
                continue
            objetivo = 1920 if vertical else 1080
            mejor = min(archivos, key=lambda f: (abs(f["height"] - objetivo), -f["height"]))
            if min(mejor.get("width") or 0, mejor["height"]) < 700:
                continue
            with requests.get(mejor["link"], timeout=120, stream=True) as d:
                d.raise_for_status()
                with open(destino, "wb") as f:
                    for trozo in d.iter_content(1 << 20):
                        f.write(trozo)
            usados.add(v["id"])
            return {"id": v["id"], "autor": v.get("user", {}).get("name"), "url": v.get("url"),
                    "duracion": v.get("duration")}
    except Exception as e:  # noqa: BLE001
        print(f"[visual] Pexels falló con '{consulta}': {e}")
    return None


def preparar(escenas, carpeta, vertical, estilo, proporcion_real):
    """Asigna a cada escena una imagen IA o un clip real. Devuelve créditos de Pexels."""
    base = random.randint(1, 10_000_000)
    usados, creditos = set(), []
    ultima_img = None
    n = len(escenas)
    # La primera escena (gancho) siempre lleva imagen IA hecha a medida
    reales = set()
    if PEXELS_API_KEY and proporcion_real > 0:
        reales = set(random.sample(range(1, n), k=min(n - 1, round((n - 1) * proporcion_real))))
    for i, esc in enumerate(escenas):
        if i in reales:
            ruta = carpeta / f"vid_{i:03d}.mp4"
            info = clip_pexels(esc["stock"], ruta, vertical, usados)
            if info:
                esc["visual"], esc["archivo"] = "clip", ruta
                creditos.append(info)
                print(f"[visual] {i + 1}/{n} clip real: {esc['stock']}")
                continue
        ruta = carpeta / f"img_{i:03d}.jpg"
        print(f"[visual] {i + 1}/{n} imagen IA")
        if imagen_ia(esc["imagen"], ruta, base + i * 17, vertical, estilo):
            ultima_img = ruta
        elif ultima_img:
            ruta.write_bytes(ultima_img.read_bytes())
        else:
            raise RuntimeError("Pollinations no devolvió imágenes")
        esc["visual"], esc["archivo"] = "imagen", ruta
        if not POLLINATIONS_TOKEN and i + 1 < n and (i + 1) not in reales:
            time.sleep(46)  # sin clave: 1 imagen cada 45 s
    return creditos
