from enum import StrEnum


class BaseStrEnum(StrEnum):
    # StrEnum with a convenience .list() of values.
    @classmethod
    def list(cls) -> list[str]:
        return [member.value for member in cls]
