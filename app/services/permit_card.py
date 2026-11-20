"""The printed permit: form PL-FORM-QHSE-009, eight cards to an A4 sheet.

Laid out as the company's Word template: a header with the logo and the form's
code, then 2 × 4 cards to cut out, each signed by the area manager. Added to the
template: "Ważne do" (the last valid day), and the UDT number when the permit
rests on UDT.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONTS = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)
_REGULAR, _BOLD = "Helvetica", "Helvetica-Bold"
for _regular, _bold in _FONTS:
    if Path(_regular).is_file() and Path(_bold).is_file():
        pdfmetrics.registerFont(TTFont("CardFont", _regular))
        pdfmetrics.registerFont(TTFont("CardFontBold", _bold))
        _REGULAR, _BOLD = "CardFont", "CardFontBold"
        break

COLUMNS, ROWS = 2, 4
_MARGIN = 8 * mm
_HEADER_H = 20 * mm
_FOOTER_H = 6 * mm
_PAD = 3 * mm

TITLE = ("IMIENNE UPOWAŻNIENIE DO OBSŁUGI WÓZKÓW WIDŁOWYCH", "NA TERENIE UŻYTKOWANYM PRZEZ CEVA")
NOTICE = (
    "Pouczenie: Zezwolenie jest ważne na terenie zakładu pracy, który je wydał. "
    "Prowadzenie pojazdu bez zezwolenia jest zabronione"
)


@dataclass(frozen=True)
class Form:
    """The form's own header: code, version, date it came into use."""

    code: str
    version: str
    introduced: str
    logo: bytes | None = None


@dataclass(frozen=True)
class Card:
    number: str
    issued_on: date
    valid_until: date
    full_name: str
    location: str
    employer: str
    category: str
    udt_number: str | None
    # Every truck type the form names, in order, and whether this permit covers it.
    truck_types: Sequence[tuple[str, bool]]


def cards_pdf(cards: Sequence[Card], form: Form, title: str = "Upoważnienia do obsługi wózków") -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    pdf.setTitle(title)
    page_w, page_h = A4
    cell_w = (page_w - 2 * _MARGIN) / COLUMNS
    cell_h = (page_h - 2 * _MARGIN - _HEADER_H - _FOOTER_H) / ROWS
    top = page_h - _MARGIN - _HEADER_H
    per_page = COLUMNS * ROWS
    logo = _logo(form.logo)

    for i, card in enumerate(cards):
        if i % per_page == 0:
            if i:
                pdf.showPage()
            _header(pdf, form, logo, page_w, page_h)
            _footer(pdf, page_w)
        slot = i % per_page
        x = _MARGIN + (slot % COLUMNS) * cell_w
        y = top - (slot // COLUMNS + 1) * cell_h
        _card(pdf, card, form, x, y, cell_w, cell_h)
    if not cards:
        _header(pdf, form, logo, page_w, page_h)
        _footer(pdf, page_w)
    pdf.save()
    return out.getvalue()


def _logo(content: bytes | None) -> ImageReader | None:
    if not content:
        return None
    try:
        return ImageReader(io.BytesIO(content))
    except Exception:  # noqa: BLE001 — a broken logo must not stop printing
        return None


def _header(pdf: canvas.Canvas, form: Form, logo: ImageReader | None, page_w: float, page_h: float) -> None:
    x0, x1 = _MARGIN, page_w - _MARGIN
    y1 = page_h - _MARGIN
    y0 = y1 - _HEADER_H + 3 * mm
    h = y1 - y0
    logo_w, form_w = 38 * mm, 30 * mm
    pdf.setStrokeGray(0)
    pdf.setLineWidth(0.6)
    pdf.rect(x0, y0, x1 - x0, h)
    pdf.line(x0 + logo_w, y0, x0 + logo_w, y1)
    pdf.line(x0 + logo_w + form_w, y0, x0 + logo_w + form_w, y1)
    mid = y0 + h / 2
    pdf.line(x0 + logo_w + form_w, mid, x1, mid)

    if logo is not None:
        iw, ih = logo.getSize()
        scale = min((logo_w - 4 * mm) / iw, (h - 4 * mm) / ih)
        w, hh = iw * scale, ih * scale
        pdf.drawImage(logo, x0 + (logo_w - w) / 2, y0 + (h - hh) / 2, w, hh, mask="auto")

    pdf.setFillGray(0)
    pdf.setFont(_BOLD, 9)
    pdf.drawCentredString(x0 + logo_w + form_w / 2, mid - 1.2 * mm, "FORMULARZ")
    text_x = x0 + logo_w + form_w + 2 * mm
    pdf.setFont(_BOLD, 8)
    pdf.drawString(text_x, mid + h / 4 - 1.2 * mm, "TYTUŁ: Imienne upoważnienie do obsługi wózków")
    pdf.setFont(_REGULAR, 6.5)
    pdf.drawString(text_x, mid - h / 4 + 2.2 * mm, f"NR DOKUMENTU: {form.code}")
    pdf.drawString(
        text_x,
        mid - h / 4 - 1.6 * mm,
        f"STRONY: 1 z 1   |   NR WERSJI: {form.version}   |   STATUS: obowiązujący   |   "
        f"DATA WPROWADZENIA: {form.introduced}",
    )


def _footer(pdf: canvas.Canvas, page_w: float) -> None:
    pdf.setFont(_REGULAR, 6.5)
    pdf.setFillGray(0.35)
    pdf.drawCentredString(page_w / 2, _MARGIN, "Niekontrolowane po wydrukowaniu")
    pdf.setFillGray(0)


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _card(pdf: canvas.Canvas, card: Card, form: Form, x: float, y: float, w: float, h: float) -> None:
    # Dashed cut line around each card.
    pdf.setStrokeGray(0.55)
    pdf.setLineWidth(0.4)
    pdf.setDash(2, 2)
    pdf.rect(x + 1 * mm, y + 1 * mm, w - 2 * mm, h - 2 * mm)
    pdf.setDash()
    pdf.setStrokeGray(0)

    left = x + _PAD + 1 * mm
    right = x + w - _PAD - 1 * mm
    width = right - left
    cy = y + h - _PAD - 1 * mm  # the baseline we write down from

    pdf.setFillGray(0)
    pdf.setFont(_BOLD, 6.8)
    for line in TITLE:
        cy -= 3 * mm
        pdf.drawCentredString((left + right) / 2, cy, line)
    cy -= 2 * mm
    pdf.setFillGray(0.6)
    pdf.rect(left, cy, width, 1.2 * mm, stroke=0, fill=1)
    pdf.setFillGray(0)

    def field(label: str, value: str, at: float, until: float, size: float = 7.5) -> None:
        pdf.setFont(_REGULAR, 6.5)
        pdf.drawString(at, cy, label)
        start = at + pdfmetrics.stringWidth(label, _REGULAR, 6.5) + 1.2 * mm
        room = until - start
        while size > 5 and pdfmetrics.stringWidth(value, _BOLD, size) > room:
            size -= 0.25
        pdf.setFont(_BOLD, size)
        pdf.drawString(start, cy, value)

    half = left + width * 0.55
    cy -= 4.4 * mm
    field("Nr uprawnienia:", card.number, left, half - 2 * mm, 8.5)
    field("Data wydania:", _day(card.issued_on), half, right)
    cy -= 4 * mm
    field("Ważne do:", _day(card.valid_until), half, right)
    field("Imię i nazwisko:", "", left, half)  # label only; the name gets its own full line
    cy -= 3.6 * mm
    field("", card.full_name, left, right, 9)
    cy -= 4 * mm
    field("Lokalizacja:", card.location, left, half - 2 * mm)
    field("Firma:", card.employer, half, right)

    cy -= 4.4 * mm
    udt_room = 32 * mm
    field("*Rodzaj uprawnień:", card.category, left, right - udt_room)
    _checkbox(pdf, right - udt_room + 2 * mm, cy, bool(card.udt_number))
    pdf.setFont(_REGULAR, 6.5)
    pdf.drawString(right - udt_room + 5.5 * mm, cy, "UDT")
    if card.udt_number:
        number = f"nr {card.udt_number}"
        size = 7
        room = udt_room - 12 * mm
        while size > 5 and pdfmetrics.stringWidth(number, _BOLD, size) > room:
            size -= 0.25
        pdf.setFont(_BOLD, size)
        pdf.drawString(right - udt_room + 11.5 * mm, cy, number)

    cy -= 4 * mm
    cy = _truck_types(pdf, card.truck_types, left, right, cy)

    pdf.setFont(_REGULAR, 5.6)
    for line in simpleSplit(NOTICE, _REGULAR, 5.6, width):
        cy -= 2.5 * mm
        pdf.drawString(left, cy, line)
    pdf.setFillGray(0.3)
    pdf.setFont(_REGULAR, 5)
    cy -= 2.4 * mm
    pdf.drawString(left, cy, "*wpisz najwyższe uprawnienia      **skreśl, usuń niedotyczące")
    pdf.setFillGray(0)

    # The bottom: the form's code on the left, the manager's signature on the right.
    base = y + _PAD + 1.5 * mm
    pdf.setFont(_REGULAR, 5.5)
    pdf.drawString(left, base, form.code)
    sign_w = width * 0.5
    pdf.setLineWidth(0.4)
    pdf.setDash(1, 1.2)
    pdf.line(right - sign_w, base + 4 * mm, right, base + 4 * mm)
    pdf.setDash()
    pdf.drawCentredString(right - sign_w / 2, base, "Podpis kierownika obszaru")


def _checkbox(pdf: canvas.Canvas, x: float, baseline: float, checked: bool) -> None:
    size = 2.6 * mm
    y = baseline - 0.4 * mm
    pdf.setLineWidth(0.5)
    pdf.rect(x, y, size, size)
    if checked:
        pdf.line(x + 0.5 * mm, y + 0.5 * mm, x + size - 0.5 * mm, y + size - 0.5 * mm)
        pdf.line(x + 0.5 * mm, y + size - 0.5 * mm, x + size - 0.5 * mm, y + 0.5 * mm)


def _truck_types(pdf: canvas.Canvas, types: Sequence[tuple[str, bool]], left: float, right: float, cy: float) -> float:
    """ "**Upoważnienie dotyczy wózków:" then every type, the ones not covered struck out."""
    label, size = "**Upoważnienie dotyczy wózków:", 6.3
    pdf.setFont(_REGULAR, 6.5)
    pdf.drawString(left, cy, label)
    at = left + pdfmetrics.stringWidth(label, _REGULAR, 6.5) + 1.2 * mm
    for n, (name, covered) in enumerate(types):
        text = name + ("," if n < len(types) - 1 else "")
        font = _BOLD if covered else _REGULAR
        text_w = pdfmetrics.stringWidth(text, font, size)
        if at + text_w > right:
            cy -= 2.9 * mm
            at = left
        pdf.setFont(font, size)
        pdf.setFillGray(0 if covered else 0.45)
        pdf.drawString(at, cy, text)
        if not covered:
            pdf.setLineWidth(0.5)
            pdf.setStrokeGray(0.2)
            strike = pdfmetrics.stringWidth(name, font, size)
            pdf.line(at, cy + size * 0.32, at + strike, cy + size * 0.32)
            pdf.setStrokeGray(0)
        at += text_w + pdfmetrics.stringWidth(" ", font, size)
    pdf.setFillGray(0)
    return cy
