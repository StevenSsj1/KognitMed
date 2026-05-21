"""Database connection tests."""

from __future__ import annotations

import pytest
from kognitmed.config import get_settings
from kognitmed.infrastructure.database.mongo import ping_mongo, close_mongo_client, get_mongo_client


@pytest.mark.asyncio
async def test_mongo_connection() -> None:
    """Verify MongoDB connection and ping."""
    settings = get_settings()
    # Ping should connect successfully if MongoDB is running
    success = await ping_mongo(settings)
    assert success is True

    # Check that client was created
    client = get_mongo_client(settings)
    assert client is not None

    # Close connection
    close_mongo_client()
