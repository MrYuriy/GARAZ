from fastapi import APIRouter

from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.dictionaries import router as dictionaries_router
from app.routers.health_check import router as health_router
from app.routers.operators import router as operators_router
from app.routers.permits import router as permits_router
from app.routers.truck_catalog import router as truck_catalog_router
from app.routers.trucks import router as trucks_router
from app.routers.users import router as users_router

__all__ = ["router"]

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(audit_router)
router.include_router(dictionaries_router)
router.include_router(trucks_router)
router.include_router(truck_catalog_router)
router.include_router(operators_router)
router.include_router(permits_router)
