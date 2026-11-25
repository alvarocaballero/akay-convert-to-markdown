"""Small generated PDF fixtures; no downloaded documents, fonts or models."""

from pathlib import Path


def write_text_pdf(path: Path) -> None:
    stream = (b"BT /F1 18 Tf 40 740 Td (Fixture heading) Tj "
              b"/F1 12 Tf 0 -30 Td (Fixture body) Tj "
              b"0 -30 Td (x = 1) Tj 0 -30 Td (E = mc2) Tj ET\n")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
               b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    _write_pdf(path, objects)


def _write_pdf(path: Path, objects: list[bytes]) -> None:
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    startxref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode())
    path.write_bytes(pdf)


SPANISH_SCAN_LINES = ("La fotosíntesis transforma la energía luminosa.",
                      "El agua y el dióxido de carbono producen oxígeno.",
                      "Las plantas necesitan luz para crecer.")


def write_spanish_scan_pdf(path: Path, *, broken_text_layer: bool = False) -> None:
    """An actual raster-only Spanish page, optionally with incorrect invisible text."""
    from PIL import Image, ImageDraw, ImageFont
    import zlib

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 100), "La fotosíntesis", font=ImageFont.load_default(size=48), fill="black")
    for index, text in enumerate(SPANISH_SCAN_LINES):
        draw.text((80, 240 + index * 65), text, font=ImageFont.load_default(size=32), fill="black")
    raster = zlib.compress(image.tobytes())
    content = b"q 600 0 0 800 0 0 cm /Im1 Do Q\n"
    if broken_text_layer:
        # Intentionally corrupt OCR overlay: visible page still contains Spanish.
        content += b"BT /F1 12 Tf 3 Tr 40 670 Td (ZZZZ WRONG TEXT LAYER) Tj ET\n"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
               b"/Resources << /Font << /F1 6 0 R >> /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
               b"<< /Type /XObject /Subtype /Image /Width 1200 /Height 1600 /ColorSpace /DeviceRGB "
               b"/BitsPerComponent 8 /Filter /FlateDecode /Length " + str(len(raster)).encode() +
               b" >>\nstream\n" + raster + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    _write_pdf(path, objects)


def write_structured_pdf(path: Path) -> None:
    """Native Spanish headings, ruled table, diagram, code and a displayed formula."""
    from PIL import Image, ImageDraw
    import zlib

    image = Image.new("RGB", (400, 250), "white")
    draw = ImageDraw.Draw(image)
    draw.line((200, 230, 200, 30), fill="green", width=12)
    draw.ellipse((70, 70, 200, 150), fill="green")
    draw.ellipse((200, 40, 330, 120), fill="green")
    draw.rectangle((150, 220, 250, 245), fill="brown")
    raster = zlib.compress(image.tobytes())
    content = bytearray()

    def text(value, x, y, size=12, font="F1"):
        escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content.extend(f"BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET\n".encode("cp1252"))

    text("Fotosíntesis", 40, 750, 26)
    text("Las plantas transforman la energía luminosa.", 40, 715)
    text("Materiales", 40, 670, 18)
    for y in (640, 610, 580, 550):
        content.extend(f"40 {y} m 280 {y} l S\n".encode())
    for x in (40, 180, 280):
        content.extend(f"{x} 550 m {x} 640 l S\n".encode())
    for label, value, y in (("Material", "Cantidad", 620), ("Agua", "2", 590), ("Plantas", "3", 560)):
        text(label, 50, y)
        text(value, 195, y)
    text("Ejemplo de código", 40, 510, 18)
    for index, line in enumerate(("def energia(masa):", "    velocidad = 299792458", "    return masa * velocidad ** 2",
                                  "", "resultado = energia(2)", "print(resultado)")):
        text(line, 55, 480 - index * 17, 11, "F2")
    text("Ecuación de energía", 40, 340, 18)
    text("E = mc", 130, 300, 22)
    text("2", 203, 310, 12)
    content.extend(b"q 240 0 0 150 170 95 cm /Im1 Do Q\n")
    text("Figura 1. Diagrama de una planta.", 170, 70)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
               b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Im1 7 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
               b"<< /Type /XObject /Subtype /Image /Width 400 /Height 250 /ColorSpace /DeviceRGB "
               b"/BitsPerComponent 8 /Filter /FlateDecode /Length " + str(len(raster)).encode() +
               b" >>\nstream\n" + raster + b"\nendstream"]
    _write_pdf(path, objects)
