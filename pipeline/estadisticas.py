"""Estadísticas del canal y aprendizaje automático de lo que funciona.

1. Descarga métricas de cada video (vistas, me gusta, comentarios; y de Analytics: retención, duración
   vista media, suscriptores ganados).
2. Analiza: categorías con más vistas, mejores títulos, duración y horario con mejores resultados.
3. Guarda data/aprendizajes.json, que la investigación y los guiones usan en los próximos videos.

Limitación: el CTR de miniaturas no está disponible en las consultas normales de YouTube Analytics API.
"""
import datetime as dt
import statistics
from collections import defaultdict
from zoneinfo import ZoneInfo

from . import db, ia, youtube
from .config import ZONA_HORARIA

METRICAS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments"


def actualizar():
    vids = [v for v in db.videos() if v.get("youtube_id")]
    est = db.leer(db.ESTADISTICAS, {"videos": {}, "historial_canal": []})
    yt = youtube.servicio()

    canal = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
    hoy = dt.date.today().isoformat()
    est["canal"] = {"suscriptores": int(canal.get("subscriberCount", 0)), "vistas": int(canal.get("viewCount", 0)),
                    "videos": int(canal.get("videoCount", 0)), "fecha": hoy}
    est["historial_canal"] = [h for h in est.get("historial_canal", []) if h["fecha"] != hoy] + [est["canal"]]
    est["historial_canal"] = est["historial_canal"][-365:]

    ids = [v["youtube_id"] for v in vids]
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics,status", id=",".join(ids[i:i + 50])).execute()
        for item in r.get("items", []):
            s = item.get("statistics", {})
            d = est["videos"].setdefault(item["id"], {})
            d.update(vistas=int(s.get("viewCount", 0)), likes=int(s.get("likeCount", 0)),
                     comentarios=int(s.get("commentCount", 0)), privacidad=item["status"].get("privacyStatus"),
                     actualizado=hoy)
            # Un video programado que ya salió pasa a "publicado"
            for v in vids:
                if v["youtube_id"] == item["id"] and d["privacidad"] == "public" and v.get("estado") != "publicado":
                    db.guardar_video({"id": v["id"], "estado": "publicado"})

    try:
        yta = youtube.servicio("youtubeAnalytics", "v2")
        inicio = min((v["fecha"][:10] for v in vids), default=hoy)
        for i in range(0, len(ids), 200):
            r = yta.reports().query(ids="channel==MINE", startDate=inicio, endDate=hoy, metrics=METRICAS,
                                    dimensions="video", filters="video==" + ",".join(ids[i:i + 200]),
                                    maxResults=200, sort="-views").execute()
            cols = [c["name"] for c in r.get("columnHeaders", [])]
            for fila in r.get("rows", []):
                d = dict(zip(cols, fila))
                est["videos"].setdefault(d["video"], {}).update(
                    minutos_vistos=d.get("estimatedMinutesWatched"), duracion_vista_media=d.get("averageViewDuration"),
                    retencion=d.get("averageViewPercentage"), suscriptores_ganados=d.get("subscribersGained"))
    except Exception as e:  # noqa: BLE001
        print(f"[estadisticas] Analytics API no disponible: {str(e)[:200]}")

    est["actualizado"] = db.ahora()
    db.escribir(db.ESTADISTICAS, est)
    print(f"[estadisticas] {len(est['videos'])} videos, {est['canal']['suscriptores']} suscriptores")
    analizar(est)
    return est


def _promedio(valores):
    valores = [x for x in valores if x is not None]
    return statistics.mean(valores) if valores else None


def analizar(est=None):
    est = est or db.leer(db.ESTADISTICAS, {"videos": {}})
    zona = ZoneInfo(ZONA_HORARIA)
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)  # ignora videos muy recientes
    filas = []
    for v in db.videos():
        m = est.get("videos", {}).get(v.get("youtube_id") or "", {})
        if not m or "vistas" not in m:
            continue
        salida = dt.datetime.fromisoformat((v.get("publicar_en") or v["fecha"]).replace("Z", "+00:00"))
        if salida > limite:
            continue
        filas.append({**v, **m, "hora": salida.astimezone(zona).hour})

    aprend = db.leer(db.APRENDIZAJES, {})
    aprend.update(actualizado=db.ahora(), videos_analizados=len(filas))
    consejos = []

    # Categorías
    por_cat = defaultdict(list)
    for f in filas:
        por_cat[f.get("categoria")].append(f["vistas"])
    media = _promedio([f["vistas"] for f in filas]) or 0
    pesos = {}
    for cat, vs in por_cat.items():
        if cat and len(vs) >= 2 and media > 0:
            pesos[cat] = round(max(0.3, min(3.0, statistics.mean(vs) / media)), 2)
    aprend["peso_categoria"] = pesos
    if pesos:
        mejor = max(pesos, key=pesos.get)
        consejos.append(f"La categoría con mejor rendimiento es '{mejor}' ({pesos[mejor]}x el promedio).")

    # Títulos top por formato
    aprend["titulos_top"] = {}
    for formato in ("short", "largo"):
        top = sorted((f for f in filas if f.get("formato") == formato), key=lambda f: -f["vistas"])[:5]
        aprend["titulos_top"][formato] = [f["titulo_yt"] for f in top]

    # Duración (shorts)
    cubetas = defaultdict(list)
    for f in filas:
        if f.get("formato") == "short" and f.get("duracion"):
            cubetas[f"{int(f['duracion'] // 10) * 10}-{int(f['duracion'] // 10) * 10 + 10}s"].append(
                f.get("retencion") or f["vistas"])
    if len(cubetas) >= 2:
        mejor = max(cubetas, key=lambda k: statistics.mean(cubetas[k]))
        aprend["duracion_ideal_short"] = mejor
        consejos.append(f"Los shorts de {mejor} rinden mejor.")

    # Horario
    horas = defaultdict(list)
    for f in filas:
        horas[f["hora"]].append(f["vistas"])
    horas = {h: statistics.mean(v) for h, v in horas.items() if len(v) >= 2}
    if horas:
        mejor = max(horas, key=horas.get)
        aprend["mejor_hora"] = mejor
        consejos.append(f"Las publicaciones cerca de las {mejor}:00 ({ZONA_HORARIA}) tienen más vistas.")

    # Retención media
    ret = _promedio([f.get("retencion") for f in filas if f.get("formato") == "short"])
    if ret is not None:
        aprend["retencion_media_short"] = round(ret, 1)

    # Con suficientes datos, la IA resume patrones de títulos y temas
    if len(filas) >= 8:
        try:
            tabla = "\n".join(f"- [{f.get('formato')}/{f.get('categoria')}] {f['titulo_yt']} | vistas {f['vistas']}"
                              f" | retención {f.get('retencion')}" for f in sorted(filas, key=lambda f: -f['vistas'])[:40])
            r = ia.generar_json(
                "Analiza el rendimiento de estos videos de un canal de misterios en YouTube. Da 3 a 5 consejos "
                "concretos y accionables para los próximos guiones y títulos (estilo de gancho, tipo de tema, "
                "longitud del título). No prometas resultados. Responde SOLO JSON: {\"consejos\": [\"...\"]}\n\n" + tabla,
                intentos=1, max_tokens=4000)
            consejos += [c for c in r.get("consejos", []) if isinstance(c, str)][:5]
        except Exception as e:  # noqa: BLE001
            print(f"[estadisticas] análisis con IA no disponible: {e}")
    aprend["consejos"] = consejos
    db.escribir(db.APRENDIZAJES, aprend)
    print(f"[estadisticas] aprendizajes: {consejos or 'aún no hay suficientes datos'}")
    return aprend
