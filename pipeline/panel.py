"""Genera el panel de control: docs/index.html (GitHub Pages) y PANEL.md (se ve directo en GitHub)."""
import datetime as dt
import html
from collections import defaultdict

from . import db
from .config import CANAL, DOCS, ROOT


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _num(x):
    return f"{x:,}".replace(",", " ") if isinstance(x, (int, float)) else "—"


def _sparkline(valores, ancho=260, alto=48):
    if len(valores) < 2:
        return ""
    mn, mx = min(valores), max(valores)
    rango = (mx - mn) or 1
    pts = " ".join(f"{i * ancho / (len(valores) - 1):.1f},{alto - (v - mn) / rango * (alto - 6) - 3:.1f}"
                   for i, v in enumerate(valores))
    return (f'<svg viewBox="0 0 {ancho} {alto}" class="spark" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="2"/></svg>')


def generar():
    vids = db.videos()
    est = db.leer(db.ESTADISTICAS, {"videos": {}, "historial_canal": []})
    ejec = db.leer(db.EJECUCIONES, [])
    aprend = db.leer(db.APRENDIZAJES, {})
    m = est.get("videos", {})
    canal = est.get("canal", {})
    ahora = dt.datetime.now(dt.timezone.utc)
    mes = ahora.strftime("%Y-%m")

    cuenta = defaultdict(int)
    for v in vids:
        cuenta[v.get("estado", "creado")] += 1
    costo_mes = sum(v.get("costo_usd", 0) for v in vids if v.get("fecha", "").startswith(mes))
    costo_total = sum(v.get("costo_usd", 0) for v in vids)
    errores = [e for e in ejec if e.get("estado") == "error"]
    errores_7d = [e for e in errores if e.get("inicio", "") >= (ahora - dt.timedelta(days=7)).isoformat()]
    proximas = sorted((v for v in vids if v.get("publicar_en") and v["publicar_en"] > ahora.isoformat()),
                      key=lambda v: v["publicar_en"])

    por_cat = defaultdict(list)
    for v in vids:
        if v.get("youtube_id") in m and "vistas" in m[v["youtube_id"]]:
            por_cat[v.get("categoria") or "—"].append(m[v["youtube_id"]]["vistas"])
    cats = sorted(((c, sum(x) / len(x), len(x)) for c, x in por_cat.items()), key=lambda t: -t[1])
    max_cat = max((c[1] for c in cats), default=1) or 1

    subs = [h["suscriptores"] for h in est.get("historial_canal", [])]

    tarjetas = [
        ("Suscriptores", _num(canal.get("suscriptores")), _sparkline(subs)),
        ("Vistas del canal", _num(canal.get("vistas")), ""),
        ("Videos creados", _num(len(vids)), ""),
        ("Publicados", _num(cuenta["publicado"]), ""),
        ("Programados", _num(cuenta["programado"]), ""),
        ("Errores (7 días)", _num(len(errores_7d)), ""),
        (f"Costo IA {mes}", f"${costo_mes:.2f}", f"<small>Total: ${costo_total:.2f}</small>"),
    ]

    filas = []
    for v in sorted(vids, key=lambda v: v.get("fecha", ""), reverse=True)[:150]:
        mm = m.get(v.get("youtube_id") or "", {})
        titulo = _e(v.get("titulo_yt"))
        if v.get("url"):
            titulo = f'<a href="{_e(v["url"])}" target="_blank" rel="noopener">{titulo}</a>'
        ret = mm.get("retencion")
        filas.append(
            f"<tr><td>{_e(v.get('fecha', '')[:10])}</td><td>{_e(v.get('formato'))}</td><td>{titulo}</td>"
            f"<td>{_e(v.get('categoria'))}</td><td><span class='st st-{_e(v.get('estado'))}'>{_e(v.get('estado'))}</span></td>"
            f"<td class='n'>{_num(mm.get('vistas'))}</td><td class='n'>{f'{ret:.0f}%' if ret is not None else '—'}</td>"
            f"<td class='n'>{_num(mm.get('suscriptores_ganados'))}</td><td class='n'>{_e(v.get('duracion'))}s</td>"
            f"<td class='n'>${v.get('costo_usd', 0):.3f}</td></tr>")

    html_out = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel {_e(CANAL)}</title>
<style>
:root {{ --bg:#f6f6f4; --card:#fff; --tx:#1d1d1f; --mu:#6b6b70; --bd:#e3e3e0; --ac:#b3261e; --ok:#1e7a3c; --wa:#9a6700; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#111214; --card:#1b1c1f; --tx:#ececec; --mu:#9a9aa2; --bd:#2c2d31; --ac:#ff6b5e; --ok:#5cc983; --wa:#e3b341; }} }}
:root[data-theme="dark"] {{ --bg:#111214; --card:#1b1c1f; --tx:#ececec; --mu:#9a9aa2; --bd:#2c2d31; --ac:#ff6b5e; --ok:#5cc983; --wa:#e3b341; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--tx); font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
main {{ max-width:1200px; margin:0 auto; padding:24px 16px 64px }}
h1 {{ font-size:1.6rem; margin:0 }} h2 {{ font-size:1.1rem; margin:32px 0 12px }}
.sub {{ color:var(--mu); margin:4px 0 20px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px }}
.card {{ background:var(--card); border:1px solid var(--bd); border-radius:12px; padding:14px }}
.card .k {{ color:var(--mu); font-size:.82rem }} .card .v {{ font-size:1.5rem; font-weight:650; font-variant-numeric:tabular-nums }}
.spark {{ width:100%; height:36px; color:var(--ac); margin-top:4px }}
.tabla {{ overflow-x:auto; background:var(--card); border:1px solid var(--bd); border-radius:12px }}
table {{ border-collapse:collapse; width:100%; font-size:.88rem }}
th,td {{ padding:8px 10px; border-bottom:1px solid var(--bd); text-align:left; white-space:nowrap }}
td:nth-child(3) {{ white-space:normal; min-width:240px }} th {{ color:var(--mu); font-weight:600 }}
.n {{ text-align:right; font-variant-numeric:tabular-nums }} a {{ color:var(--ac) }}
.st {{ font-size:.78rem; padding:2px 8px; border-radius:99px; border:1px solid var(--bd) }}
.st-publicado {{ color:var(--ok) }} .st-programado, .st-subido {{ color:var(--wa) }} .st-error {{ color:var(--ac) }}
.bar {{ display:grid; grid-template-columns:140px 1fr 90px; gap:10px; align-items:center; margin:6px 0 }}
.bar i {{ display:block; height:10px; background:var(--ac); border-radius:5px }}
ul {{ padding-left:20px }} li {{ margin:4px 0 }} code {{ font-size:.8rem; color:var(--mu) }}
</style></head><body><main>
<h1>{_e(CANAL)}: panel de control</h1>
<p class="sub">Actualizado: {ahora:%Y-%m-%d %H:%M} UTC · estadísticas de YouTube: {_e((est.get('actualizado') or 'aún no')[:16])}</p>
<div class="grid">{''.join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div>{x}</div>' for k, v, x in tarjetas)}</div>

<h2>Próximas publicaciones</h2>
<div class="tabla"><table><tr><th>Fecha (UTC)</th><th>Formato</th><th>Título</th></tr>
{''.join(f"<tr><td>{_e(v['publicar_en'])}</td><td>{_e(v.get('formato'))}</td><td>{_e(v.get('titulo_yt'))}</td></tr>" for v in proximas) or '<tr><td colspan=3>No hay publicaciones programadas.</td></tr>'}
</table></div>

<h2>Lo que el sistema aprendió</h2>
<div class="card">{('<ul>' + ''.join(f'<li>{_e(c)}</li>' for c in aprend.get('consejos', [])) + '</ul>') if aprend.get('consejos') else '<p>Todavía no hay suficientes datos (se necesitan videos con más de 2 días).</p>'}
{f"<p><b>Retención media de shorts:</b> {aprend['retencion_media_short']}%</p>" if aprend.get('retencion_media_short') else ''}</div>

<h2>Vistas promedio por categoría</h2>
<div class="card">{''.join(f'<div class="bar"><span>{_e(c)}</span><i style="width:{a / max_cat * 100:.0f}%"></i><span class="n">{a:,.0f} ({n})</span></div>' for c, a, n in cats) or '<p>Sin datos aún.</p>'}</div>

<h2>Historial de contenidos</h2>
<div class="tabla"><table><tr><th>Fecha</th><th>Formato</th><th>Título</th><th>Categoría</th><th>Estado</th><th class="n">Vistas</th><th class="n">Retención</th><th class="n">Subs</th><th class="n">Duración</th><th class="n">Costo</th></tr>
{''.join(filas) or '<tr><td colspan=10>Aún no hay videos.</td></tr>'}</table></div>

<h2>Errores recientes</h2>
<div class="tabla"><table><tr><th>Cuándo</th><th>Tipo</th><th>Error</th></tr>
{''.join(f"<tr><td>{_e(e.get('inicio', '')[:16])}</td><td>{_e(e.get('tipo'))}</td><td><code>{_e(e.get('error'))}</code></td></tr>" for e in reversed(errores[-15:])) or '<tr><td colspan=3>Sin errores. 👌</td></tr>'}
</table></div>
</main></body></html>"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(html_out, encoding="utf-8")

    md = [f"# Panel: {CANAL}", "", f"*Actualizado: {ahora:%Y-%m-%d %H:%M} UTC*", "",
          "| Suscriptores | Vistas | Creados | Publicados | Programados | Errores 7d | Costo IA mes |",
          "|---|---|---|---|---|---|---|",
          f"| {_num(canal.get('suscriptores'))} | {_num(canal.get('vistas'))} | {len(vids)} | {cuenta['publicado']} | "
          f"{cuenta['programado']} | {len(errores_7d)} | ${costo_mes:.2f} |", "",
          "## Últimos videos", "", "| Fecha | Formato | Título | Estado | Vistas |", "|---|---|---|---|---|"]
    for v in sorted(vids, key=lambda v: v.get("fecha", ""), reverse=True)[:30]:
        t = (v.get("titulo_yt") or "").replace("|", "/")
        t = f"[{t}]({v['url']})" if v.get("url") else t
        md.append(f"| {v.get('fecha', '')[:10]} | {v.get('formato')} | {t} | {v.get('estado')} | "
                  f"{_num(m.get(v.get('youtube_id') or '', {}).get('vistas'))} |")
    if aprend.get("consejos"):
        md += ["", "## Aprendizajes", ""] + [f"- {c}" for c in aprend["consejos"]]
    if errores:
        md += ["", "## Errores recientes", ""] + [f"- {e.get('inicio', '')[:16]} · {e.get('tipo')} · `{e.get('error')}`"
                                                   for e in reversed(errores[-10:])]
    (ROOT / "PANEL.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("[panel] docs/index.html y PANEL.md actualizados")
