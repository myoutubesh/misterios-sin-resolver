"""Narración con edge-tts (voces neuronales de Microsoft, gratis) y tiempos por palabra."""
import asyncio
import subprocess
import time

import edge_tts

from .config import PAUSA_ESCENA, VOZ, VOZ_PITCH, VOZ_RATE


async def _sintetizar(texto, mp3, rate):
    com = edge_tts.Communicate(texto, VOZ, rate=rate, pitch=VOZ_PITCH, boundary="WordBoundary")
    palabras = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                palabras.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
    return palabras


def duracion(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def narrar(escenas, carpeta, rate=VOZ_RATE, pausa=PAUSA_ESCENA):
    """Un wav por escena (con pausa al final). Añade a cada escena: wav, inicio, dur y palabras."""
    t0 = 0.0
    for i, esc in enumerate(escenas):
        mp3, wav = carpeta / f"voz_{i:03d}.mp3", carpeta / f"voz_{i:03d}.wav"
        for intento in range(5):
            try:
                palabras = asyncio.run(_sintetizar(esc["narracion"], mp3, rate))
                if not palabras or mp3.stat().st_size < 1000:
                    raise RuntimeError("audio vacío")
                break
            except Exception as e:  # noqa: BLE001
                print(f"[voz] escena {i} intento {intento + 1}: {e}")
                if intento == 4:
                    raise
                time.sleep(4 * (intento + 1))
        p = pausa + (0.25 if esc.get("pausa_extra") else 0)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af", f"apad=pad_dur={p}",
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        dur = duracion(wav)
        esc.update(wav=wav, inicio=t0, dur=dur,
                   palabras=[{"t": q["t"] + t0, "d": q["d"], "w": q["w"]} for q in palabras])
        t0 += dur
    return escenas, t0
