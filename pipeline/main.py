"""Punto de entrada del sistema.

  python -m pipeline.main short                  # investiga, crea y publica un short
  python -m pipeline.main largo                  # lo mismo con un video largo (16:9)
  python -m pipeline.main short --no-subir       # solo crea el video (queda en out/)
  python -m pipeline.main short --tema "Mary Celeste"
  python -m pipeline.main largo --prueba         # video largo corto, para probar el sistema
  python -m pipeline.main estadisticas           # actualiza métricas y aprendizajes
  python -m pipeline.main panel                  # regenera el panel
"""
import argparse
import datetime as dt
import json
import re
import shutil
import sys
import unicodedata

from . import db, guion, ia, investigacion, miniatura, montaje, panel, visuales, voz, youtube
import random
import time

from .config import (CANAL, LARGO_DIAS, LIMITE_SUBIDAS_DIA, OUT, PROB_LISTA, PUBLICAR_CON_RESPALDO, VOZ_RATE,
                     VOZ_RATE_LARGO)


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:50]


def _mmss(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def metadatos(g, art, formato, capitulos, creditos):
    titulo = g["titulo"]
    if formato == "short":
        # En el reproductor de Shorts casi nadie abre la descripción: los hashtags que se VEN son los del
        # título. Ponemos los 2 más específicos del caso + #Shorts (si caben en los 100 caracteres).
        en_titulo = []
        for h in [*[x.lstrip("#").strip() for x in g.get("hashtags", [])][:2], "Shorts"]:
            if h and len(titulo) + len(" #" + h) <= 100 and h.lower() not in [x.lower() for x in en_titulo]:
                titulo += " #" + h
                en_titulo.append(h)
    partes = [g["descripcion"].strip(), ""]
    if formato == "largo" and len(capitulos) >= 3:
        partes += ["⏱️ Capítulos"] + [f"{_mmss(t)} {n}" for t, n in capitulos] + [""]
    if formato == "short":
        # Como MundoCreepy: el short lleva al video largo (solo si ese largo ya es público)
        largo = ultimo_largo_publico()
        if largo:
            partes += [f"▶️ Mira el documental completo: {largo['url']}", ""]
    partes.append("¿Tú qué crees que pasó? Te leo en los comentarios 👇")
    partes.append(f"🔔 Suscríbete a {CANAL} para un misterio nuevo cada día.\n")
    fuentes = art.get("fuentes", []) + g.get("fuentes_extra", [])
    partes.append("📚 Fuentes:\n" + "\n".join(f"• {u}" for u in dict.fromkeys(fuentes)))
    if art.get("reddit"):
        partes.append(f"💬 Tema sugerido por la conversación de la comunidad r/{art['reddit']['sub']}.")
    if creditos:
        for fuente in dict.fromkeys(c.get("fuente", "Pexels") for c in creditos):
            autores = ", ".join(dict.fromkeys(c["autor"] for c in creditos
                                              if c.get("autor") and c.get("fuente", "Pexels") == fuente))
            partes.append(f"🎞️ Clips de archivo: {fuente} ({autores}).")
    partes.append("🎨 Imágenes ilustrativas generadas con IA y narración con voz sintética. Las teorías y leyendas "
                  "se presentan como tales; los hechos provienen de las fuentes citadas.")
    # YouTube ignora TODOS los hashtags si hay más de 15 (contando los del título): usamos 15 en total
    del_titulo = [h.lower() for h in re.findall(r"#(\w+)", titulo)]
    maximo = 15 - len(del_titulo)
    extra = ["Misterio", "Shorts" if formato == "short" else "Documental"]
    lista = []
    for h in [*g.get("hashtags", []), *extra]:
        h = h.lstrip("#").strip()
        if h and h.lower() not in [x.lower() for x in lista] + del_titulo and len(lista) < maximo:
            lista.append(h)
    if "misterio" not in [x.lower() for x in lista] + del_titulo and lista:
        lista[-1] = "Misterio"  # la etiqueta del canal siempre va
    partes.append("\n" + " ".join("#" + h for h in lista))
    desc = "\n".join(partes)
    # Etiquetas: YouTube acepta hasta 500 caracteres en total
    tags, largo = [], 0
    for t in [*g.get("tags", []), *[h for h in re.findall(r"#(\w+)", titulo) + lista if h.lower() != "shorts"]]:
        t = t.strip()
        if t and t.lower() not in [x.lower() for x in tags] and largo + len(t) + 3 <= 480:
            tags.append(t)
            largo += len(t) + 3
    return {"titulo": titulo[:100], "descripcion": desc[:4900], "tags": tags}


def ultimo_largo_publico():
    ahora = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    for v in reversed(db.videos()):
        if v.get("formato") == "largo" and v.get("url") and (
                v.get("estado") == "publicado" or (v.get("publicar_en") and v["publicar_en"] <= ahora)):
            return v
    return None


PACIFICO = "America/Los_Angeles"


def subidas_hoy():
    """Subidas a YouTube en el día de cuota actual (medianoche a medianoche, hora del Pacífico)."""
    from zoneinfo import ZoneInfo
    pacifico = ZoneInfo(PACIFICO)
    hoy = dt.datetime.now(pacifico).date()
    cuenta = {"short": 0, "largo": 0}
    for v in db.videos():
        if not v.get("youtube_id") or not v.get("fecha") or v.get("estado") == "duplicado_evitado":
            continue
        try:
            f = dt.datetime.fromisoformat(v["fecha"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if f.tzinfo and f.astimezone(pacifico).date() == hoy and v.get("formato") in cuenta:
            cuenta[v["formato"]] += 1
    return cuenta, hoy


def hace_falta_short():
    """Para las ejecuciones automáticas: ¿toca crear un short ahora?

    - No pasa del límite diario de subidas de YouTube (6 por día de cuota). Los días con video largo deja
      1 lugar libre para él (5 shorts + 1 largo).
    - Si los 2 próximos horarios ya tienen video programado, no hace nada. Así las ejecuciones de respaldo
      solo crean video cuando GitHub se saltó una ejecución principal.
    """
    cuenta, hoy = subidas_hoy()
    reservado = 1 if hoy.weekday() in LARGO_DIAS and cuenta["largo"] == 0 else 0
    limite = LIMITE_SUBIDAS_DIA - reservado
    if cuenta["short"] + cuenta["largo"] >= limite:
        print(f"[main] ya hay {cuenta['short']} shorts y {cuenta['largo']} largos en el día de cuota de YouTube "
              f"(límite {limite}{', 1 lugar guardado para el largo' if reservado else ''}); no creo otro")
        return False
    proximos = youtube.proximos_horarios(2)
    if proximos and all(ocupado for _, ocupado in proximos):
        print(f"[main] los próximos horarios ya tienen video ({', '.join(h for h, _ in proximos)}); no hace falta otro")
        return False
    return True


def esperar_cupo_largo():
    """Antes de subir un largo: si el día de cuota ya está lleno, espera a que YouTube la reinicie (si falta poco)."""
    from zoneinfo import ZoneInfo
    cuenta, _ = subidas_hoy()
    if cuenta["short"] + cuenta["largo"] < LIMITE_SUBIDAS_DIA:
        return
    ahora = dt.datetime.now(ZoneInfo(PACIFICO))
    manana = (ahora + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    espera = (manana - ahora).total_seconds()
    if espera > 4 * 3600:
        raise RuntimeError("La cuota de YouTube de hoy ya está llena y falta mucho para que se reinicie; "
                           "el video queda guardado como artefacto del workflow.")
    print(f"[main] cuota de hoy llena: espero {espera / 60:.0f} min a que YouTube la reinicie")
    time.sleep(espera)


def crear_video(formato, tema=None, subir=True, prueba=False, tipo_largo="auto"):
    vertical = formato == "short"
    with db.Ejecucion(formato) as ej:
        ia.reiniciar_costos()
        es_lista = (not vertical and not tema and
                    (tipo_largo == "lista" or (tipo_largo == "auto" and random.random() < PROB_LISTA)))
        if es_lista:
            art = investigacion.elegir_lista()
        else:
            art = investigacion.elegir_tema(formato, tema)
        ej.nota(tema=art["titulo"])

        if vertical:
            g = guion.guion_short(art)
        elif es_lista:
            g = guion.guion_lista(art, prueba=prueba)
        else:
            g = guion.guion_largo(art, prueba=prueba)
        print(f"[main] título: {g['titulo']}")
        for e in g["escenas"][:12]:
            print(f"   · [{e['tipo']}] {e['narracion']}")

        vid_id = f"{dt.date.today().isoformat()}-{formato}-{slug(art['titulo'])}"
        carpeta = OUT / vid_id
        trabajo = carpeta / "trabajo"
        if trabajo.exists():
            shutil.rmtree(trabajo)
        trabajo.mkdir(parents=True)

        escenas = g["escenas"]
        if not vertical:  # pausa un poco más larga al cambiar de capítulo
            for a, b in zip(escenas, escenas[1:]):
                a["pausa_extra"] = a.get("capitulo") != b.get("capitulo")
        escenas, total_voz = voz.narrar(escenas, trabajo, rate=VOZ_RATE if vertical else VOZ_RATE_LARGO)
        print(f"[main] narración: {total_voz:.1f}s")

        capitulos = []
        if not vertical:
            vistos = set()
            for e in escenas:
                if e["capitulo"] not in vistos:
                    vistos.add(e["capitulo"])
                    capitulos.append((0.0 if not capitulos else e["inicio"], g["capitulos"][e["capitulo"]]))

        estilo = visuales.elegir_estilo()
        print(f"[main] estilo visual: {estilo['nombre']}")
        creditos = visuales.preparar(escenas, trabajo, vertical, estilo, 0.3 if vertical else 0.6)

        video = carpeta / ("short.mp4" if vertical else "video.mp4")
        info = montaje.montar(escenas, total_voz, trabajo, video, vertical, estilo,
                              gancho=g.get("gancho_pantalla", ""), capitulos=capitulos)

        mini, estilo_mini = None, None
        if not vertical:
            # Una imagen IA por capítulo (para el collage de las listas); la primera es la del gancho
            imagenes, caps_vistos = [], set()
            for e in escenas:
                if e["visual"] == "imagen" and e.get("capitulo") not in caps_vistos:
                    caps_vistos.add(e.get("capitulo"))
                    imagenes.append(e["archivo"])
            if es_lista and len(imagenes) > 3:  # una del caso más fuerte (el último) y dos de otros casos
                imagenes = [imagenes[-2], imagenes[1], imagenes[len(imagenes) // 2]]
            texto = g.get("texto_miniatura") or guion.corto(g["titulo"], 4)
            mini, estilo_mini = miniatura.crear(imagenes, texto, carpeta / "miniatura.jpg",
                                                numero=len(art["casos"]) if es_lista else None)

        meta = metadatos(g, art, formato, capitulos, creditos)
        registro = {
            "id": vid_id, "fecha": db.ahora(), "formato": formato, "estado": "creado",
            "tema": art["titulo"], "tema_clave": art.get("clave", art["titulo"]), "categoria": art.get("categoria"),
            "interes_wikipedia": art.get("interes"), "titulo_yt": meta["titulo"], "estructura": g.get("estructura"),
            "estilo": estilo["nombre"], "duracion": info["duracion"], "escenas": len(escenas),
            "clips_reales": len(creditos), "musica": info["musica"], "verificacion": g.get("verificacion"),
            "fuentes": list(dict.fromkeys(art.get("fuentes", []) + g.get("fuentes_extra", []))),
            "costo_usd": round(ia.COSTOS["usd"], 4), "ia": ia.COSTOS["llamadas"],
            "prueba": prueba,
        }
        if not vertical:
            registro.update(tipo_largo="lista" if es_lista else "caso", miniatura_estilo=estilo_mini)
            if es_lista:
                registro.update(lista_id=art["lista_id"], casos=[c["titulo"] for c in art["casos"]])
        (carpeta / "meta.json").write_text(json.dumps({**meta, "registro": registro, "guion": [
            {k: e.get(k) for k in ("capitulo", "tipo", "narracion", "imagen", "stock", "visual")} for e in escenas]},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if not prueba:
            db.guardar_video(registro)
        print(f"[main] video listo: {video} ({info['duracion']}s) · costo IA ${registro['costo_usd']:.3f}")

        # Filtro de calidad: Pollinations (respaldo sin clave) inventa datos con frecuencia; no publicamos eso
        solo_respaldo = all(c["proveedor"] == "pollinations" for c in ia.COSTOS["llamadas"])
        if subir and not prueba and solo_respaldo and not PUBLICAR_CON_RESPALDO:
            registro["estado"] = "retenido_calidad"
            db.guardar_video(registro)
            raise RuntimeError("Guion escrito solo por el respaldo gratuito (Pollinations): no se publica. "
                               "Configura ANTHROPIC_API_KEY o GEMINI_API_KEY (ver GUIA.md).")
        if subir and not prueba:
            if not youtube.credenciales_listas():
                print("[main] faltan credenciales de YouTube: el video no se sube (ver GUIA.md)")
            elif db.ya_subido(registro["tema_clave"], formato):
                print("[main] este tema ya se subió antes: no lo subo otra vez")
            else:
                if not vertical:
                    esperar_cupo_largo()
                ultimo = None
                for intento in range(3):
                    try:
                        res = youtube.subir(video, meta, mini)
                        registro.update(res)
                        db.guardar_video(registro)
                        (OUT / "SUBIDO").write_text(registro.get("youtube_id", ""), encoding="utf-8")
                        break
                    except Exception as e:  # noqa: BLE001
                        ultimo = e
                        print(f"[main] subida falló (intento {intento + 1}): {e}")
                else:
                    registro["estado"] = "error_subida"
                    db.guardar_video(registro)
                    raise RuntimeError(f"No se pudo subir a YouTube: {ultimo}")
        ej.nota(video=vid_id, estado_video=registro["estado"], costo_usd=registro["costo_usd"])
    return registro


def main():
    ap = argparse.ArgumentParser(description="Sistema autónomo de YouTube — Misterios Sin Resolver")
    ap.add_argument("accion", choices=["short", "largo", "estadisticas", "panel"])
    ap.add_argument("--tema", help="Título del artículo de Wikipedia en inglés")
    ap.add_argument("--no-subir", action="store_true")
    ap.add_argument("--prueba", action="store_true", help="Video corto de prueba (no se registra ni se sube)")
    ap.add_argument("--tipo", choices=["auto", "caso", "lista"], default="auto",
                    help="Video largo: caso a fondo, lista de 5-7 casos o al azar (auto)")
    ap.add_argument("--programado", action="store_true",
                    help="Ejecución automática: solo crea el short si hace falta (ver hace_falta_short)")
    args = ap.parse_args()

    if args.programado and args.accion == "short" and not hace_falta_short():
        return 0
    try:
        if args.accion in ("short", "largo"):
            crear_video(args.accion, args.tema, subir=not args.no_subir, prueba=args.prueba, tipo_largo=args.tipo)
        elif args.accion == "estadisticas":
            with db.Ejecucion("estadisticas"):
                from . import estadisticas
                if youtube.credenciales_listas():
                    estadisticas.actualizar()
                else:
                    print("[main] sin credenciales de YouTube: solo analizo lo guardado")
                    estadisticas.analizar()
    finally:
        panel.generar()  # el panel se actualiza siempre, también cuando algo falla
    return 0


if __name__ == "__main__":
    sys.exit(main())
