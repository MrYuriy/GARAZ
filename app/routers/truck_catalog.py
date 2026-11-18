from fastapi import APIRouter, status

from app.dependencies import AdminUserDep, RequestMetaDep, StaffUserDep, TruckCatalogServiceDep
from app.schemas.truck_catalog import ManufacturerOut, NameIn, TruckModelCreate, TruckModelOut

router = APIRouter(tags=["Truck manufacturers and models"])

_IN_USE = {409: {"description": "Still used by trucks; the body lists them under `trucks` ({id, number})."}}


@router.get("/truck-manufacturers", response_model=list[ManufacturerOut])
async def list_manufacturers(staff: StaffUserDep, service: TruckCatalogServiceDep) -> list[ManufacturerOut]:
    """Every manufacturer with its models, by name. Short lists, so no paging."""
    return await service.list_manufacturers()


@router.post("/truck-manufacturers", response_model=ManufacturerOut, status_code=status.HTTP_201_CREATED)
async def create_manufacturer(
    data: NameIn, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> ManufacturerOut:
    return await service.create_manufacturer(admin, data, meta)


@router.patch("/truck-manufacturers/{manufacturer_id}", response_model=ManufacturerOut)
async def rename_manufacturer(
    manufacturer_id: int, data: NameIn, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> ManufacturerOut:
    return await service.rename_manufacturer(admin, manufacturer_id, data, meta)


@router.delete("/truck-manufacturers/{manufacturer_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_IN_USE)
async def delete_manufacturer(
    manufacturer_id: int, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> None:
    """Deletes it with its models — refused while any truck uses it."""
    await service.delete_manufacturer(admin, manufacturer_id, meta)


@router.post("/truck-models", response_model=TruckModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    data: TruckModelCreate, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> TruckModelOut:
    return await service.create_model(admin, data, meta)


@router.patch("/truck-models/{model_id}", response_model=TruckModelOut)
async def rename_model(
    model_id: int, data: NameIn, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> TruckModelOut:
    return await service.rename_model(admin, model_id, data, meta)


@router.delete("/truck-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_IN_USE)
async def delete_model(
    model_id: int, admin: AdminUserDep, service: TruckCatalogServiceDep, meta: RequestMetaDep
) -> None:
    """Refused while any truck is this model."""
    await service.delete_model(admin, model_id, meta)
