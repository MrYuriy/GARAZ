"""QR codes as images: one PNG per truck, and a printable A4 sheet of labels."""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import segno
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# A TrueType font with Polish letters; the built-in PDF fonts have no "ł" or "ż".
# DejaVu ships in the Docker image; the rest cover a developer's machine.
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
_FONT = "Helvetica"
for _path in _FONT_CANDIDATES:
    if Path(_path).is_file():
        pdfmetrics.registerFont(TTFont("LabelFont", _path))
        _FONT = "LabelFont"
        break

# Label grid until the sticker size is decided (open question 7): 2 × 4 on A4,
# each 105 × 74 mm — the common "8 per sheet" self-adhesive format.
COLUMNS, ROWS = 2, 4
_QR_SIZE = 56 * mm


@dataclass(frozen=True)
class Label:
    qr_data: str
    title: str  # large: the truck number, the operator's name
    subtitle: str  # the truck type, the employer
    # Small print under it: what to do with the code.
    note: tuple[str, ...] = ("Zeskanuj, aby zgłosić", "awarię lub kolizję.")


def qr_png(data: str, scale: int = 10) -> bytes:
    """A QR code as PNG. Error correction "Q" survives a scuffed sticker."""
    out = io.BytesIO()
    segno.make(data, error="q", micro=False).save(out, kind="png", scale=scale, border=4)
    return out.getvalue()


def labels_pdf(labels: Sequence[Label], title: str = "GARAZ — etykiety QR wózków") -> bytes:
    """An A4 sheet (or several) of labels: QR on the left, title and subtitle on the right."""
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    pdf.setTitle(title)
    page_w, page_h = A4
    cell_w, cell_h = page_w / COLUMNS, page_h / ROWS
    per_page = COLUMNS * ROWS

    for i, label in enumerate(labels):
        if i and i % per_page == 0:
            pdf.showPage()
        slot = i % per_page
        x = (slot % COLUMNS) * cell_w
        y = page_h - (slot // COLUMNS + 1) * cell_h
        _draw_label(pdf, label, x, y, cell_w, cell_h)

    pdf.save()
    return out.getvalue()


def _draw_label(pdf: canvas.Canvas, label: Label, x: float, y: float, w: float, h: float) -> None:
    # A light cut line, so the sheet works on plain paper too.
    pdf.setStrokeGray(0.8)
    pdf.setLineWidth(0.3)
    pdf.rect(x, y, w, h)

    qr_x = x + 6 * mm
    qr_y = y + (h - _QR_SIZE) / 2
    _draw_qr(pdf, label.qr_data, qr_x, qr_y, _QR_SIZE)

    text_x = qr_x + _QR_SIZE + 4 * mm
    text_w = x + w - 5 * mm - text_x
    pdf.setFillGray(0)
    pdf.setFont(_FONT, _fit(label.title, text_w, 26))
    pdf.drawString(text_x, y + h / 2 + 4 * mm, label.title)
    pdf.setFont(_FONT, _fit(label.subtitle, text_w, 9))
    pdf.drawString(text_x, y + h / 2 - 3 * mm, label.subtitle)
    pdf.setFont(_FONT, 7)
    pdf.setFillGray(0.35)
    for n, line in enumerate(label.note):
        pdf.drawString(text_x, y + h / 2 - (12 + 3.5 * n) * mm, line)


def _draw_qr(pdf: canvas.Canvas, data: str, x: float, y: float, size: float) -> None:
    """Draw the code as vector squares: sharp at any printer resolution."""
    rows = list(segno.make(data, error="q", micro=False).matrix_iter(scale=1, border=2))
    module = size / len(rows)
    pdf.setFillGray(0)
    for r, row in enumerate(rows):
        for c, dark in enumerate(row):
            if dark:
                pdf.rect(x + c * module, y + size - (r + 1) * module, module, module, stroke=0, fill=1)


def _fit(text: str, width: float, size: float) -> float:
    """The largest font size up to `size` at which `text` fits `width`."""
    while size > 6 and pdfmetrics.stringWidth(text, _FONT, size) > width:
        size -= 0.5
    return size
