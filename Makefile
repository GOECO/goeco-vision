PORT ?= 8000

.PHONY: start dev seed migrate test lint clean help

help:
	@echo "GOECO Vision — commands:"
	@echo "  make start    — Run migrations + seed + server"
	@echo "  make dev      — Dev server only (no seed)"
	@echo "  make seed     — Seed demo data"
	@echo "  make migrate  — Run Alembic migrations"
	@echo "  make test     — Run test suite"
	@echo "  make clean    — Remove .pyc, uploads cache"

start:
	@bash scripts/start.sh

dev:
	@uvicorn main:app --host 0.0.0.0 --port $(PORT) --reload --log-level info

seed:
	@python3 scripts/seed_demo.py

migrate:
	@python3 -c "from alembic.config import main; main(argv=['upgrade', 'head'])"

test:
	@pytest -x -q -k "not db_health"

clean:
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -f uploads/verifications/*.jpg 2>/dev/null || true
	@echo "Clean done."
