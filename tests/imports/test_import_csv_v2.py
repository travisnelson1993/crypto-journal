import pytest

pytest.skip(
    "Option B (full importer / lifecycle) not implemented — Option A only",
    allow_module_level=True,
)

import pytest_asyncio
from httpx import AsyncClient
from httpx import ASGITransport

from app.main import app
from app.db.database import get_db
from app.models.executions import Execution


@pytest_asyncio.fixture
async def client(async_session):
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_import_creates_executions(client, async_session):
    csv_data = """Order Time,Side,Underlying Asset,Avg Fill,Filled,Fee
2024-01-01 10:00:00,Open Long,BTCUSDT,40000,0.01,1
2024-01-01 11:00:00,Close Long,BTCUSDT,41000,0.01,1
"""

    response = await client.post(
        "/api/import/csv",
        files={"file": ("test.csv", csv_data, "text/csv")},
    )

    assert response.status_code == 200

    result = await async_session.execute(
        Execution.__table__.select()
    )
    executions = result.fetchall()

    assert len(executions) == 2


@pytest.mark.asyncio
async def test_import_is_idempotent(client, async_session):
    csv_data = """Order Time,Side,Underlying Asset,Avg Fill,Filled,Fee
2024-01-01 10:00:00,Open Long,BTCUSDT,40000,0.01,1
2024-01-01 11:00:00,Close Long,BTCUSDT,41000,0.01,1
"""

    # ---- First import
    resp1 = await client.post(
        "/api/import/csv",
        files={"file": ("test.csv", csv_data, "text/csv")},
    )
    assert resp1.status_code == 200

    # ---- Second import (same file)
    resp2 = await client.post(
        "/api/import/csv",
        files={"file": ("test.csv", csv_data, "text/csv")},
    )
    assert resp2.status_code == 200

    # ---- Assert no duplicates
    result = await async_session.execute(
        Execution.__table__.select()
    )
    executions = result.fetchall()

    assert len(executions) == 2
