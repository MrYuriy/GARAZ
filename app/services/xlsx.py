"""Excel files for the reports and list exports.

One sheet per table: a bold header row that stays in view, a filter on it,
and columns wide enough to read. Times are written in the warehouse's local
time (Excel cells carry no zone) and dates as real dates, so Excel can sort and
filter them.
"""

import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.time import local_zone

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill("solid", fgColor="DDE3EA")
_MAX_WIDTH = 60


@dataclass
class Sheet:
    title: str
    headers: Sequence[str]
    rows: Iterable[Sequence[Any]]


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(local_zone()).replace(tzinfo=None, microsecond=0)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return "TAK" if value else "NIE"
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value)
    return value


def _width(value: Any) -> int:
    if isinstance(value, datetime):
        return 16
    if isinstance(value, date):
        return 10
    return len(str(value)) if value is not None else 0


def workbook(*sheets: Sheet) -> bytes:
    """The sheets as an .xlsx file."""
    book = Workbook()
    book.remove(book.active)
    for sheet in sheets:
        ws = book.create_sheet(sheet.title[:31])  # Excel's limit on a sheet name
        ws.append(list(sheet.headers))
        widths = [len(h) for h in sheet.headers]
        for row in sheet.rows:
            values = [_cell(v) for v in row]
            ws.append(values)
            widths = [max(w, _width(v)) for w, v in zip(widths, values, strict=True)]
        for column, cell in enumerate(ws[1], start=1):
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            ws.column_dimensions[get_column_letter(column)].width = min(widths[column - 1] + 2, _MAX_WIDTH)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, datetime):
                    cell.number_format = "yyyy-mm-dd hh:mm"
                elif isinstance(cell.value, date):
                    cell.number_format = "yyyy-mm-dd"
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
