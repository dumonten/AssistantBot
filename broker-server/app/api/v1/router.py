from fastapi import APIRouter

from api.v1.routes import root

# Main API router with common configuration
api_router = APIRouter(
    prefix="",
    responses={404: {"description": "Endpoint not found"}},
)

# Include sub-routers for different API sections
api_router.include_router(root.router, tags=["Root"])
