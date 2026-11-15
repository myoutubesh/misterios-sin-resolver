# Misterios Sin Resolver: arquitectura, herramientas y presupuesto

*Precios y límites revisados el 15-nov-2026. Varios proveedores cambian sus límites gratis sin aviso, así que lo marcado con ⚠️ hay que confirmarlo en tu cuenta.*

## 1. Cómo funciona (vista general)

```
            ┌──────────────────── GitHub Actions (nube, gratis) ────────────────────┐
 cron  ───► │ 1 INVESTIGAR   Wikipedia (EN+ES) + popularidad (Wikimedia Pageviews)    │
 3/día      │                + aprendizajes de tus estadísticas → elige el tema       │
 shorts     │ 2 GUIONIZAR    IA: Claude API ▸ Gemini ▸ Pollinations (respaldo)         │
            │                borrador → editor → verificación con búsqueda web         │
 2/semana   │ 3 NARRAR       voz neuronal es-MX (edge-tts) + tiempos por palabra       │
 largos     │ 4 VISUALES     imágenes IA (Pollinations) + clips reales (Pexels)        │
            │ 5 EDITAR       FFmpeg: cámara, transiciones, subtítulos, música y efectos │
            │                generados, normalización de volumen, plantilla variable  │
            │ 6 MINIATURA    imagen + texto (Pillow), solo videos largos               │
            │ 7 PUBLICAR     YouTube Data API (OAuth): sube, programa, miniatura       │
            │ 8 REGISTRAR    data/*.json en el repositorio (= base de datos)           │
            └───────────────────────────────────────────────────────────────────────┘
 cron diario ─► ESTADÍSTICAS  YouTube Data API + Analytics API → aprendizajes.json
             ─► PANEL         docs/index.html (GitHub Pages) + PANEL.md
 si falla   ─► GitHub te manda un correo (aviso solo cuando hay error)
```

Todo vive en un repositorio de GitHub. No hace falta servidor, base de datos externa ni que tu PC esté prendida.

## 2. Herramientas elegidas (y por qué)

| Función | Elegida | Costo | Alternativas evaluadas |
|---|---|---|---|
| Ejecución 24/7 | **GitHub Actions** | Gratis e ilimitado en repo **público**; 2,000 min/mes en repo privado | VPS (~$5/mes), Railway/Render (planes gratis con límites y "sueño"), tu PC (debe estar encendida) |
| Guiones e investigación | **Claude API** (si pones clave) ▸ Gemini gratis ▸ Pollinations | Ver tabla 3 | ElevenLabs/otros no aplican; OpenAI similar a Claude en precio |
| Verificación de datos | Claude + herramienta de búsqueda web | ≈ $10 por 1,000 búsquedas ⚠️ | Solo Wikipedia (gratis, menos verificación) |
| Voz | **edge-tts** (voces neuronales de Microsoft) | $0 | ElevenLabs Creator ~$22/mes (no alcanza para videos largos); Azure Speech: plan gratis oficial de 500k caracteres/mes ⚠️ (pide tarjeta) |
| Imágenes IA | **Pollinations** (Flux) | $0 sin cuenta: 1 imagen cada 45 s (medido) | Registro gratis "Seed" con menos espera ⚠️; muapi/Kling: ~$0.30-1 por clip |
| Clips de video reales | **Pexels API** | $0, uso comercial permitido, ~200 pedidos/hora ⚠️ | Pixabay (similar), Storyblocks (pago) |
| Música y efectos | **Generados con FFmpeg** (síntesis) | $0, sin copyright | Biblioteca de audio de YouTube (manual), Epidemic (~$10/mes) |
| Edición | **FFmpeg + Python** | $0 | MoviePy (más lento), Remotion (Node, más complejo) |
| Miniaturas | **Pillow** sobre imagen IA | $0 | Canva API (pago) |
| Publicación y estadísticas | **YouTube Data API v3 + YouTube Analytics API** | $0 (cuota diaria) | — |
| Base de datos | **Archivos JSON en el repo** | $0 | SQLite/Supabase: innecesario a este volumen |
| Panel | **GitHub Pages** (HTML estático) + PANEL.md | $0 | Streamlit Cloud, Vercel |

## 3. Presupuesto mensual estimado

Supuestos: 2 shorts al día (60/mes) y 2 videos largos por semana (8/mes). Precios oficiales de Claude por millón de tokens: Opus 5.5 $4 / $20, Sonnet 5.5 $2 / $10, Haiku 5.5 $0.10 / $0.50 (entrada / salida).

| Partida | Opción "todo gratis" | Con Claude Haiku 5.5 | Con Claude Sonnet 5.5 | Con Claude Opus 5.5 (máxima calidad) |
|---|---|---|---|---|
| Guiones + edición + verificación (60 shorts) | $0 | ≈ $2.40 | ≈ $10 | ≈ $18 |
| Guiones videos largos (8) | $0 | ≈ $0.50 | ≈ $5 | ≈ $10 |
| Voz, imágenes, clips, música, edición, nube | $0 | $0 | $0 | $0 |
| **Total aproximado** | **$0** | **≈ $3/mes** | **≈ $15/mes** | **≈ $28/mes** |

- Con **3 shorts al día**, suma un 50 % a la línea de shorts.
- Son estimaciones: la factura real depende de cuántos tokens use cada guion. El panel muestra el costo real de cada video (lo calcula con los tokens que reporta la API).
- **"Todo gratis" tiene un riesgo real:** el plan gratis de Gemini bajó mucho en 2026 (las fuentes hablan de unos 20 pedidos al día ⚠️) y Google puede usar esos datos para entrenar. Cada short usa 2 o 3 pedidos y cada video largo de 4 a 8, así que 2 shorts al día + videos largos puede quedarse corto. Si Gemini se agota, el sistema pasa a Pollinations, que escribe peor.
- **Recomendación:** pon una clave de Claude API con un límite de gasto mensual (por ejemplo, $10 o $30) en console.anthropic.com. Tú eliges el modelo con la variable `CLAUDE_MODELO`. Por defecto el sistema usa `claude-opus-5-5`, que es el de mejor calidad. Si quieres gastar menos, cámbialo a `claude-sonnet-5-5` o `claude-haiku-5-5`.

## 4. Qué se automatiza de verdad (y qué no)

| Tarea | ¿Automática? | Nota |
|---|---|---|
| Investigar, elegir tema, no repetir | ✅ | Wikipedia + popularidad + lo que mejor funciona en tu canal |
| Verificar fechas y nombres | ✅ parcial | Compara con Wikipedia en 2 idiomas; con Claude además busca en la web. Ninguna IA es infalible: revisa de vez en cuando |
| Guion, voz, imágenes, clips, música, subtítulos, edición | ✅ | Plantilla visual distinta en cada video |
| Miniatura (largos) | ✅ | Requiere canal verificado con teléfono |
| Subir, programar, título, descripción, etiquetas | ✅ | Tras aprobarse la auditoría de la API (ver 5.1) |
| Estadísticas y aprendizaje | ✅ parcial | Vistas, retención, suscriptores y duración sí. El CTR de miniaturas **no** lo da la Analytics API normal (ver 5.4) |
| Cambiar el horario de publicación solo | ❌ | El panel te dice qué horario rinde mejor; tú cambias una línea |
| Configuración inicial (cuentas, claves, OAuth) | ❌ | Una sola vez, unos 40-60 min, ver GUIA.md |

## 5. Limitaciones técnicas importantes

1. **Videos bloqueados en privado al inicio.** YouTube deja en privado todo lo que sube un proyecto de Google Cloud que no ha pasado su auditoría. La auditoría es gratis pero tarda de días a semanas. Hasta entonces el sistema genera y sube, pero tú tienes que publicar a mano (o descargar y resubir).
2. **Cuota de la API de YouTube:** 10,000 unidades al día. El costo de subir un video aparece como 1,600 unidades en la documentación de Google, aunque guías recientes dicen que bajó ⚠️. Con 1,600 entran unas 6 subidas al día, que alcanza para 3 shorts + 1 largo.
3. **Velocidad de imágenes gratis:** 1 imagen cada 45 s sin cuenta. Un short (8 imágenes) tarda unos 6 min. Un largo usa clips de Pexels para la mayoría de escenas y tarda de 40 a 90 min. Esto obliga a usar repo **público** (minutos ilimitados) o una cuenta Seed de Pollinations.
4. **CTR de miniaturas:** la YouTube Analytics API no entrega impresiones ni CTR en sus consultas normales; solo la Reporting API (reportes masivos con 1-2 días de retraso). Queda como mejora de la fase 2.
5. **edge-tts** usa el servicio de lectura en voz alta de Microsoft Edge, que no tiene contrato de API oficial: puede dejar de funcionar sin aviso. Alternativa oficial y gratis: Azure Speech (mismas voces, 500k caracteres al mes ⚠️). Se puede cambiar después.
6. **Políticas de YouTube:** para monetizar, el contenido no puede ser "repetitivo o producido en masa". El sistema varía estructura y estilo, cita fuentes y marca el contenido como sintético, pero **ninguna herramienta garantiza la monetización**. YouTube decide en la revisión humana.
7. **Repo público vs privado:** en un repo público cualquiera puede ver el código, los guiones y el panel, pero **no** tus claves (los *Secrets* nunca se muestran). En uno privado tienes 2,000 minutos al mes, que no alcanzan con videos largos.

## 6. Fases

- **Fase 1 (esta versión):** todo lo anterior funcionando de punta a punta: shorts, largos, publicación programada, estadísticas básicas, panel y avisos por correo.
- **Fase 2:** CTR por Reporting API, voz con Azure, pruebas A/B de títulos, listas de reproducción automáticas y respuestas a comentarios (esta última con revisión humana, por las políticas de spam).
