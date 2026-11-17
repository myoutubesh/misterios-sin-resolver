"""Capa única de IA de texto. Usa el primer proveedor disponible:

  1. Claude API (si hay ANTHROPIC_API_KEY): mejor calidad + verificación con búsqueda web.
  2. Gemini (si hay GEMINI_API_KEY): plan gratis con límites diarios.
  3. Pollinations (sin clave): respaldo gratis, 1 respuesta cada 45 s, calidad menor.

Cada llamada devuelve (dict, uso) y acumula el costo en COSTOS para guardarlo con el video.
"""
import json
import re
import time

import requests

from .config import (ANTHROPIC_API_KEY, CLAUDE_ESFUERZO, CLAUDE_MODELO, GEMINI_API_KEY, GEMINI_MODELOS,
                     POLLINATIONS_TOKEN, PRECIO_BUSQUEDA_WEB, PRECIOS)

COSTOS = {"usd": 0.0, "llamadas": []}


def reiniciar_costos():
    COSTOS["usd"] = 0.0
    COSTOS["llamadas"] = []


def _anotar(proveedor, modelo, entrada=0, salida=0, busquedas=0):
    pin, pout = PRECIOS.get(modelo, (0.0, 0.0))
    usd = entrada / 1e6 * pin + salida / 1e6 * pout + busquedas * PRECIO_BUSQUEDA_WEB
    COSTOS["usd"] += usd
    COSTOS["llamadas"].append({"proveedor": proveedor, "modelo": modelo, "entrada": entrada,
                               "salida": salida, "busquedas": busquedas, "usd": round(usd, 4)})


def extraer_json(texto):
    texto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("la respuesta no trae JSON")
    try:
        return json.loads(texto[i:j + 1])
    except json.JSONDecodeError:
        from json_repair import repair_json
        return json.loads(repair_json(texto[i:j + 1]))


# ---------- Claude ----------
def _claude(prompt, max_tokens, buscar_web=False):
    import anthropic

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
    kwargs = dict(
        model=CLAUDE_MODELO,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": CLAUDE_ESFUERZO},
    )
    if buscar_web:
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    # Si el modelo rechaza algo por seguridad, la API reintenta con otro modelo (fallbacks="default")
    usar_fallback = CLAUDE_MODELO in ("claude-opus-5-5", "claude-sonnet-5-5")
    if usar_fallback:
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        stream = cliente.beta.messages.stream(**kwargs)
    else:
        stream = cliente.messages.stream(**kwargs)
    with stream as s:
        msg = s.get_final_message()

    # Continúa si la búsqueda web pausó el turno
    vueltas = 0
    while msg.stop_reason == "pause_turn" and vueltas < 3:
        vueltas += 1
        kwargs["messages"] = [{"role": "user", "content": prompt}, {"role": "assistant", "content": msg.content}]
        st = cliente.beta.messages.stream(**kwargs) if usar_fallback else cliente.messages.stream(**kwargs)
        with st as s:
            msg = s.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude se negó a responder este tema")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("respuesta cortada por max_tokens")
    u = msg.usage
    busquedas = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
    entrada = (u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0) + \
              (getattr(u, "cache_creation_input_tokens", 0) or 0)
    _anotar("claude", msg.model or CLAUDE_MODELO, entrada, u.output_tokens or 0, busquedas)
    texto = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return texto


# ---------- Gemini ----------
def _gemini(prompt, max_tokens, buscar_web=False):
    from google import genai
    from google.genai import types

    # Límite de 5 min por llamada (en ms): sin esto una respuesta colgada bloqueó un short 59 min
    cliente = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=300_000))
    ultimo = None
    # Gemini gratis se satura seguido (503) o agota la cuota de un modelo (429): se dan hasta 3 vueltas por
    # todos los modelos, esperando entre vueltas, antes de rendirse.
    for vuelta in range(3):
        if vuelta:
            espera = 45 * vuelta
            print(f"[ia] Gemini saturado; espero {espera}s y vuelvo a intentar (vuelta {vuelta + 1}/3)")
            time.sleep(espera)
        modelos = [m for m in _modelos_gemini(cliente) if m not in _GEMINI_AGOTADOS]
        if not modelos:
            break
        texto, ultimo = _vuelta_gemini(cliente, types, modelos, prompt, max_tokens)
        if texto is not None:
            return texto
    raise RuntimeError(ultimo)


_GEMINI_AGOTADOS = set()  # modelos que respondieron 429 (cuota del día agotada) en esta ejecución


def _vuelta_gemini(cliente, types, modelos, prompt, max_tokens):
    ultimo = None
    for modelo in modelos:
        try:
            extra = {}
            if modelo.startswith("gemini-3"):  # piensa menos: mucho más rápido y suficiente para guiones
                extra["thinking_config"] = types.ThinkingConfig(thinking_level="low")
            t0 = time.time()
            r = cliente.models.generate_content(
                model=modelo, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9,
                                                   max_output_tokens=max_tokens, **extra))
            if not r.text:
                raise RuntimeError("respuesta vacía")
            print(f"[ia] Gemini {modelo} respondió en {time.time() - t0:.0f}s")
            _anotar("gemini", modelo)
            return r.text, None
        except Exception as e:  # noqa: BLE001
            print(f"[ia] Gemini {modelo} falló: {str(e)[:160]}")
            ultimo = e
            if "404" in str(e):
                _GEMINI_NO_EXISTE.add(modelo)
            elif "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                _GEMINI_AGOTADOS.add(modelo)
    return None, ultimo


_GEMINI_NO_EXISTE = set()
_GEMINI_DESCUBIERTOS = []


def _modelos_gemini(cliente):
    """Modelos configurados y, detrás, los 'flash' que tu clave realmente puede usar (Google los retira seguido)."""
    if not _GEMINI_DESCUBIERTOS:
        try:
            nombres = []
            for m in cliente.models.list():
                nombre = (m.name or "").removeprefix("models/")
                acciones = getattr(m, "supported_actions", None) or []
                if ("flash" in nombre and "generateContent" in acciones
                        and not any(x in nombre for x in ("lite", "image", "tts", "live", "audio", "preview", "exp"))):
                    nombres.append(nombre)
            _GEMINI_DESCUBIERTOS.extend(sorted(nombres, reverse=True))
            print(f"[ia] modelos Gemini disponibles: {_GEMINI_DESCUBIERTOS[:5]}")
        except Exception as e:  # noqa: BLE001
            print(f"[ia] no pude listar modelos Gemini: {str(e)[:150]}")
    lista = []
    for m in GEMINI_MODELOS + _GEMINI_DESCUBIERTOS:
        if m not in lista and m not in _GEMINI_NO_EXISTE:
            lista.append(m)
    return lista


# ---------- Pollinations ----------
def esperar_limite(r):
    """Si Pollinations respondió 'Free limit reached… Retry after Ns', devuelve cuántos segundos esperar."""
    if r.status_code not in (402, 429):
        return 0
    m = re.search(r"[Rr]etry after (\d+)", r.text)
    return int(m.group(1)) + 3 if m else 47


def _pollinations(prompt, max_tokens, buscar_web=False):
    headers = {"Content-Type": "application/json"}
    if POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {POLLINATIONS_TOKEN}"
    r = None
    for _ in range(5):
        r = requests.post("https://text.pollinations.ai/openai", headers=headers, timeout=300, json={
            "model": "openai", "messages": [{"role": "user", "content": prompt}],
            "seed": int(time.time()) % 100000, "max_tokens": max(max_tokens, 12000), "reasoning_effort": "low"})
        espera = esperar_limite(r)
        if not espera:
            break
        print(f"[ia] límite gratis de Pollinations, espero {espera}s")
        time.sleep(espera)
    if not r.ok:
        raise RuntimeError(f"Pollinations {r.status_code}: {r.text[:300]}")
    _anotar("pollinations", "openai")
    return r.json()["choices"][0]["message"]["content"]


def proveedores():
    lista = []
    if ANTHROPIC_API_KEY:
        lista.append(("claude", _claude))
    if GEMINI_API_KEY:
        lista.append(("gemini", _gemini))
    lista.append(("pollinations", _pollinations))
    return lista


def generar_json(prompt, validar=None, max_tokens=16000, intentos=2, buscar_web=False, solo_claude=False):
    """Pide JSON a la IA. 'validar' recibe el dict y debe devolverlo (o lanzar error para reintentar)."""
    errores = []
    lista = proveedores()
    if solo_claude:
        lista = [p for p in lista if p[0] == "claude"]
    for intento in range(intentos):
        for nombre, fn in lista:
            try:
                datos = extraer_json(fn(prompt, max_tokens, buscar_web=buscar_web))
                return validar(datos) if validar else datos
            except Exception as e:  # noqa: BLE001
                errores.append(f"{nombre}: {str(e)[:200]}")
                print(f"[ia] intento {intento + 1} con {nombre} no sirvió: {str(e)[:200]}")
        time.sleep(5)
    raise RuntimeError("Ninguna IA pudo responder: " + " | ".join(errores))
