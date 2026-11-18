from pydantic import BaseModel, Field, field_validator

from app.schemas.common import required


class TruckModelOut(BaseModel):
    id: int
    name: str
    # How many trucks are this model; a model in use cannot be deleted.
    truck_count: int = 0


class ManufacturerOut(BaseModel):
    id: int
    name: str
    models: list[TruckModelOut]
    # Trucks of this manufacturer, any model; one in use cannot be deleted.
    truck_count: int = 0


class NameIn(BaseModel):
    name: str = Field(max_length=64)

    _name = field_validator("name")(required)


class TruckModelCreate(NameIn):
    manufacturer_id: int
