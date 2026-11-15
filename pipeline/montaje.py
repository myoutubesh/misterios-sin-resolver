"""Edición automática con FFmpeg, para shorts (9:16) y videos largos (16:9).

- Imágenes: movimiento de cámara (zoom/paneo) distinto en cada escena.
- Clips reales: recortados a la duración de la escena.
- Transiciones suaves (fundidos cortos) y efectos de sonido sintetizados (whoosh e impacto).
- Subtítulos sincronizados palabra por palabra (shorts) o por frase (largos) + títulos de capítulo.
- Música ambiental generada (sin copyright) con "ducking" bajo la voz y volumen normalizado (-14 LUFS).
- Gradación de color, grano y viñeta según el estilo elegido para el video.
"""
import random
import shutil
import subprocess

import requests

from .config import ASSETS, FPS, VOLUMEN_MUSICA

FUENTES = {
    "Anton": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
    "Bebas Neue": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
}
COLA = 1.2


def _ff(args, cwd=None, limite=900):
    """FFmpeg sin leer el teclado (-nostdin) y con tiempo máximo, para que nunca se quede colgado."""
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True, cwd=cwd, stdin=subprocess.DEVNULL, timeout=limite)


def asegurar_fuentes(destino):
    destino.mkdir(exist_ok=True)
    for nombre, url in FUENTES.items():
        archivo = ASSETS / "fonts" / url.rsplit("/", 1)[1]
        if not archivo.exists():
            archivo.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            archivo.write_bytes(r.content)
        shutil.copy(archivo, destino / archivo.name)


# ---------- escenas ----------
MOVIMIENTOS = ["in", "out", "abajo", "arriba", "derecha", "izquierda"]


def _zoompan(mov, n, w, h):
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    z, x, y = {
        "in": (f"1+0.14*on/{n}", cx, cy),
        "out": (f"1.14-0.14*on/{n}", cx, cy),
        "abajo": ("1.12", cx, f"(ih-ih/zoom)*on/{n}"),
        "arriba": ("1.12", cx, f"(ih-ih/zoom)*(1-on/{n})"),
        "derecha": ("1.12", f"(iw-iw/zoom)*on/{n}", cy),
        "izquierda": ("1.12", f"(iw-iw/zoom)*(1-on/{n})", cy),
    }[mov]
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={FPS}"


def clip_escena(esc, dur, mov, salida, w, h, escala):
    n = max(2, round(dur * FPS))
    fades = f"fade=t=in:st=0:d=0.22,fade=t=out:st={max(0, dur - 0.18):.3f}:d=0.18"
    comunes = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
               "-an", str(salida)]
    if esc["visual"] == "clip":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
              f"setpts=PTS-STARTPTS,{fades}")
        _ff(["-stream_loop", "-1", "-i", str(esc["archivo"]), "-t", f"{dur:.3f}", "-vf", vf, "-frames:v", str(n),
             *comunes])
    else:
        W, H = int(w * escala) // 2 * 2, int(h * escala) // 2 * 2
        # Recorta 7 % de abajo (posible marca de agua) y llena el cuadro
        vf = (f"crop=iw:ih*0.93:0:0,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"{_zoompan(mov, n, w, h)},{fades}")
        _ff(["-i", str(esc["archivo"]), "-vf", vf, "-frames:v", str(n), *comunes])


# ---------- subtítulos ----------
def _ts(s):
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _t(w):
    return w.replace("{", "(").replace("}", ")").replace("\\", "")


def _bloques(palabras, max_palabras, max_letras):
    bloques, actual = [], []
    for i, p in enumerate(palabras):
        actual.append(p)
        sig = palabras[i + 1] if i + 1 < len(palabras) else None
        pausa = sig and sig["t"] - (p["t"] + p["d"]) > 0.25
        if len(actual) >= max_palabras or not sig or pausa or len(" ".join(x["w"] for x in actual)) > max_letras:
            bloques.append(actual)
            actual = []
    return bloques


def escribir_ass(escenas, ruta, total, vertical, estilo, gancho="", capitulos=None):
    fuente = random.choice(list(FUENTES)) if vertical else "Bebas Neue"
    acento, caja = estilo["acento"], estilo["caja"]
    if vertical:
        tam = 104 if fuente == "Anton" else 120
        margen = random.choice([640, 720, 820])
        estilos = (f"Style: Sub,{fuente},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,1,0,1,7,4,2,70,70,{margen},1\n"
                   f"Style: Gancho,{fuente},{tam - 14},&H00FFFFFF,&H00FFFFFF,{caja},&H00000000,0,0,0,0,100,100,1,0,3,22,0,8,90,90,330,1\n")
        resx, resy = 1080, 1920
    else:
        estilos = ("Style: Sub,Bebas Neue,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,1,0,1,4,2,2,160,160,70,1\n"
                   f"Style: Cap,Bebas Neue,86,&H00FFFFFF,&H00FFFFFF,{caja},&H00000000,0,0,0,0,100,100,2,0,3,18,0,7,90,90,80,1\n")
        resx, resy = 1920, 1080
    cab = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {resx}\nPlayResY: {resy}\nWrapStyle: 0\n"
           "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           f"MarginL, MarginR, MarginV, Encoding\n{estilos}\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lineas = []
    palabras = [p for e in escenas for p in e["palabras"]]

    if vertical:
        if gancho:
            lineas.append(f"Dialogue: 1,{_ts(0)},{_ts(2.8)},Gancho,,0,0,0,,{{\\fad(0,250)}}{_t(gancho.upper())}")
        maxp = random.choice([2, 3, 3])
        for b_i, b in enumerate(bl := _bloques(palabras, maxp, 16)):
            fin_b = b[-1]["t"] + b[-1]["d"] + 0.15
            if b_i + 1 < len(bl):
                fin_b = min(fin_b, bl[b_i + 1][0]["t"])
            fin_b = min(fin_b, total)
            for k, p in enumerate(b):
                ini, fin = p["t"], (b[k + 1]["t"] if k + 1 < len(b) else fin_b)
                if fin <= ini:
                    continue
                txt = " ".join(("{\\c" + acento + "}" + _t(q["w"]).upper() + "{\\c&H00FFFFFF&}") if j == k
                               else _t(q["w"]).upper() for j, q in enumerate(b))
                pop = "{\\fscx90\\fscy90\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
                lineas.append(f"Dialogue: 0,{_ts(ini)},{_ts(fin)},Sub,,0,0,0,,{pop}{txt}")
    else:
        bl = _bloques(palabras, 8, 46)
        for b_i, b in enumerate(bl):
            ini = b[0]["t"]
            fin = min(b[-1]["t"] + b[-1]["d"] + 0.3, bl[b_i + 1][0]["t"] if b_i + 1 < len(bl) else total)
            lineas.append(f"Dialogue: 0,{_ts(ini)},{_ts(fin)},Sub,,0,0,0,,{_t(' '.join(q['w'] for q in b))}")
        for t0, nombre in (capitulos or []):
            if t0 > 1:
                lineas.append(f"Dialogue: 1,{_ts(t0)},{_ts(t0 + 3.5)},Cap,,0,0,0,,{{\\fad(300,400)}}{_t(nombre.upper())}")
    ruta.write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")
    return fuente


# ---------- audio ----------
def musica(dur, salida):
    pistas = list((ASSETS / "music").glob("*.mp3")) + list((ASSETS / "music").glob("*.wav"))
    if pistas:
        _ff(["-stream_loop", "-1", "-i", str(random.choice(pistas)), "-t", f"{dur:.2f}",
             "-af", f"afade=t=in:d=1,afade=t=out:st={dur - 2:.2f}:d=2", "-ar", "44100", "-ac", "2", str(salida)])
        return "pista propia"
    raiz = random.choice([41.2, 46.25, 49.0, 55.0, 61.74])
    intervalo = random.choice([1.4142, 1.189, 1.335])  # tritono, tercera menor, cuarta
    d = f"{dur:.2f}"
    fc = (f"anoisesrc=color=brown:amplitude=0.5:duration={d},lowpass=f={random.choice([180, 240, 320])},volume=0.55[nz];"
          f"sine=f={raiz}:d={d},volume=0.5[s1];"
          f"sine=f={raiz * intervalo:.2f}:d={d},volume=0.28,tremolo=f={random.uniform(0.1, 0.25):.2f}:d=0.7[s2];"
          f"sine=f={raiz * 2:.2f}:d={d},volume=0.18,tremolo=f={random.uniform(0.15, 0.3):.2f}:d=0.85[s3];"
          f"sine=f={raiz * 3.03:.2f}:d={d},volume=0.06,tremolo=f=0.31:d=0.9[s4];"
          f"[nz][s1][s2][s3][s4]amix=inputs=5:normalize=0,aecho=0.8:0.7:700|1300:0.35|0.22,"
          f"afade=t=in:d=1.5,afade=t=out:st={dur - 2.5:.2f}:d=2.5,aformat=channel_layouts=stereo")
    _ff(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-filter_complex", fc, "-t", d, "-ar", "44100", str(salida)])
    return "drone sintetizado"


def efectos(momentos, dur, carpeta):
    """Pista de efectos: impacto grave al inicio y 'whoosh' en las transiciones."""
    _ff(["-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:a=0.6", "-af",
         "highpass=f=500,lowpass=f=5000,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35,volume=0.5,"
         "aformat=sample_rates=44100:channel_layouts=stereo", str(carpeta / "whoosh.wav")])
    _ff(["-f", "lavfi", "-i", "sine=f=48:d=1.6", "-f", "lavfi", "-i", "anoisesrc=d=0.25:c=brown:a=0.8",
         "-filter_complex", "[0]volume=1.2[a];[1]lowpass=f=300,afade=t=out:d=0.25[b];[a][b]amix=inputs=2:normalize=0,"
         "afade=t=out:st=0.1:d=1.5:curve=exp,aformat=sample_rates=44100:channel_layouts=stereo",
         str(carpeta / "boom.wav")])
    entradas = ["-i", "boom.wav"] + sum((["-i", "whoosh.wav"] for _ in momentos), [])
    partes = ["[0]adelay=0|0[e0]"]
    for k, t in enumerate(momentos, start=1):
        ms = max(0, int((t - 0.3) * 1000))
        partes.append(f"[{k}]adelay={ms}|{ms}[e{k}]")
    mezcla = "".join(f"[e{k}]" for k in range(len(momentos) + 1))
    fc = ";".join(partes) + f";{mezcla}amix=inputs={len(momentos) + 1}:normalize=0,apad,atrim=0:{dur:.2f}"
    _ff([*entradas, "-filter_complex", fc, "-ar", "44100", "efectos.wav"], cwd=carpeta)


# ---------- todo junto ----------
def montar(escenas, total_voz, carpeta, salida, vertical, estilo, gancho="", capitulos=None):
    asegurar_fuentes(carpeta / "fonts")
    w, h = (1080, 1920) if vertical else (1920, 1080)
    escala = 2.0 if vertical else 1.5
    total = total_voz + COLA
    movs = MOVIMIENTOS[:]
    random.shuffle(movs)

    lista = []
    for i, e in enumerate(escenas):
        dur = e["dur"] + (COLA if i == len(escenas) - 1 else 0)
        clip = carpeta / f"clip_{i:03d}.mp4"
        if i % 10 == 0 or vertical:
            print(f"[montaje] escena {i + 1}/{len(escenas)}")
        clip_escena(e, dur, movs[i % len(movs)], clip, w, h, escala)
        lista.append(f"file '{clip.name}'")
    (carpeta / "clips.txt").write_text("\n".join(lista), encoding="utf-8")
    print("[montaje] uniendo escenas")
    _ff(["-f", "concat", "-safe", "0", "-i", "clips.txt", "-c", "copy", "video_mudo.mp4"], cwd=carpeta)

    (carpeta / "voces.txt").write_text("\n".join(f"file '{e['wav'].name}'" for e in escenas), encoding="utf-8")
    _ff(["-f", "concat", "-safe", "0", "-i", "voces.txt", "-c", "copy", "narracion.wav"], cwd=carpeta)

    print("[montaje] música y efectos")
    origen_musica = musica(total, carpeta / "musica.wav")
    if vertical:
        momentos = [e["inicio"] for e in escenas[1:]]
    else:  # en largos, whoosh solo al cambiar de capítulo (más sobrio)
        momentos = [t for t, _ in (capitulos or []) if t > 1]
    efectos(momentos, total, carpeta)
    fuente = escribir_ass(escenas, carpeta / "subs.ass", total, vertical, estilo, gancho, capitulos)

    vol_sfx = 0.55 if vertical else 0.35
    fc = (f"[0:v]{estilo['grade']},noise=alls=5:allf=t,vignette=angle=PI/4.5,"
          "subtitles=subs.ass:fontsdir=fonts,format=yuv420p[v];"
          "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,apad,asplit[n1][n2];"
          f"[2:a]volume={VOLUMEN_MUSICA}[m];[3:a]volume={vol_sfx}[fx];"
          "[m][n2]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=450[md];"
          "[n1][md][fx]amix=inputs=3:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    print("[montaje] mezcla final")
    _ff(["-i", "video_mudo.mp4", "-i", "narracion.wav", "-i", "musica.wav", "-i", "efectos.wav",
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "medium" if vertical else "faster", "-crf", "21",
         "-maxrate", "9M" if vertical else "12M", "-bufsize", "18M" if vertical else "24M", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(salida.resolve())],
        cwd=carpeta, limite=1200 if vertical else 7200)
    return {"duracion": round(total, 1), "musica": origen_musica, "fuente_subs": fuente}
