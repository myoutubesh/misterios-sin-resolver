"""'Base de datos' en archivos JSON dentro del repositorio.

A este volumen (unos 100 videos al mes) JSON es más simple y transparente que una base
de datos: GitHub guarda el historial de cada cambio y no hay nada que administrar.

  data/videos.json        un registro por video (estado, tema, fuentes, costo, enlace…)
  data/ejecuciones.json   un registro por ejecución del sistema (éxito/error, duración)
  data/estadisticas.json  métricas de YouTube por video (las llena estadisticas.py)
  data/aprendizajes.json  conclusiones que usa la IA para mejorar (las llena estadisticas.py)
"""
import datetime as dt
import json
import traceback

from .config import DATA

VIDEOS = DATA / "videos.json"
EJECUCIONES = DATA / "ejecuciones.json"
ESTADISTICAS = DATA / "estadisticas.json"
APRENDIZAJES = DATA / "aprendizajes.json"


def ahora():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def leer(ruta, defecto):
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[db] {ruta.name} está dañado; empiezo vacío")
    return defecto


def escribir(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


# ---------- videos ----------
def videos():
    return leer(VIDEOS, [])


def guardar_video(registro):
    """Inserta o actualiza por 'id'."""
    todos = videos()
    for i, v in enumerate(todos):
        if v["id"] == registro["id"]:
            todos[i] = {**v, **registro}
            break
    else:
        todos.append(registro)
    escribir(VIDEOS, todos)


def temas_usados():
    usados = set()
    for v in videos():
        if v.get("estado") in ("publicado", "programado", "subido", "creado"):
            usados.add(v.get("tema_clave", "").lower())
    return usados


def ya_subido(clave, formato):
    return any(v.get("tema_clave", "").lower() == clave.lower() and v.get("formato") == formato and v.get("youtube_id")
               for v in videos())


# ---------- ejecuciones ----------
class Ejecucion:
    """Uso: with Ejecucion('short') as ej: ...  → registra inicio, fin, estado y error."""

    def __init__(self, tipo):
        self.reg = {"id": dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{tipo}", "tipo": tipo,
                    "inicio": ahora(), "estado": "en curso"}

    def __enter__(self):
        return self

    def nota(self, **kw):
        self.reg.update(kw)

    def __exit__(self, tipo_exc, exc, tb):
        self.reg["fin"] = ahora()
        if exc:
            self.reg["estado"] = "error"
            self.reg["error"] = f"{tipo_exc.__name__}: {exc}"[:500]
            self.reg["traza"] = "".join(traceback.format_exception(tipo_exc, exc, tb))[-2000:]
        else:
            self.reg["estado"] = "ok"
        todas = leer(EJECUCIONES, [])
        todas.append(self.reg)
        escribir(EJECUCIONES, todas[-500:])  # guarda las últimas 500
        return False  # no oculta el error: el workflow falla y GitHub te avisa
