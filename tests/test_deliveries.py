import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import get_db
from app.models.base import Base
import app.models.delivery  # noqa
import app.models.shelf     # noqa

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    from main import app
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_get_delivery(client):
    r = await client.post("/api/v1/deliveries/", json={
        "tracking_code": "TRK-001",
        "shipper_id": "shipper-1",
        "recipient_id": "resident-12B",
        "building_id": "PARK-HILL-A",
        "unit_number": "12B",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending"
    assert data["tracking_code"] == "TRK-001"

    r2 = await client.get(f"/api/v1/deliveries/{data['id']}")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_delivery_not_found(client):
    r = await client.get("/api/v1/deliveries/9999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delivery_event_history(client):
    r = await client.post("/api/v1/deliveries/", json={
        "tracking_code": "TRK-002",
        "shipper_id": "s1", "recipient_id": "r1",
        "building_id": "B1", "unit_number": "1A",
    })
    did = r.json()["id"]

    events = (await client.get(f"/api/v1/deliveries/{did}/events")).json()
    assert any(e["event_type"] == "created" for e in events)


@pytest.mark.asyncio
async def test_status_change_creates_event(client):
    r = await client.post("/api/v1/deliveries/", json={
        "tracking_code": "TRK-003",
        "shipper_id": "s1", "recipient_id": "r1",
        "building_id": "B1", "unit_number": "1A",
    })
    did = r.json()["id"]
    await client.patch(f"/api/v1/deliveries/{did}", json={"status": "arrived"})

    events = (await client.get(f"/api/v1/deliveries/{did}/events")).json()
    assert any(e["event_type"] == "status_changed" for e in events)


@pytest.mark.asyncio
async def test_smart_shelf_lifecycle(client):
    # Tạo kệ 5 slot
    r = await client.post("/api/v1/shelves/", json={
        "building_id": "PARK-HILL-A",
        "floor": "1",
        "name": "Kệ A-1",
        "total_slots": 5,
    })
    assert r.status_code == 201
    shelf = r.json()
    shelf_id = shelf["id"]
    assert shelf["total_slots"] == 5
    assert shelf["occupied_slots"] == 0
    assert shelf["alert_level"] == "ok"

    # Shipper đặt hàng vào slot 1
    r2 = await client.post(f"/api/v1/shelves/{shelf_id}/slots/1/occupy", json={
        "actor_id": "shipper-1",
        "delivery_id": None,
        "notes": "Kiện hàng 500g",
    })
    assert r2.status_code == 200
    slot = r2.json()
    assert slot["status"] == "occupied"
    token = slot["access_token"]
    assert token is not None

    # Cư dân lấy hàng bằng token
    r3 = await client.post(f"/api/v1/shelves/{shelf_id}/slots/1/release", json={
        "actor_id": "resident-12B",
        "access_token": token,
    })
    assert r3.status_code == 200
    assert r3.json()["status"] == "empty"

    # Kiểm tra lịch sử sự kiện
    events = (await client.get(f"/api/v1/shelves/{shelf_id}/events")).json()
    event_types = {e["event_type"] for e in events}
    assert "item_in" in event_types
    assert "item_out" in event_types


@pytest.mark.asyncio
async def test_slot_wrong_token_rejected(client):
    r = await client.post("/api/v1/shelves/", json={
        "building_id": "B1", "floor": "2", "name": "Kệ B-2", "total_slots": 3
    })
    shelf_id = r.json()["id"]

    await client.post(f"/api/v1/shelves/{shelf_id}/slots/1/occupy", json={"actor_id": "s1"})

    r2 = await client.post(f"/api/v1/shelves/{shelf_id}/slots/1/release", json={
        "actor_id": "hacker",
        "access_token": "wrong-token-000",
    })
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_shelf_alerts(client):
    r = await client.post("/api/v1/shelves/", json={
        "building_id": "B2", "floor": "1", "name": "Kệ nhỏ", "total_slots": 2
    })
    shelf_id = r.json()["id"]

    # Lấp đầy 2/2 slot
    for i in range(1, 3):
        await client.post(f"/api/v1/shelves/{shelf_id}/slots/{i}/occupy", json={"actor_id": "s1"})

    alerts = (await client.get("/api/v1/shelves/alerts")).json()
    alert_ids = [a["id"] for a in alerts]
    assert shelf_id in alert_ids
