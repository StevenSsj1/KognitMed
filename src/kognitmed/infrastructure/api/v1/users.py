"""Users API — query insured users."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from kognitmed.application.users_service.service import UsersService
from kognitmed.dependencies import get_users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/")
async def list_users(
    svc: Annotated[UsersService, Depends(get_users_service)],
) -> list[dict]:
    return await svc.get_all()


@router.get("/cedula/{cedula}")
async def get_by_cedula(
    cedula: str,
    svc: Annotated[UsersService, Depends(get_users_service)],
) -> dict:
    user = await svc.get_by_cedula(cedula)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.get("/seguro/{seguro}")
async def get_by_seguro(
    seguro: str,
    svc: Annotated[UsersService, Depends(get_users_service)],
) -> list[dict]:
    return await svc.get_by_seguro(seguro)
