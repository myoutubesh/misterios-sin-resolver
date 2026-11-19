"""Guiones para shorts y videos largos.

Proceso: borrador → editor (español, ritmo, gancho, fidelidad a la fuente) → verificación de datos
(con Claude + búsqueda web, si hay clave). El editor y el verificador devuelven solo correcciones.
"""
import json
import random
import re

from . import db, ia
from .config import ANTHROPIC_API_KEY, CANAL, CLAUDE_VERIFICAR, DATA

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


def guia_contenido():
    """Guía de estilo editable en data/guia_contenido.md (se actualiza con lo que se aprende del mercado)."""
    try:
        return (DATA / "guia_contenido.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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
    g["hashtags"] = [re.sub(r"\W", "", h) for h in (g.get("hashtags") or []) if isinstance(h, str)][:14]
    g["tags"] = [limpiar(t) for t in (g.get("tags") or []) if isinstance(t, str)][:30]
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

ANTES QUE NADA: ¿el guion cuenta el MISMO caso del que habla la FUENTE, y sus hechos principales están en
la FUENTE? Si el guion habla de otra cosa, o su historia central no aparece en la FUENTE (por ejemplo, una
anécdota que no está ahí), responde "fiel_a_fuente": false y explica por qué en "problema". Ese guion no se
publicará.

Responde SOLO con JSON:
{{"fiel_a_fuente": true, "problema": "",
  "correcciones": [{{"i": 0, "narracion": "texto corregido", "tipo": "hecho|hipotesis|leyenda"}}],
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


class GuionNoFiel(RuntimeError):
    pass


def _revisar(g, art, formato, extra):
    fuente = (art["texto_en"] + "\n\n" + (art["texto_es"] or ""))[:40000]
    try:
        resp = ia.generar_json(EDITOR.format(canal=CANAL, formato=formato, titulo=art["titulo"], extra=extra,
                                             guion=_vista(g), fuente=fuente), intentos=1)
    except Exception as e:  # noqa: BLE001
        resp = None
        print(f"[guion] editor no disponible ({e}); sigo con el borrador")
    if resp is None and art.get("reddit"):
        raise GuionNoFiel("tema de Reddit sin revisión del editor: no lo publico")
    if resp is not None and resp.get("fiel_a_fuente") is False:
        # Candado: nunca publicar un guion que no sale de la fuente
        raise GuionNoFiel(f"el editor detectó que el guion no sale de la fuente: {resp.get('problema', '')[:200]}")
    try:
        if resp is not None:
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

Escribe UN YouTube Short de 35 a 50 segundos sobre el caso de abajo (categoría: {categoria}).

ESTRUCTURA DE ESTE VIDEO: {estructura}
{reddit}
{guia}

RETENCIÓN (resumen obligatorio)
- Primera frase = gancho de máximo 10 palabras, concreto y anómalo. Sin saludos ni "hoy te cuento".
- Total: 100 a 135 palabras. 6 a 9 escenas de 1 o 2 frases (máximo 22 palabras por escena).
- Penúltima escena: la pregunta sin resolver del caso. Última escena (muy corta): cierra el círculo con la
  primera frase e invita a comentar con una pregunta concreta. {cta}

{reglas}
METADATOS
- "titulo": máximo 60 caracteres, curiosidad honesta, sin hashtags, sin mayúsculas sostenidas, sin mentir.
- "gancho_pantalla": 2 a 5 palabras en MAYÚSCULAS para mostrar arriba los primeros segundos.
- "descripcion": 2 o 3 frases que presenten el caso sin revelar el final.
- "hashtags": 12 hashtags sin #, TODOS relacionados con este video, en una sola palabra cada uno (sin
  espacios). Mezcla: 4 específicos del caso (nombre del caso, lugar, año o persona, ej. DyatlovPass,
  Rusia1959), 4 del tipo de misterio (ej. DesaparicionesMisteriosas, CasosSinResolver, Criptozoologia) y
  4 amplios de la temática con mucha búsqueda en español (ej. Misterio, Paranormal, HistoriasReales,
  DatosCuriosos). Nada que no tenga que ver con el video.
- "tags": 20 etiquetas de búsqueda en español (frases que la gente escribiría para encontrar este caso,
  incluyendo el nombre del caso en español y en inglés).
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
    reddit = ""
    if art.get("reddit"):
        reddit = (f"\nPOR QUÉ ESTE TEMA: esta semana se comenta mucho en r/{art['reddit']['sub']} con el título "
                  f"\"{art['reddit']['titulo']}\". Úsalo solo como pista de qué le intriga a la gente; no copies "
                  "textos de usuarios y usa solo datos de la FUENTE. Si la FUENTE no habla de lo mismo que el "
                  "post, ignora el post por completo y cuenta solo lo que dice la FUENTE.\n")
    cta = (f"En este video sí invita a suscribirse a {CANAL}, en pocas palabras." if random.random() < 0.34
           else "En este video NO pidas suscripción.")
    prompt = PROMPT_SHORT.format(canal=CANAL, categoria=art.get("categoria", ""), estructura=estructura,
                                 reddit=reddit, guia=guia_contenido(), cta=cta, reglas=REGLAS_COMUNES, aprendizajes=_aprendizajes("short"), titulo=art["titulo"],
                                 texto_en=art["texto_en"], texto_es=art["texto_es"] or "(no hay)")
    g = ia.generar_json(prompt, validar=lambda d: _normalizar(d, 5, 11, 90, 185))
    g = _revisar(g, art, "YouTube Short de 45 segundos",
                 "Que la primera frase sea un gancho concreto de máximo 10 palabras, que 'gancho_pantalla' añada "
                 "la duda sin repetir la voz, que no haya frases de relleno y que la última frase conecte con la primera.")
    g["estructura"] = nombre
    return g


# ---------- VIDEO LARGO ----------
PROMPT_LARGO = """Eres el guionista principal de "{canal}", canal documental de YouTube en español sobre misterios
reales, casos sin resolver, fenómenos paranormales, lugares misteriosos, leyendas y civilizaciones antiguas.

Escribe el guion de un VIDEO DOCUMENTAL de 14 a 18 minutos sobre el caso de abajo (categoría: {categoria}).

ESTRUCTURA
1. Introducción (60-90 s): abre con la escena más intrigante, plantea la gran pregunta y promete qué se va a
   descubrir. No saludes ni pidas suscripción al inicio.
2. De 5 a 7 capítulos con títulos cortos (contexto, los hechos, la investigación, las teorías, lo que sigue sin
   explicación…). Cada capítulo cierra con una pregunta o giro que empuje al siguiente.
3. Cierre (45-60 s): resume qué es hecho, qué es teoría y qué sigue abierto; invita a comentar su teoría,
   a suscribirse a {canal} y a ver el siguiente video.

ESTILO: narración documental, intrigante y natural, como un buen podcast de misterio. Variedad de ritmo:
frases cortas en momentos de tensión, más largas al explicar contexto.

LONGITUD: 2,000 a 2,600 palabras en total, divididas en 65 a 95 escenas de 1 a 3 frases (15 a 40 palabras).
Aprovecha TODO el material de la fuente (contexto histórico, personas involucradas, cronología, investigaciones,
cada teoría con sus pruebas a favor y en contra). Nada de relleno ni repeticiones para alargar.
Cada escena indica a qué capítulo pertenece ("capitulo": índice desde 0; la introducción es el capítulo 0).

{reglas}
METADATOS
- "titulo": máximo 80 caracteres con este patrón: gancho honesto + " | " + nombre del caso con el que la gente
  lo buscaría. Ej.: "El avión que desapareció y volvió 37 años después | Pan Am 914". Como mucho UNA palabra
  en MAYÚSCULAS para dar fuerza.
- "texto_miniatura": 2 a 4 palabras impactantes y honestas para la miniatura (en mayúsculas).
- "capitulos": lista de títulos de capítulo (el primero es "Introducción").
- "descripcion": 4 a 6 frases para YouTube (sin revelar el final).
- "hashtags": 12 sin #, todos relacionados con el caso (específicos del caso, del tipo de misterio y
  amplios de la temática). "tags": 20 etiquetas de búsqueda en español.
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
    minimos = (6, 20, 120, 600) if prueba else (50, 120, 1700, 3100)
    prompt = PROMPT_LARGO.format(canal=CANAL, categoria=art.get("categoria", ""), reglas=REGLAS_COMUNES,
                                 aprendizajes=_aprendizajes("largo"), titulo=art["titulo"],
                                 texto_en=art["texto_en"], texto_es=art["texto_es"] or "(no hay)")
    if prueba:
        prompt = prompt.replace("2,000 a 2,600 palabras en total, divididas en 65 a 95 escenas",
                                "PRUEBA CORTA: 200 a 350 palabras en total, divididas en 8 a 12 escenas") \
                       .replace("De 5 a 7 capítulos", "2 capítulos")
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


# ---------- VIDEO LARGO TIPO LISTA ----------
PROMPT_LISTA = """Eres el guionista principal de "{canal}", canal documental de YouTube en español sobre misterios
reales, leyendas, fenómenos sin explicar y casos sin resolver.

Escribe el guion de un VIDEO LISTA de 16 a 20 minutos: "{titulo}". Tienes {n} casos (abajo, cada uno con su fuente).

ESTRUCTURA
1. Introducción (40-60 s, capítulo 0): abre con un detalle concreto del caso más fuerte, sin decir cuál es,
   y promete que el último es el más inquietante. No saludes ni pidas suscripción al inicio.
2. Un capítulo por caso (capítulos 1 a {n}), ordenados del MENOS al MÁS inquietante. Cada caso: dónde y cuándo,
   qué pasó o qué cuenta la leyenda, qué detalles lo hacen raro, qué explicaciones hay y qué sigue sin
   explicación. Cierra cada caso con una frase que empuje al siguiente ("pero lo que pasó en … es peor").
3. Cierre (30-45 s, capítulo {cierre}): cuál te parece más difícil de explicar, pregunta concreta para
   comentarios, invitación a suscribirse a {canal}.

ESTILO: narración documental, intrigante y natural. Frases cortas en los momentos de tensión.

LONGITUD: 2,100 a 2,900 palabras en total (unas 300 a 380 por caso), divididas en 70 a 110 escenas de 1 a 3
frases (15 a 40 palabras). Cada escena indica su capítulo ("capitulo": índice desde 0).

{reglas}
- Cada caso usa SOLO los datos de SU fuente. No mezcles datos entre casos.
- Si un caso es leyenda o folclore, narra "según la leyenda…", "cuentan que…": nunca como hecho.

METADATOS
- "titulo": máximo 80 caracteres: el número + el tema + algo que dé curiosidad honesta. Como mucho UNA palabra
  en MAYÚSCULAS. Ej.: "7 leyendas de México que todavía dan miedo", "7 barcos encontrados sin nadie a bordo".
- "texto_miniatura": 2 a 4 palabras para la franja de la miniatura (en mayúsculas), sin el número.
  Ej.: "LEYENDAS DE MÉXICO".
- "capitulos": lista de {total_caps} títulos: "Introducción", luego "1. Nombre corto del caso", "2. …" en el orden
  en que los cuentas, y al final "Conclusión".
- "descripcion": 4 a 6 frases para YouTube (sin revelar cuál es el último caso).
- "hashtags": 12 sin #, relacionados con los casos y el tema. "tags": 20 etiquetas de búsqueda en español.
{aprendizajes}
Responde SOLO con JSON:
{{"titulo": "", "texto_miniatura": "", "descripcion": "", "hashtags": [], "tags": [], "capitulos": [],
  "escenas": [{{"capitulo": 0, "narracion": "", "tipo": "hecho", "imagen": "", "stock": ""}}]}}

FUENTES (una por caso):
{fuente}
"""


def guion_lista(art, prueba=False):
    n = len(art["casos"])
    prompt = PROMPT_LISTA.format(canal=CANAL, titulo=art["titulo"], n=n, cierre=n + 1, total_caps=n + 2,
                                 reglas=REGLAS_COMUNES, aprendizajes=_aprendizajes("largo"), fuente=art["texto_en"])
    minimos = (n + 4, 40, 300, 1400) if prueba else (55, 130, 1800, 3400)
    if prueba:
        prompt = prompt.replace("2,100 a 2,900 palabras en total (unas 300 a 380 por caso), divididas en 70 a 110 escenas",
                                "PRUEBA CORTA: 350 a 700 palabras en total (unas 60 por caso), divididas en "
                                f"{n + 4} a 30 escenas")
    g = ia.generar_json(prompt, max_tokens=56000, validar=lambda d: _normalizar(d, *minimos))
    caps = [limpiar(c) for c in (g.get("capitulos") or []) if isinstance(c, str)] or ["Introducción"]
    for e in g["escenas"]:
        try:
            e["capitulo"] = max(0, min(int(e.get("capitulo", 0)), len(caps) - 1))
        except (TypeError, ValueError):
            e["capitulo"] = 0
    g["capitulos"] = caps
    g = _revisar(g, art, "video largo tipo lista (varios casos, cada uno con su fuente)",
                 "Que cada caso use solo datos de SU fuente, que el título tenga el número correcto de casos y que "
                 "'texto_miniatura' sea honesto.")
    if not re.match(rf"\s*{n}\b", g["titulo"]):
        g["titulo"] = f"{n} " + re.sub(r"^\s*\d+\s*", "", g["titulo"])
    return g
