"""Users service — seed and query insured users from MongoDB."""

from __future__ import annotations

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

log = structlog.get_logger(__name__)

COLLECTION = "users"

SEED_USERS = [
    {"nombre": "María López Gutiérrez", "cedula": "1712345678", "seguro": "saludsa"},
    {"nombre": "Carlos Andrade Vega", "cedula": "0923456789", "seguro": "humana"},
    {"nombre": "Ana Belén Córdova", "cedula": "0104567890", "seguro": "bupa"},
    {"nombre": "Luis Fernando Paredes", "cedula": "1715678901", "seguro": "bmi"},
    {"nombre": "Gabriela Salazar Mena", "cedula": "0926789012", "seguro": "ecuasanitas"},
]


class UsersService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[COLLECTION]

    async def seed_if_empty(self) -> int:
        """Insert seed users only if the collection is empty. Returns inserted count."""
        count = await self._col.count_documents({})
        if count > 0:
            log.info("users_already_seeded", count=count)
            return 0
        await self._col.insert_many(SEED_USERS)
        log.info("users_seeded", count=len(SEED_USERS))
        return len(SEED_USERS)

    async def get_all(self) -> list[dict]:
        cursor = self._col.find({}, {"_id": 0})
        return await cursor.to_list(length=100)

    async def get_by_cedula(self, cedula: str) -> dict | None:
        return await self._col.find_one({"cedula": cedula}, {"_id": 0})

    async def get_by_seguro(self, seguro: str) -> list[dict]:
        cursor = self._col.find({"seguro": seguro.lower()}, {"_id": 0})
        return await cursor.to_list(length=100)
