"""MongoDB connection helper.

MongoDB is intentionally disabled for now. The prior implementation is kept
commented below so it can be restored when this datastore is used again.
"""

# from __future__ import annotations
#
# import structlog
# from motor.motor_asyncio import AsyncIOMotorClient
# from kognitmed.config import Settings
#
# log = structlog.get_logger(__name__)
#
# _mongo_client: AsyncIOMotorClient | None = None
#
#
# def get_mongo_client(settings: Settings) -> AsyncIOMotorClient:
#     """Retrieve or initialize the global AsyncIOMotorClient."""
#     global _mongo_client
#     if _mongo_client is None:
#         log.info(
#             "database_connecting",
#             host=settings.mongo_host,
#             port=settings.mongo_port,
#             db=settings.mongo_db,
#         )
#         _mongo_client = AsyncIOMotorClient(
#             settings.mongo_uri,
#             serverSelectionTimeoutMS=5000,
#             connectTimeoutMS=5000,
#         )
#     return _mongo_client
#
#
# def close_mongo_client() -> None:
#     """Close the global database client if initialized."""
#     global _mongo_client
#     if _mongo_client is not None:
#         log.info("database_connection_closing")
#         _mongo_client.close()
#         _mongo_client = None
#
#
# async def ping_mongo(settings: Settings) -> bool:
#     """Send a ping command to verify database connectivity."""
#     client = get_mongo_client(settings)
#     try:
#         await client[settings.mongo_db].command("ping")
#         log.info("database_connected", host=settings.mongo_host, db=settings.mongo_db)
#         return True
#     except Exception as e:
#         log.error("database_connection_failed", error=str(e))
#         return False
