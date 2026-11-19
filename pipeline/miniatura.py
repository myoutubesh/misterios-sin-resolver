"""Miniaturas 1280x720 para videos largos.

Estilos (recreados a partir del estudio de la competencia, ver COMPETENCIA.md):
  - clasico: imagen + degradado oscuro a la izquierda + texto grande con color de acento.
  - rojo:    toda la imagen teñida de rojo oscuro, texto blanco enorme centrado con brillo rojo.
  - vhs:     marco de videocámara (● REC, batería, contador), grano y líneas de TV vieja.
  - lista:   collage de 3 imágenes, un número rojo gigante en medio y una franja con el tema abajo.
Las imágenes son siempre las generadas para el propio video (nunca de otros canales).
"""
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .config import ASSETS

W, H = 1280, 720
ACENTOS = [(255, 214, 10), (235, 50, 45), (120, 220, 255)]
ESTILOS_CASO = ["clasico", "rojo", "vhs"]


def _fuente(tam, preferida="Anton-Regular.ttf"):
    for nombre in (preferida, "Anton-Regular.ttf", "BebasNeue-Regular.ttf"):
        ruta = ASSETS / "fonts" / nombre
        if ruta.exists():
            return ImageFont.truetype(str(ruta), tam)
    return ImageFont.load_default(tam)


def _envolver(texto, fuente, ancho, dibujo):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _ajustar(texto, ancho, max_lineas, tam, minimo, dibujo, preferida="Anton-Regular.ttf"):
    while True:
        fuente = _fuente(tam, preferida)
        lineas = _envolver(texto, fuente, ancho, dibujo)
        if len(lineas) <= max_lineas or tam <= minimo:
            return fuente, lineas, tam
        tam -= 8


def _cargar(imagen, w=W, h=H):
    img = Image.open(imagen).convert("RGB")
    img = img.crop((0, 0, img.width, int(img.height * 0.93)))  # quita la franja de abajo (posible marca de agua)
    return ImageOps.fit(img, (w, h), Image.LANCZOS, centering=(0.5, 0.45))


def _bloque(dibujo, lineas, fuente, cx, cy, colores, borde=8, alineacion="centro", x0=60):
    """Dibuja líneas de texto centradas verticalmente en cy. Devuelve la y final."""
    cajas = [dibujo.textbbox((0, 0), ln, font=fuente, stroke_width=borde) for ln in lineas]
    altos = [c[3] - c[1] for c in cajas]
    sep = int(fuente.size * 0.08)
    y = cy - (sum(altos) + sep * (len(lineas) - 1)) // 2
    for i, (ln, caja, alto) in enumerate(zip(lineas, cajas, altos)):
        ancho = caja[2] - caja[0]
        x = cx - ancho // 2 if alineacion == "centro" else x0
        dibujo.text((x - caja[0], y - caja[1]), ln, font=fuente, fill=colores[min(i, len(colores) - 1)],
                    stroke_width=borde, stroke_fill=(0, 0, 0))
        y += alto + sep
    return y


# ---------- estilos ----------
def _clasico(imagenes, texto, **_):
    img = _cargar(imagenes[0])
    img = ImageEnhance.Brightness(ImageEnhance.Contrast(img).enhance(1.25)).enhance(0.85)
    sombra = Image.new("L", (W, H))
    d = ImageDraw.Draw(sombra)
    for x in range(W):
        d.line([(x, 0), (x, H)], fill=int(max(0, 210 - x * 0.28)))
    img = Image.composite(Image.new("RGB", (W, H)), img, sombra.filter(ImageFilter.GaussianBlur(20)))
    dibujo = ImageDraw.Draw(img)
    acento = random.choice(ACENTOS)
    fuente, lineas, _ = _ajustar(texto, 700, 3, 150, 70, dibujo)
    colores = [(255, 255, 255)] * (len(lineas) - 1) + [acento]
    y = _bloque(dibujo, lineas, fuente, 0, H // 2 - 10, colores, alineacion="izq", x0=60)
    dibujo.rectangle([(64, y + 6), (64 + 180, y + 20)], fill=acento)
    return img


def _rojo(imagenes, texto, **_):
    base = ImageEnhance.Contrast(_cargar(imagenes[0]).convert("L")).enhance(1.35)
    img = ImageOps.colorize(base, black=(8, 0, 0), mid=(150, 12, 12), white=(255, 190, 170))
    # Viñeta: bordes negros, centro iluminado
    vin = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vin).ellipse([(-160, -120), (W + 160, H + 120)], fill=255)
    img = Image.composite(img, Image.new("RGB", (W, H)), vin.filter(ImageFilter.GaussianBlur(120)))
    dibujo = ImageDraw.Draw(img)
    fuente, lineas, _ = _ajustar(texto, 1120, 2, 170, 80, dibujo)
    # Brillo rojo detrás de las letras
    brillo = Image.new("RGB", (W, H))
    _bloque(ImageDraw.Draw(brillo), lineas, fuente, W // 2, int(H * 0.68), [(255, 30, 30)], borde=18)
    img = ImageChops.add(img, brillo.filter(ImageFilter.GaussianBlur(16)))
    dibujo = ImageDraw.Draw(img)
    _bloque(dibujo, lineas, fuente, W // 2, int(H * 0.68), [(255, 255, 255), (255, 60, 50)], borde=7)
    return img


def _vhs(imagenes, texto, **_):
    img = _cargar(imagenes[0])
    img = ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.15)).enhance(0.7)
    # Desfase de color (cinta vieja)
    r, g, b = img.split()
    img = Image.merge("RGB", (ImageChops.offset(r, 5, 0), g, ImageChops.offset(b, -5, 0)))
    # Grano y líneas de TV
    ruido = Image.effect_noise((W, H), 38).convert("RGB")
    img = Image.blend(img, ruido, 0.10)
    lineas_tv = Image.new("L", (W, H), 0)
    dl = ImageDraw.Draw(lineas_tv)
    for y in range(0, H, 4):
        dl.line([(0, y), (W, y)], fill=60)
    img = Image.composite(Image.new("RGB", (W, H)), img, lineas_tv)
    dibujo = ImageDraw.Draw(img)
    blanco = (240, 240, 240)
    f_ui = _fuente(46, "BebasNeue-Regular.ttf")
    dibujo.ellipse([(52, 46), (82, 76)], fill=(230, 20, 20))
    dibujo.text((96, 38), "REC", font=f_ui, fill=blanco)
    dibujo.rectangle([(1120, 46), (1206, 78)], outline=blanco, width=4)
    dibujo.rectangle([(1206, 54), (1214, 70)], fill=blanco)
    for k in range(3):
        dibujo.rectangle([(1128 + k * 26, 53), (1146 + k * 26, 71)], fill=blanco)
    contador = f"{random.randint(0, 2):02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}"
    dibujo.text((W - 60 - dibujo.textlength(contador, font=f_ui), H - 92), contador, font=f_ui, fill=blanco)
    dibujo.text((56, H - 92), "PLAY ▶" if random.random() < 0.5 else "SP", font=f_ui, fill=blanco)
    # Esquinas del visor
    for (x, y, dx, dy) in [(36, 30, 1, 1), (W - 36, 30, -1, 1), (36, H - 30, 1, -1), (W - 36, H - 30, -1, -1)]:
        dibujo.line([(x, y), (x + 70 * dx, y)], fill=blanco, width=5)
        dibujo.line([(x, y), (x, y + 70 * dy)], fill=blanco, width=5)
    fuente, lineas, _ = _ajustar(texto, 1000, 2, 150, 76, dibujo, "BebasNeue-Regular.ttf")
    _bloque(dibujo, lineas, fuente, W // 2, H // 2 + 40, [(255, 236, 60), (255, 255, 255)], borde=9)
    return img


def _lista(imagenes, texto, numero=7, **_):
    fotos = (list(imagenes) * 3)[:3]
    ancho = W // 3
    img = Image.new("RGB", (W, H))
    for i, f in enumerate(fotos):
        trozo = ImageEnhance.Contrast(_cargar(f, ancho, H)).enhance(1.2)
        img.paste(ImageEnhance.Brightness(trozo).enhance(0.8), (i * ancho, 0))
    dibujo = ImageDraw.Draw(img)
    for i in (1, 2):  # separadores
        dibujo.line([(i * ancho, 0), (i * ancho, H)], fill=(0, 0, 0), width=8)
    # Franja de abajo con el tema
    alto_franja = 150
    franja = Image.new("RGB", (W, alto_franja), (0, 0, 0))
    img.paste(Image.blend(img.crop((0, H - alto_franja, W, H)), franja, 0.82), (0, H - alto_franja))
    dibujo = ImageDraw.Draw(img)
    fuente, lineas, _ = _ajustar(texto, 1180, 1, 104, 52, dibujo)
    _bloque(dibujo, lineas[:1], fuente, W // 2, H - alto_franja // 2, [(255, 255, 255)], borde=6)
    # Número gigante en el centro con brillo
    f_num = _fuente(470)
    num = str(numero)
    capa = Image.new("RGB", (W, H))
    _bloque(ImageDraw.Draw(capa), [num], f_num, W // 2, int(H * 0.40), [(255, 0, 0)], borde=24)
    img = ImageChops.add(img, capa.filter(ImageFilter.GaussianBlur(22)))
    dibujo = ImageDraw.Draw(img)
    _bloque(dibujo, [num], f_num, W // 2, int(H * 0.40), [(235, 22, 22)], borde=12)
    return img


ESTILOS = {"clasico": _clasico, "rojo": _rojo, "vhs": _vhs, "lista": _lista}


def crear(imagenes, texto, salida, estilo=None, numero=None):
    """imagenes: una ruta o una lista de rutas (la lista usa 3). Devuelve (ruta, estilo usado)."""
    if not isinstance(imagenes, (list, tuple)):
        imagenes = [imagenes]
    estilo = estilo or ("lista" if numero else random.choice(ESTILOS_CASO))
    texto = (texto or "").upper().strip() or "SIN RESOLVER"
    img = ESTILOS[estilo](imagenes, texto, numero=numero or 7)
    img.convert("RGB").save(salida, "JPEG", quality=92)
    return salida, estilo
