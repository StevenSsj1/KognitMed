"""MongoDB connection tests.

MongoDB is intentionally disabled for now. The prior integration test is kept
commented below until the datastore is enabled again.
"""

# from __future__ import annotations
#
# import pytest
# from kognitmed.config import get_settings
# from kognitmed.infrastructure.database.mongo import (
#     close_mongo_client,
#     get_mongo_client,
#     ping_mongo,
# )
#
#
# @pytest.mark.asyncio
# async def test_mongo_connection() -> None:
#     """Verify MongoDB connection and ping."""
#     settings = get_settings()
#     success = await ping_mongo(settings)
#     assert success is True
#
#     client = get_mongo_client(settings)
#     assert client is not None
#
#     close_mongo_client()
