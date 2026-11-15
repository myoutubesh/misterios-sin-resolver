"""Investigación automática: elige el tema del video y reúne la fuente.

Cómo decide:
  1. Elige una categoría (desapariciones, paranormal, leyendas…), con más peso para las que mejor
     funcionan en tu canal (data/aprendizajes.json) y sin repetir la de los últimos videos.
  2. Junta candidatos: lista curada (data/temas.json) + artículos de categorías de Wikipedia.
  3. Mide el interés de cada candidato con las visitas en Wikipedia de los últimos 60 días
     (API pública de Wikimedia) y elige uno con buen interés, sin repetir temas ya usados.
  4. Descarga el artículo en inglés y en español (dos fuentes que se contrastan entre sí).
"""
import datetime as dt
import json
import math
import random
import re
import time
import urllib.parse

import requests

from . import db
from .config import DATA, USER_AGENT

H = {"User-Agent": USER_AGENT}
SEMILLAS = DATA / "temas.json"

# Categorías de Wikipedia (inglés) para descubrir temas nuevos cuando se acaba la lista curada
CATEGORIAS_WIKI = {
    "desapariciones": ["Category:Unexplained disappearances"],
    "fenomenos": ["Category:Unexplained phenomena"],
    "paranormal": ["Category:Paranormal"],
    "leyendas": ["Category:Urban legends"],
    "civilizaciones": ["Category:Undeciphered writing systems"],
    "conspiraciones": ["Category:Conspiracy theories"],
    "lugares": ["Category:Ghost ships"],
    "curiosidades": ["Category:Cryptids"],
}

# Temas que no tocamos: desinformación dañina o que viola políticas de YouTube
PROHIBIDO = re.compile(
    r"vaccin|vacun|covid|coronavirus|\b5g\b|chemtrail|holocaust|\bjew|judí|antisemit|stolen election|"
    r"sandy hook|school shooting|tiroteo escolar|qanon|pizzagate|flat earth|white genocide|"
    r"great replacement|self-harm", re.I)


def _api(lang, **params):
    params.update(format="json", formatversion=2)
    for intento in range(4):
        try:
            r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers=H, timeout=30)
            if r.ok and r.text.strip().startswith("{"):
                return r.json()
        except requests.RequestException as e:
            print(f"[investigacion] wikipedia: {e}")
        time.sleep(3 * (intento + 1))
    raise RuntimeError("Wikipedia no respondió")


def _limpiar(texto):
    texto = re.split(r"\n==+ ?(See also|References|External links|Further reading|Notes|Bibliography|Sources|"
                     r"Véase también|Referencias|Enlaces externos|Bibliografía|Notas)\b", texto)[0]
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def traer_articulo(titulo, largo=False):
    limite_en, limite_es = (32000, 14000) if largo else (10000, 5000)
    d = _api("en", action="query", prop="extracts|langlinks|info", explaintext=1, redirects=1,
             titles=titulo, lllang="es", inprop="url")
    page = d["query"]["pages"][0]
    if page.get("missing"):
        return None
    info = {"titulo": page["title"], "url": page.get("fullurl"),
            "texto_en": _limpiar(page.get("extract", ""))[:limite_en], "texto_es": "", "url_es": None}
    links = page.get("langlinks") or []
    if links:
        e = _api("es", action="query", prop="extracts|info", explaintext=1, titles=links[0]["title"], inprop="url")
        ep = e["query"]["pages"][0]
        info["texto_es"] = _limpiar(ep.get("extract", ""))[:limite_es]
        info["url_es"] = ep.get("fullurl")
    info["fuentes"] = [u for u in (info["url"], info["url_es"]) if u]
    return info


def visitas(titulo, dias=60):
    fin = dt.date.today() - dt.timedelta(days=1)
    ini = fin - dt.timedelta(days=dias)
    t = urllib.parse.quote(titulo.replace(" ", "_"), safe="")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
           f"{t}/daily/{ini:%Y%m%d}/{fin:%Y%m%d}")
    try:
        r = requests.get(url, headers=H, timeout=20)
        if r.ok:
            return sum(i["views"] for i in r.json().get("items", []))
    except requests.RequestException:
        pass
    return 0


def _miembros(categoria):
    try:
        d = _api("en", action="query", list="categorymembers", cmtitle=categoria, cmlimit=500, cmnamespace=0)
        return [m["title"] for m in d["query"]["categorymembers"]
                if not m["title"].lower().startswith(("list of", "lists of"))]
    except Exception as e:  # noqa: BLE001
        print(f"[investigacion] no pude leer {categoria}: {e}")
        return []


def _elegir_categoria(semillas, formato):
    aprend = db.leer(db.APRENDIZAJES, {})
    pesos = aprend.get("peso_categoria", {})
    recientes = [v.get("categoria") for v in db.videos()[-2:] if v.get("formato") == formato]
    cats = [c for c in semillas if c not in recientes] or list(semillas)
    if random.random() < 0.25:  # 25 % exploración: probar categorías aunque no sean las favoritas
        return random.choice(cats)
    w = [max(0.2, float(pesos.get(c, 1.0))) for c in cats]
    return random.choices(cats, weights=w, k=1)[0]


def elegir_tema(formato="short", forzar=None):
    largo = formato == "largo"
    usados = db.temas_usados()

    if forzar:
        art = traer_articulo(forzar, largo)
        if not art:
            raise SystemExit(f"No encontré '{forzar}' en Wikipedia (usa el título en inglés).")
        art.update(clave=art["titulo"], categoria="pedido")
        return art

    semillas = json.loads(SEMILLAS.read_text(encoding="utf-8"))
    for _ in range(4):  # si una categoría se agotó, prueba otra
        categoria = _elegir_categoria(semillas, formato)
        candidatos = [t for t in semillas[categoria] if t.lower() not in usados]
        if len(candidatos) < 4:
            for cat in CATEGORIAS_WIKI.get(categoria, []):
                candidatos += [t for t in _miembros(cat) if t.lower() not in usados]
        candidatos = [t for t in dict.fromkeys(candidatos) if not PROHIBIDO.search(t)]
        if not candidatos:
            continue
        muestra = random.sample(candidatos, min(8, len(candidatos)))
        puntuados = sorted(((math.log10(visitas(t) + 10) * random.uniform(0.8, 1.2), t) for t in muestra),
                           reverse=True)
        for puntos, titulo in puntuados:
            try:
                art = traer_articulo(titulo, largo)
            except Exception as e:  # noqa: BLE001
                print(f"[investigacion] error con {titulo}: {e}")
                continue
            if not art or art["titulo"].lower() in usados or PROHIBIDO.search(art["texto_en"][:600]):
                continue
            minimo = 9000 if largo else 2500
            if len(art["texto_en"]) + len(art["texto_es"]) < minimo:
                print(f"[investigacion] {titulo}: poco material, salto")
                continue
            art.update(clave=titulo, categoria=categoria, interes=round(puntos, 2))
            print(f"[investigacion] categoría {categoria} → {art['titulo']} (interés {puntos:.2f})")
            return art
    raise RuntimeError("No encontré un tema nuevo. Agrega más en data/temas.json")
