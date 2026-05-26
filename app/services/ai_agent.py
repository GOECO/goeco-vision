"""
GOECO AI Operations Agent — powered by Claude claude-sonnet-4-6.

Mỗi vai trò (cư dân, shipper, ban quản lý) có system prompt riêng
và bộ tools để truy vấn dữ liệu vận hành real-time từ DB.
"""
import json
import logging
from typing import Any

import anthropic
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.delivery import Delivery, DeliveryStatus
from app.models.shelf import SmartShelf, ShelfSlot, SlotStatus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


TOOLS: list[dict] = [
    {
        "name": "get_delivery_status",
        "description": "Kiểm tra trạng thái đơn hàng theo tracking code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracking_code": {
                    "type": "string",
                    "description": "Mã tracking đơn hàng, ví dụ: GOECO-2024-001",
                }
            },
            "required": ["tracking_code"],
        },
    },
    {
        "name": "get_my_pending_deliveries",
        "description": "Lấy danh sách đơn hàng chưa lấy (arrived/verified) của cư dân hiện tại.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_shelf_availability",
        "description": "Kiểm tra kệ thông minh còn slot trống tại tòa nhà.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "ID tòa nhà, ví dụ: PARK-HILL-A",
                }
            },
        },
    },
    {
        "name": "get_building_stats",
        "description": "Thống kê vận hành tòa nhà: tổng đơn theo trạng thái, kệ thông minh, cảnh báo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {"type": "string", "description": "ID tòa nhà"}
            },
        },
    },
]

_SYSTEM = {
    UserRole.RESIDENT: (
        "Bạn là trợ lý AI cá nhân của GOECO, hỗ trợ cư dân {name} tại tòa {building}, "
        "căn hộ {unit}. Giúp kiểm tra đơn hàng, kệ thông minh, giải đáp thắc mắc dịch vụ. "
        "Trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
        "Ưu tiên thông tin cụ thể từ hệ thống thay vì câu trả lời chung chung."
    ),
    UserRole.MANAGER: (
        "Bạn là AI vận hành GOECO cho ban quản lý tòa nhà {building}. "
        "Theo dõi giao nhận, kệ thông minh, cảnh báo an ninh, phân tích dữ liệu vận hành. "
        "Cung cấp số liệu chính xác, đề xuất hành động khi có vấn đề. Tiếng Việt, chuyên nghiệp."
    ),
    UserRole.SHIPPER: (
        "Bạn là trợ lý giao nhận GOECO cho shipper {name}. "
        "Hỗ trợ kiểm tra kệ trống, xác nhận giao nhận, xử lý phát sinh. "
        "Ngắn gọn, thực tế, tập trung thông tin cần cho việc giao hàng."
    ),
    UserRole.ADMIN: (
        "Bạn là AI quản trị hệ thống GOECO. "
        "Truy cập toàn bộ dữ liệu vận hành, hỗ trợ phân tích và ra quyết định. "
        "Trả lời kỹ thuật và chuyên sâu khi cần."
    ),
}


async def _run_tool(name: str, tool_input: dict, user: User, db: AsyncSession) -> str:
    try:
        if name == "get_delivery_status":
            result = await db.execute(
                select(Delivery).where(Delivery.tracking_code == tool_input["tracking_code"])
            )
            d = result.scalar_one_or_none()
            if not d:
                return f"Không tìm thấy đơn hàng với mã {tool_input['tracking_code']}."
            return json.dumps({
                "tracking_code": d.tracking_code,
                "status": d.status.value,
                "building_id": d.building_id,
                "unit_number": d.unit_number,
                "verified_at": d.verified_at.isoformat() if d.verified_at else None,
                "ai_confidence": d.ai_confidence_score,
                "note": d.verification_note,
            }, ensure_ascii=False)

        if name == "get_my_pending_deliveries":
            query = select(Delivery).where(
                Delivery.recipient_id == user.username,
                Delivery.status.in_([DeliveryStatus.ARRIVED, DeliveryStatus.VERIFIED]),
            ).order_by(Delivery.updated_at.desc()).limit(10)
            result = await db.execute(query)
            deliveries = result.scalars().all()
            if not deliveries:
                return "Hiện không có đơn hàng nào đang chờ lấy."
            items = [
                {"tracking": d.tracking_code, "status": d.status.value, "unit": d.unit_number}
                for d in deliveries
            ]
            return json.dumps(items, ensure_ascii=False)

        if name == "get_shelf_availability":
            building_id = tool_input.get("building_id", user.building_id)
            query = select(SmartShelf).options(selectinload(SmartShelf.slots))
            if building_id:
                query = query.where(SmartShelf.building_id == building_id)
            result = await db.execute(query)
            shelves = result.scalars().all()
            summary = []
            for s in shelves:
                occupied = sum(1 for sl in s.slots if sl.status == SlotStatus.OCCUPIED)
                free = s.total_slots - occupied
                summary.append({
                    "shelf": s.name,
                    "floor": s.floor,
                    "free_slots": free,
                    "total_slots": s.total_slots,
                    "status": "full" if free == 0 else ("gần đầy" if free <= 2 else "còn trống"),
                })
            return json.dumps(summary, ensure_ascii=False) if summary else "Không tìm thấy kệ thông minh."

        if name == "get_building_stats":
            building_id = tool_input.get("building_id", user.building_id)
            q = select(Delivery.status, func.count()).group_by(Delivery.status)
            if building_id:
                q = q.where(Delivery.building_id == building_id)
            rows = (await db.execute(q)).all()
            counts = {r[0].value: r[1] for r in rows}

            shelf_q = select(SmartShelf).options(selectinload(SmartShelf.slots))
            if building_id:
                shelf_q = shelf_q.where(SmartShelf.building_id == building_id)
            shelves = (await db.execute(shelf_q)).scalars().all()
            full_shelves = sum(
                1 for s in shelves
                if sum(1 for sl in s.slots if sl.status == SlotStatus.OCCUPIED) >= s.total_slots
            )
            return json.dumps({
                "delivery_counts": counts,
                "total_shelves": len(shelves),
                "full_shelves": full_shelves,
                "alert": f"{full_shelves} kệ đầy" if full_shelves else "Không có cảnh báo",
            }, ensure_ascii=False)

    except Exception as e:
        logger.error("Tool %s error: %s", name, e)
        return f"Lỗi khi truy vấn dữ liệu: {e}"

    return "Tool không xác định."


async def chat(
    user: User,
    messages: list[dict],
    db: AsyncSession,
) -> tuple[str, list[dict]]:
    """
    Gửi tin nhắn đến AI Agent và nhận phản hồi.
    Trả về (assistant_reply, updated_messages).
    """
    system_tpl = _SYSTEM.get(user.role, _SYSTEM[UserRole.RESIDENT])
    system = system_tpl.format(
        name=user.full_name,
        building=user.building_id or "chưa xác định",
        unit=user.unit_number or "chưa xác định",
    )

    client = _get_client()
    history = list(messages)

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=history,
        )

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            reply = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return reply, history

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = await _run_tool(block.name, block.input, user, db)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    })
            history.append({"role": "user", "content": tool_results})
            continue

        break

    return "Không có phản hồi.", history
