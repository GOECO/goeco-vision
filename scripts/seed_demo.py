"""
Seed demo data cho GOECO Vision.
Chạy: python scripts/seed_demo.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from app.database import engine
    from app.models.base import Base
    from app.models.user import User, UserRole
    from app.models.delivery import Delivery, DeliveryEvent, DeliveryStatus
    from app.models.shelf import SmartShelf, ShelfSlot, SlotStatus, ShelfEvent
    from app.models.shipper import ShipperProfile
    from app.models.notification import Notification
    from app.core.security import hash_password
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from datetime import datetime, timedelta

    async with AsyncSession(engine) as session:
        # Kiểm tra đã seed chưa
        existing = await session.execute(select(User).where(User.username == "admin"))
        if existing.scalar_one_or_none():
            print("✓ Demo data đã tồn tại — bỏ qua seed.")
            return

        now = datetime.utcnow()

        # === USERS ===
        users = [
            User(username="admin",      full_name="Admin GOECO",           hashed_password=hash_password("Admin@123"),    role=UserRole.ADMIN,    building_id="PARK-HILL-A", is_active=True, created_at=now),
            User(username="manager01",  full_name="Nguyễn Văn Quản Lý",   hashed_password=hash_password("Manager@123"), role=UserRole.MANAGER,  building_id="PARK-HILL-A", is_active=True, created_at=now),
            User(username="manager02",  full_name="Trần Thị Quản Lý",     hashed_password=hash_password("Manager@123"), role=UserRole.MANAGER,  building_id="SUNRISE-B",   is_active=True, created_at=now),
            User(username="resident01", full_name="Lê Thị Cư Dân",        hashed_password=hash_password("Resident@123"),role=UserRole.RESIDENT, building_id="PARK-HILL-A", unit_number="A-1201", is_active=True, created_at=now),
            User(username="resident02", full_name="Phạm Văn Cư Dân",      hashed_password=hash_password("Resident@123"),role=UserRole.RESIDENT, building_id="PARK-HILL-A", unit_number="B-0802", is_active=True, created_at=now),
            User(username="shipper01",  full_name="Vũ Đức Shipper",       hashed_password=hash_password("Shipper@123"), role=UserRole.SHIPPER,  is_active=True, created_at=now),
        ]
        session.add_all(users)
        await session.flush()
        print(f"✓ {len(users)} users created")

        # === SHIPPERS ===
        shippers = [
            ShipperProfile(shipper_id="shipper01", name="Vũ Đức Shipper", phone="0901234567", company="GHN Express", is_active=True, registered_at=now),
            ShipperProfile(shipper_id="shipper02", name="Ngô Thị Giao",   phone="0912345678", company="J&T Express", is_active=True, registered_at=now),
        ]
        session.add_all(shippers)
        await session.flush()
        print(f"✓ {len(shippers)} shippers created")

        # === SHELVES ===
        shelf_a = SmartShelf(building_id="PARK-HILL-A", floor="1", name="Kệ A1", location_note="Gần sảnh chính, cạnh thang máy", total_slots=8, created_at=now)
        shelf_b = SmartShelf(building_id="PARK-HILL-A", floor="2", name="Kệ A2", location_note="Hành lang tầng 2", total_slots=6, created_at=now)
        shelf_c = SmartShelf(building_id="SUNRISE-B",   floor="1", name="Kệ B1", location_note="Sảnh tòa B", total_slots=10, created_at=now)
        session.add_all([shelf_a, shelf_b, shelf_c])
        await session.flush()

        # Slots cho shelf_a (2 occupied)
        for i in range(1, shelf_a.total_slots + 1):
            status = SlotStatus.OCCUPIED if i in (2, 5) else SlotStatus.EMPTY
            session.add(ShelfSlot(shelf_id=shelf_a.id, slot_number=i, status=status, occupied_since=now if status == SlotStatus.OCCUPIED else None))
        # Slots cho shelf_b
        for i in range(1, shelf_b.total_slots + 1):
            session.add(ShelfSlot(shelf_id=shelf_b.id, slot_number=i, status=SlotStatus.EMPTY))
        # Slots cho shelf_c
        for i in range(1, shelf_c.total_slots + 1):
            status = SlotStatus.OCCUPIED if i <= 7 else SlotStatus.EMPTY
            session.add(ShelfSlot(shelf_id=shelf_c.id, slot_number=i, status=status, occupied_since=now if status == SlotStatus.OCCUPIED else None))
        await session.flush()
        print(f"✓ 3 shelves + slots created")

        # === DELIVERIES ===
        deliveries_data = [
            dict(tracking_code="GOECO-2026-001", shipper_id="shipper01", recipient_id="resident01", building_id="PARK-HILL-A", unit_number="A-1201", status=DeliveryStatus.VERIFIED,   verified_at=now - timedelta(hours=2), ai_confidence_score=0.87, verification_note="✅ YOLO + Face ID — confidence 87%", created_at=now - timedelta(hours=6)),
            dict(tracking_code="GOECO-2026-002", shipper_id="shipper01", recipient_id="resident01", building_id="PARK-HILL-A", unit_number="A-1201", status=DeliveryStatus.ARRIVED,    created_at=now - timedelta(hours=4)),
            dict(tracking_code="GOECO-2026-003", shipper_id="shipper02", recipient_id="resident02", building_id="PARK-HILL-A", unit_number="B-0802", status=DeliveryStatus.IN_TRANSIT, created_at=now - timedelta(hours=2)),
            dict(tracking_code="GOECO-2026-004", shipper_id="shipper01", recipient_id="resident02", building_id="PARK-HILL-A", unit_number="B-0802", status=DeliveryStatus.COLLECTED,  created_at=now - timedelta(days=1)),
            dict(tracking_code="GOECO-2026-005", shipper_id="shipper02", recipient_id="resident01", building_id="PARK-HILL-A", unit_number="A-1201", status=DeliveryStatus.DISPUTED,   created_at=now - timedelta(days=2)),
            dict(tracking_code="GOECO-2026-006", shipper_id="shipper01", recipient_id="resident01", building_id="SUNRISE-B",   unit_number="C-0501", status=DeliveryStatus.PENDING,    created_at=now - timedelta(minutes=30)),
        ]
        delivery_objs = []
        for d in deliveries_data:
            obj = Delivery(updated_at=d.get("created_at", now), **d)
            session.add(obj)
            delivery_objs.append(obj)
        await session.flush()

        # Events
        for d in delivery_objs:
            session.add(DeliveryEvent(delivery_id=d.id, event_type="created", description="Đơn hàng được tạo", actor_id=d.shipper_id, actor_role="shipper", occurred_at=d.created_at))
            if d.status in (DeliveryStatus.ARRIVED, DeliveryStatus.VERIFIED, DeliveryStatus.COLLECTED):
                session.add(DeliveryEvent(delivery_id=d.id, event_type="status_changed", description="arrived", occurred_at=d.created_at + timedelta(hours=1)))
            if d.status == DeliveryStatus.VERIFIED:
                session.add(DeliveryEvent(delivery_id=d.id, event_type="ai_verified", description=f"YOLO confidence {d.ai_confidence_score:.0%}", occurred_at=d.verified_at))
        await session.flush()
        print(f"✓ {len(delivery_objs)} deliveries + events created")

        # === NOTIFICATIONS ===
        mgr = next(u for u in users if u.username == "manager01")
        notifs = [
            Notification(user_id=mgr.id, title="⚠️ Kệ B1 gần đầy", body="Kệ B1 tòa SUNRISE-B đang 70% (7/10 slots). Cần xử lý sớm.", notif_type="shelf_alert", is_read=False, created_at=now - timedelta(minutes=10)),
            Notification(user_id=mgr.id, title="✅ Xác thực thành công — GOECO-2026-001", body="Đơn GOECO-2026-001 đã xác thực AI. Confidence: 87%.", notif_type="verify_ok", is_read=True, read_at=now - timedelta(hours=1), delivery_id=delivery_objs[0].id, created_at=now - timedelta(hours=2)),
            Notification(user_id=mgr.id, title="⚠️ Xác thực thất bại — GOECO-2026-005", body="Đơn GOECO-2026-005 không qua xác thực. Face ID không khớp. Cần kiểm tra.", notif_type="verify_failed", is_read=False, delivery_id=delivery_objs[4].id, created_at=now - timedelta(days=2)),
        ]
        session.add_all(notifs)
        await session.flush()
        print(f"✓ {len(notifs)} notifications created")

        await session.commit()
        print("\n🎉 Seed demo data hoàn tất!")
        print("   Accounts:")
        print("   admin / Admin@123         (admin)")
        print("   manager01 / Manager@123   (manager)")
        print("   resident01 / Resident@123 (resident)")
        print("   shipper01 / Shipper@123   (shipper)")


if __name__ == "__main__":
    asyncio.run(main())
