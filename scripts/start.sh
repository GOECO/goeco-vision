#!/usr/bin/env bash
# start.sh — Khởi động GOECO Vision (PostgreSQL + migration + seed + server)
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[GOECO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERR]${NC}   $1"; exit 1; }

PORT=${PORT:-8000}
ENV_FILE=".env"

# 1. Load .env
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs) 2>/dev/null || true
    info "Loaded $ENV_FILE"
else
    warn ".env not found — using defaults (SQLite)"
    export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./goeco_vision.db}"
    export JWT_SECRET="${JWT_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
fi

# 2. Check Python
python3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'" \
    || error "Python 3.11+ required"
info "Python $(python3 --version)"

# 3. Install deps
if ! python3 -c "import fastapi" &>/dev/null; then
    info "Installing dependencies..."
    pip install -q -r requirements.txt
fi

# 4. Create upload dirs
mkdir -p uploads/verifications uploads/shippers
info "Upload directories ready"

# 5. Run Alembic migration
info "Running database migrations..."
python3 -c "
from alembic.config import main
main(argv=['upgrade', 'head'])
" && info "Migrations done" || warn "Migration skipped (will auto-create on startup)"

# 6. Seed demo data
if [ "${SKIP_SEED:-0}" != "1" ]; then
    info "Seeding demo data..."
    python3 scripts/seed_demo.py || warn "Seed skipped (data may already exist)"
fi

# 7. Start server
info "Starting GOECO Vision on port $PORT..."
echo ""
echo "  Dashboard : http://localhost:$PORT/dashboard"
echo "  Verify UI : http://localhost:$PORT/verify"
echo "  API Docs  : http://localhost:$PORT/docs"
echo "  Health    : http://localhost:$PORT/health"
echo ""

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --reload \
    --log-level info
