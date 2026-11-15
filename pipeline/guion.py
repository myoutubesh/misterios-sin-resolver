"""Guiones para shorts y videos largos.

Proceso: borrador → editor (español, ritmo, gancho, fidelidad a la fuente) → verificación de datos
(con Claude + búsqueda web, si hay clave). El editor y el verificador devuelven solo correcciones.
"""
import json
import random
import re

from . import db, ia
from .config import ANTHROPIC_API_KEY, CANAL, CLAUDE_VERIFICAR

ESTRUCTURAS_SHORT = {
    "cronologica": "Cuenta el caso en orden, pero abre con el detalle más extraño y vuelve atrás.",
    "en_medias_res": "Empieza en el momento más tenso del caso, como si estuviera pasando ahora, y luego explica cómo se llegó ahí.",
    "pregunta": "Abre con una pregunta directa al espectador que el caso responde a medias.",
    "tres_detalles": "Organízalo como tres detalles inquietantes, del menos al más perturbador.",
    "segunda_persona": "Narra en segunda persona en el inicio ('Imagina que eres…') y luego pasa a los hechos.",
}

REGLAS_COMUNES = """REGLAS DE VERDAD (obligatorias)
- Usa SOLO hechos que aparezcan en la FUENTE. No inventes fechas, nombres, cifras ni citas.
- Distingue siempre: HECHO comprobado, HIPÓTESIS (teorías: "una teoría dice…", "algunos investigadores creen…")
  y LEYENDA (folclore: "según la leyenda…", "cuentan que…"). Nunca presentes una teoría o leyenda como hecho.
- En conspiraciones, explica qué se afirma y qué dicen las pruebas; no promuevas desinformación.
- Respeto a víctimas y familias: sin detalles gráficos, sin sangre, sin describir cadáveres.
- No acuses de un crimen a ninguna persona real que no haya sido condenada.
- Español latino neutro y natural, frases cortas, palabras sencillas. Años con números (1959). Sin emojis ni markdown.

IMÁGENES (por escena)
- "imagen": prompt EN INGLÉS de 20 a 40 palabras con lo que se ve (lugar, objetos, época, clima, encuadre).
  Personas solo como siluetas, de espaldas o lejanas. Nunca el retrato de una persona real, texto ni violencia.
- "stock": 2 a 4 palabras EN INGLÉS para buscar un clip real de archivo (ej. "foggy pine forest", "old ship deck", "snowy mountain night").
- "tipo": "hecho", "hipotesis" o "leyenda".
"""


def _aprendizajes(formato):
    a = db.leer(db.APRENDIZAJES, {})
    partes = []
    if a.get("titulos_top", {}).get(formato):
        partes.append("Títulos que mejor funcionaron en el canal: " + " | ".join(a["titulos_top"][formato][:5]))
    if a.get("consejos"):
        partes.append("Observaciones del análisis de estadísticas: " + " ".join(a["consejos"][:4]))
    return ("\nLO QUE FUNCIONA EN ESTE CANAL (úsalo como guía, sin copiar):\n" + "\n".join(partes) + "\n") if partes else ""


_RAROS = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)


def limpiar(s):
    s = (s or "").translate(_RAROS).replace("*", "").replace("_", " ").replace("#", "")
    return re.sub(r"\s+", " ", s).strip()


def corto(texto, max_palabras):
    palabras = limpiar(texto).upper().split()[:max_palabras]
    vacias = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "EN", "Y", "A", "QUE", "UN", "UNA", "POR", "CON", "SU"}
    while len(palabras) > 1 and palabras[-1].strip(",.;:") in vacias:
        palabras.pop()
    return " ".join(palabras).rstrip(",.;:")


def _palabras(escenas):
    return sum(len(e["narracion"].split()) for e in escenas)


def _normalizar(g, min_esc, max_esc, min_pal, max_pal):
    escenas = [e for e in (g.get("escenas") or []) if isinstance(e, dict)]
    for e in escenas:
        e["narracion"] = limpiar(e.get("narracion"))
        e["imagen"] = limpiar(e.get("imagen"))
        e["stock"] = limpiar(e.get("stock")) or "dark foggy landscape"
        e["tipo"] = e.get("tipo") if e.get("tipo") in ("hecho", "hipotesis", "leyenda") else "hecho"
        if not e["narracion"] or not e["imagen"]:
            raise ValueError("escena incompleta")
    if not (min_esc <= len(escenas) <= max_esc):
        raise ValueError(f"{len(escenas)} escenas (esperaba {min_esc}-{max_esc})")
    p = _palabras(escenas)
    if not (min_pal <= p <= max_pal):
        raise ValueError(f"{p} palabras (esperaba {min_pal}-{max_pal})")
    g["escenas"] = escenas
    for k in ("titulo", "descripcion"):
        if not g.get(k):
            raise ValueError(f"falta {k}")
        g[k] = limpiar(g[k]) if k == "titulo" else g[k].strip()
    g["gancho_pantalla"] = corto(g.get("gancho_pantalla"), 5)
    g["texto_miniatura"] = corto(g.get("texto_miniatura"), 4)
    g["hashtags"] = [re.sub(r"\W", "", h) for h in (g.get("hashtags") or []) if isinstance(h, str)][:6]
    g["tags"] = [limpiar(t) for t in (g.get("tags") or []) if isinstance(t, str)][:15]
    return g


# ---------- correcciones (editor y verificador) ----------
def _aplicar(g, resp, etiqueta):
    n = 0
    for c in resp.get("correcciones") or []:
        try:
            i = int(c["i"])
            if 0 <= i < len(g["escenas"]) and c.get("narracion"):
                g["escenas"][i]["narracion"] = limpiar(c["narracion"])
                if c.get("tipo") in ("hecho", "hipotesis", "leyenda"):
                    g["escenas"][i]["tipo"] = c["tipo"]
                n += 1
        except (KeyError, ValueError, TypeError):
            continue
    if resp.get("titulo"):
        g["titulo"] = limpiar(resp["titulo"])[:100]
    if resp.get("gancho_pantalla"):
        g["gancho_pantalla"] = corto(resp["gancho_pantalla"], 5)
    if resp.get("texto_miniatura"):
        g["texto_miniatura"] = corto(resp["texto_miniatura"], 4)
    print(f"[guion] {etiqueta}: {n} correcciones")
    return g


def _vista(g):
    return json.dumps({"titulo": g["titulo"], "gancho_pantalla": g.get("gancho_pantalla"),
                       "escenas": [{"i": i, "tipo": e["tipo"], "narracion": e["narracion"]}
                                   for i, e in enumerate(g["escenas"])]}, ensure_ascii=False, indent=1)


EDITOR = """Eres el editor jefe de "{canal}". Revisa este guion ({formato}) sobre "{titulo}".

Busca y corrige:
1. Errores de español: palabras inventadas o en inglés, concordancia, frases que suenan raras en voz alta.
2. Datos que NO están en la FUENTE o están mal (fechas, cifras, lugares, quién hizo qué, orden de hechos).
3. Teorías o leyendas presentadas como hechos: reescríbelas con "una teoría dice…", "según la leyenda…".
4. {extra}

No cambies lo que ya está bien. Mantén la longitud de cada escena parecida.
Responde SOLO con JSON:
{{"correcciones": [{{"i": 0, "narracion": "texto corregido", "tipo": "hecho|hipotesis|leyenda"}}],
  "titulo": "solo si lo mejoras", "gancho_pantalla": "solo si lo mejoras", "texto_miniatura": "solo si lo mejoras"}}

GUION:
{guion}

FUENTE:
{fuente}
"""

VERIFICADOR = """Eres verificador de datos de "{canal}". Comprueba con búsquedas web (fuentes confiables:
enciclopedias, medios reconocidos, documentos oficiales, publicaciones académicas) las fechas, nombres, lugares
y cifras de este guion sobre "{titulo}". Haz como máximo 5 búsquedas, sobre los datos más importantes.

Si un dato es incorrecto o no se puede confirmar, corrígelo o suavízalo ("según algunos reportes…").
Si algo es teoría o leyenda, que la narración lo diga.

Responde SOLO con JSON:
{{"correcciones": [{{"i": 0, "narracion": "texto corregido", "tipo": "hecho|hipotesis|leyenda"}}],
  "fuentes": ["url1", "url2"], "nota": "resumen de lo verificado en una frase"}}

GUION:
{guion}
"""


def _revisar(g, art, formato, extra):
    fuente = (art["texto_en"] + "\n\n" + (art["texto_es"] or ""))[:40000]
    try:
        resp = ia.generar_json(EDITOR.format(canal=CANAL, formato=formato, titulo=art["titulo"], extra=extra,
                                             guion=_vista(g), fuente=fuente), intentos=1)
        g = _aplicar(g, resp, "editor")
    except Exception as e:  # noqa: BLE001
        print(f"[guion] editor no disponible ({e}); sigo con el borrador")
    g["verificacion"] = "solo contra Wikipedia (EN y ES)"
    if ANTHROPIC_API_KEY and CLAUDE_VERIFICAR:
        try:
            resp = ia.generar_json(VERIFICADOR.format(canal=CANAL, titulo=art["titulo"], guion=_vista(g)),
                                   intentos=1, buscar_web=True, solo_claude=True)
            g = _aplicar(g, resp, "verificador")
            g["fuentes_extra"] = [u for u in (resp.get("fuentes") or []) if isinstance(u, str)][:8]
            g["verificacion"] = resp.get("nota") or "verificado con búsqueda web"
        except Exception as e:  # noqa: BLE001
            print(f"[guion] verificación web no disponible ({e})")
    return g


# ---------- SHORT ----------
PROMPT_SHORT = """Eres el guionista de "{canal}", canal de YouTube en español sobre misterios reales, casos sin
resolver, fenómenos paranormales, lugares misteriosos, leyendas, civilizaciones antiguas y teorías.

Escribe UN YouTube Short de 40 a 55 segundos sobre el caso de abajo (categoría: {categoria}).

ESTRUCTURA DE ESTE VIDEO: {estructura}

RETENCIÓN
- Primera frase = gancho de máximo 12 palabras con el dato más raro o inquietante. Sin saludos ni "hoy te cuento".
- Crea preguntas abiertas y respóndelas más adelante. Ritmo de suspenso.
- Total: 115 a 145 palabras. 7 a 9 escenas de 1 o 2 frases (máximo 24 palabras por escena).
- Penúltima escena: la pregunta sin resolver del caso. Última escena (corta): invita a comentar su teoría
  y a suscribirse a {canal}, de forma natural y variada (no siempre la misma frase).

{reglas}
METADATOS
- "titulo": máximo 60 caracteres, curiosidad honesta, sin hashtags, sin mayúsculas sostenidas, sin mentir.
- "gancho_pantalla": 2 a 5 palabras en MAYÚSCULAS para mostrar arriba los primeros segundos.
- "descripcion": 2 o 3 frases que presenten el caso sin revelar el final.
- "hashtags": 5 en español, sin #. "tags": 10 etiquetas de búsqueda en español.
{aprendizajes}
Responde SOLO con JSON:
{{"titulo": "", "gancho_pantalla": "", "descripcion": "", "hashtags": [], "tags": [],
  "escenas": [{{"narracion": "", "tipo": "hecho", "imagen": "", "stock": ""}}]}}

CASO: {titulo}

FUENTE (Wikipedia en inglés):
{texto_en}

FUENTE (Wikipedia en español):
{texto_es}
"""


def guion_short(art):
    nombre, estructura = random.choice(list(ESTRUCTURAS_SHORT.items()))
    prompt = PROMPT_SHORT.format(canal=CANAL, categoria=art.get("categoria", ""), estructura=estructura,
                                 reglas=REGLAS_COMUNES, aprendizajes=_aprendizajes("short"), titulo=art["titulo"],
                                 texto_en=art["texto_en"], texto_es=art["texto_es"] or "(no hay)")
    g = ia.generar_json(prompt, validar=lambda d: _normalizar(d, 5, 11, 90, 185))
    g = _revisar(g, art, "YouTube Short de 45 segundos",
                 "Que la primera frase sea un gancho fuerte de máximo 12 palabras y que 'gancho_pantalla' se entienda solo.")
    g["estructura"] = nombre
    return g


# ---------- VIDEO LARGO ----------
PROMPT_LARGO = """Eres el guionista principal de "{canal}", canal documental de YouTube en español sobre misterios
reales, casos sin resolver, fenómenos paranormales, lugares misteriosos, leyendas y civilizaciones antiguas.

Escribe el guion de un VIDEO DOCUMENTAL de 9 a 12 minutos sobre el caso de abajo (categoría: {categoria}).

ESTRUCTURA
1. Introducción (60-90 s): abre con la escena más intrigante, plantea la gran pregunta y promete qué se va a
   descubrir. No saludes ni pidas suscripción al inicio.
2. De 4 a 6 capítulos con títulos cortos (contexto, los hechos, la investigación, las teorías, lo que sigue sin
   explicación…). Cada capítulo cierra con una pregunta o giro que empuje al siguiente.
3. Cierre (45-60 s): resume qué es hecho, qué es teoría y qué sigue abierto; invita a comentar su teoría,
   a suscribirse a {canal} y a ver el siguiente video.

ESTILO: narración documental, intrigante y natural, como un buen podcast de misterio. Variedad de ritmo:
frases cortas en momentos de tensión, más largas al explicar contexto.

LONGITUD: 1,350 a 1,800 palabras en total, divididas en 45 a 70 escenas de 1 a 3 frases (15 a 40 palabras).
Cada escena indica a qué capítulo pertenece ("capitulo": índice desde 0; la introducción es el capítulo 0).

{reglas}
METADATOS
- "titulo": máximo 70 caracteres, con la palabra clave principal al inicio, curiosidad honesta.
- "texto_miniatura": 2 a 4 palabras impactantes y honestas para la miniatura (en mayúsculas).
- "capitulos": lista de títulos de capítulo (el primero es "Introducción").
- "descripcion": 4 a 6 frases para YouTube (sin revelar el final).
- "hashtags": 5 sin #. "tags": 15 etiquetas de búsqueda en español.
{aprendizajes}
Responde SOLO con JSON:
{{"titulo": "", "texto_miniatura": "", "descripcion": "", "hashtags": [], "tags": [], "capitulos": [],
  "escenas": [{{"capitulo": 0, "narracion": "", "tipo": "hecho", "imagen": "", "stock": ""}}]}}

CASO: {titulo}

FUENTE (Wikipedia en inglés):
{texto_en}

FUENTE (Wikipedia en español):
{texto_es}
"""


def guion_largo(art, prueba=False):
    minimos = (6, 20, 120, 600) if prueba else (35, 90, 1100, 2300)
    prompt = PROMPT_LARGO.format(canal=CANAL, categoria=art.get("categoria", ""), reglas=REGLAS_COMUNES,
                                 aprendizajes=_aprendizajes("largo"), titulo=art["titulo"],
                                 texto_en=art["texto_en"], texto_es=art["texto_es"] or "(no hay)")
    if prueba:
        prompt = prompt.replace("1,350 a 1,800 palabras en total, divididas en 45 a 70 escenas",
                                "PRUEBA CORTA: 200 a 350 palabras en total, divididas en 8 a 12 escenas") \
                       .replace("De 4 a 6 capítulos", "2 capítulos")
    g = ia.generar_json(prompt, max_tokens=48000, validar=lambda d: _normalizar(d, *minimos))
    caps = [limpiar(c) for c in (g.get("capitulos") or []) if isinstance(c, str)] or ["Introducción"]
    for e in g["escenas"]:
        try:
            e["capitulo"] = max(0, min(int(e.get("capitulo", 0)), len(caps) - 1))
        except (TypeError, ValueError):
            e["capitulo"] = 0
    g["capitulos"] = caps
    g = _revisar(g, art, "video documental largo",
                 "Que la introducción enganche en los primeros 15 segundos y que 'texto_miniatura' sea honesto (nada de clickbait falso).")
    return g
