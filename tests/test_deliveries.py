import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import get_db
from app.models.base import Base
import app.models.delivery  # noqa
import app.models.shelf     # noqa
import app.models.shipper   # noqa

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


# ── Health ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_db_health(client):
    r = await client.get("/health/db")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Deliveries ───────────────────────────────────────────────────────────────

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


# ── Smart Shelf ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smart_shelf_lifecycle(client):
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

    r3 = await client.post(f"/api/v1/shelves/{shelf_id}/slots/1/release", json={
        "actor_id": "resident-12B",
        "access_token": token,
    })
    assert r3.status_code == 200
    assert r3.json()["status"] == "empty"

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
    for i in range(1, 3):
        await client.post(f"/api/v1/shelves/{shelf_id}/slots/{i}/occupy", json={"actor_id": "s1"})
    alerts = (await client.get("/api/v1/shelves/alerts")).json()
    assert shelf_id in [a["id"] for a in alerts]


# ── Shipper / Face ID ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_shipper(client):
    r = await client.post("/api/v1/shippers/", json={
        "shipper_id": "ghn-001",
        "name": "Nguyễn Văn A",
        "phone": "0901234567",
        "company": "GHN",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["shipper_id"] == "ghn-001"
    assert data["has_face_id"] == False  # chưa upload ảnh


@pytest.mark.asyncio
async def test_duplicate_shipper_rejected(client):
    payload = {"shipper_id": "ghn-dup", "name": "Trùng"}
    await client.post("/api/v1/shippers/", json=payload)
    r2 = await client.post("/api/v1/shippers/", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_register_face_no_face_in_image(client):
    """Upload ảnh trắng → API trả 422 vì không phát hiện khuôn mặt."""
    import io
    from PIL import Image as PILImage

    await client.post("/api/v1/shippers/", json={"shipper_id": "ghn-face-test", "name": "Test"})

    img = PILImage.new("RGB", (320, 240), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    r = await client.post(
        "/api/v1/shippers/ghn-face-test/face",
        files={"photo": ("blank.jpg", buf, "image/jpeg")},
    )
    assert r.status_code == 422


# ── Dashboard ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_renders(client):
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "GOECO Vision" in r.text


@pytest.mark.asyncio
async def test_dashboard_stats_api(client):
    r = await client.get("/api/v1/dashboard/stats")
    assert r.status_code == 200
    data = r.json()
    assert "deliveries" in data
    assert "shelves" in data
    assert data["deliveries"]["total"] >= 0
