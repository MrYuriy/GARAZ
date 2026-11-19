# Reports and Excel exports.
from app.core.config.base import BaseConfig


class ReportConfig(BaseConfig):
    # "Wygasające uprawnienia": how many days ahead the report looks by default.
    REPORT_EXPIRING_DAYS: int = 30
    # The most rows one Excel export writes; a larger list should be filtered first.
    REPORT_MAX_ROWS: int = 20000
