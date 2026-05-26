import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import get_db
from app.models.base import Base
import app.models.delivery
import app.models.shelf
import app.models.shipper
import app.models.user
import app.models.notification

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
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


async def _register_and_login(client, username, role="resident", building="B1", unit="1A"):
    await client.post("/api/v1/auth/register", json={
        "username": username,
        "password": "goeco123",
        "full_name": f"User {username}",
        "role": role,
        "building_id": building,
        "unit_number": unit,
    })
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "goeco123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return r.json()["access_token"]


# ── Auth ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_and_login(client):
    token = await _register_and_login(client, "resident01")
    assert token

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "resident01"
    assert r.json()["role"] == "resident"


@pytest.mark.asyncio
async def test_duplicate_username(client):
    await _register_and_login(client, "dup_user")
    r = await client.post("/api/v1/auth/register", json={
        "username": "dup_user", "password": "x", "full_name": "Dup"
    })
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_wrong_password(client):
    await _register_and_login(client, "user_pw")
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "user_pw", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_no_token(client):
    r = await client.get("/api/v1/notifications/")
    assert r.status_code == 401


# ── Notifications ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notifications_empty(client):
    token = await _register_and_login(client, "notif_user")
    r = await client.get(
        "/api/v1/notifications/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


# ── AI Agent ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_chat_mocked(client):
    """AI Agent endpoint trả đúng cấu trúc — Claude API được mock."""
    token = await _register_and_login(client, "agent_user", role="manager", building="PARK-A")

    with patch("app.services.ai_agent._get_client") as mock_get:
        mock_client = AsyncMock()
        mock_get.return_value = mock_client

        from anthropic.types import Message, TextBlock, Usage
        mock_client.messages.create = AsyncMock(return_value=Message(
            id="msg_test",
            type="message",
            role="assistant",
            content=[TextBlock(type="text", text="Tòa PARK-A hiện có 5 đơn đang chờ xử lý.")],
            model="claude-sonnet-4-6",
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=10, output_tokens=20),
        ))

        r = await client.post(
            "/api/v1/agent/chat",
            json={"message": "Tổng quan vận hành hôm nay?", "history": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data["role"] == "manager"
    assert len(data["history"]) >= 2


@pytest.mark.asyncio
async def test_agent_requires_auth(client):
    r = await client.post(
        "/api/v1/agent/chat",
        json={"message": "hello"},
    )
    assert r.status_code == 401
