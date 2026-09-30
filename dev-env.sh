#!/usr/bin/env bash
# =============================================================================
# 开发环境搭建脚本（和生产完全隔离）
#
# 建好之后你会得到：
#   - 一个开发用 Odoo 容器（自带无头浏览器、PDF 工具、中文字体、测试依赖）
#   - 一个独立的 PostgreSQL 容器
#   - Odoo 19 社区版源码（跑测试要用）
#   - scripts/test.sh：一条命令跑测试
#
#   用法：
#     ./dev-env.sh                      # 默认：Odoo 8169 端口，PG 5442 端口
#     ./dev-env.sh --port 8170 --pg-port 5443
#     ./dev-env.sh --seed-from letaoge  # 从生产库复制一份数据当测试库
#     ./dev-env.sh --down               # 停掉开发环境（不删数据）
#     ./dev-env.sh --destroy            # 停掉并删除开发环境的数据卷
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$PROJECT_DIR/CLAUDE.md" ]] || PROJECT_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
DEV_DIR="$PROJECT_DIR/.devenv"
ODOO_PORT=8169
PG_PORT=5442
ODOO_SRC="$DEV_DIR/odoo-src"
SEED_FROM=""
PROD_PG_CONTAINER="prod-postgres"
ACTION="up"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) ODOO_PORT="$2"; shift 2 ;;
        --pg-port) PG_PORT="$2"; shift 2 ;;
        --seed-from) SEED_FROM="$2"; shift 2 ;;
        --prod-pg) PROD_PG_CONTAINER="$2"; shift 2 ;;
        --down) ACTION="down"; shift ;;
        --destroy) ACTION="destroy"; shift ;;
        -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

log() { printf '\e[1;36m==>\e[0m %s\n' "$*"; }
ok()  { printf '  \e[32m✓\e[0m %s\n' "$*"; }
die() { printf '\e[1;31m✗ %s\e[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "找不到 docker"
docker compose version >/dev/null 2>&1 || die "找不到 docker compose"

cd "$PROJECT_DIR"
mkdir -p "$DEV_DIR"

if [[ "$ACTION" != "up" ]]; then
    log "停止开发环境"
    (cd "$DEV_DIR" && docker compose down $([[ "$ACTION" == "destroy" ]] && echo "-v") 2>/dev/null || true)
    ok "已停止$([[ "$ACTION" == "destroy" ]] && echo "，数据卷已删除")"
    exit 0
fi

# ---- Odoo 源码（测试框架需要）------------------------------------------------
if [[ ! -d "$ODOO_SRC/odoo" ]]; then
    log "下载 Odoo 19 社区版源码（约 1 GB，只做一次）"
    git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git "$ODOO_SRC"
else
    ok "Odoo 源码已存在: $ODOO_SRC"
fi

# ---- 开发镜像 ---------------------------------------------------------------
cat > "$DEV_DIR/Dockerfile" <<'EOF'
FROM odoo:19
USER root
# 无头浏览器（跑界面测试）、中文字体、条码图片渲染依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium fonts-noto-cjk poppler-utils git \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir --break-system-packages rlPyCairo websocket-client polib || \
    pip3 install --no-cache-dir rlPyCairo websocket-client polib
USER odoo
EOF

cat > "$DEV_DIR/docker-compose.yml" <<EOF
name: barcode-dev
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: postgres
    ports: ["127.0.0.1:${PG_PORT}:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  odoo:
    build: .
    depends_on: [db]
    ports: ["127.0.0.1:${ODOO_PORT}:8069"]
    environment:
      HOST: db
      USER: odoo
      PASSWORD: odoo
    volumes:
      - "${PROJECT_DIR}:/mnt/project:ro"
      - "${ODOO_SRC}:/mnt/odoo-src:ro"
      - "odoo-data:/var/lib/odoo"
    command: >
      odoo --addons-path=/mnt/odoo-src/addons,/mnt/project
           --http-port=8069 --limit-time-real=600 --workers=0
volumes:
  pgdata:
  odoo-data:
EOF

log "构建并启动开发容器（首次构建约 3-5 分钟）"
(cd "$DEV_DIR" && docker compose up -d --build)
sleep 5
docker ps --format '{{.Names}}' | grep -q barcode-dev-odoo || die "开发容器没起来，看 docker compose logs"
ok "Odoo: http://127.0.0.1:${ODOO_PORT}   PostgreSQL: 127.0.0.1:${PG_PORT}"

# ---- 测试脚本 ---------------------------------------------------------------
cat > "$PROJECT_DIR/scripts/test.sh" <<'EOF'
#!/usr/bin/env bash
# 在开发容器里跑测试
#   ./scripts/test.sh                      # 全套（7 个模块，含界面测试）
#   ./scripts/test.sh stock_barcode_ce     # 只测一个模块
#   ./scripts/test.sh stock_barcode_ce TestBarcodeV2   # 只测一个测试类
#   ./scripts/test.sh --core               # 跑 Odoo 自带库存测试做回归对照
set -euo pipefail
# 用一次性容器跑：开发容器里已有占着 8069 的 Odoo 服务，PDF 渲染会去请求它并和测试事务互相等锁
DEVENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.devenv"
ALL="barcode_camera_ce,product_barcode_quick,stock_barcode_ce,stock_barcode_print_ce,sale_barcode_ce,purchase_barcode_ce,pos_barcode_ce"
DB="test_$(date +%H%M%S)"

if [[ "${1:-}" == "--core" ]]; then
    MODULES="stock,stock_account,sale_stock,purchase_stock,stock_picking_batch,$ALL"
    TAGS="/stock,/stock_account,/sale_stock,/purchase_stock,/stock_picking_batch"
else
    MODULES="${1:-$ALL}"
    if [[ -n "${2:-}" ]]; then TAGS="/${1}:${2}"; else TAGS=$(echo "$MODULES" | sed 's/[^,]*/\/&/g'); fi
    MODULES="$MODULES,stock_account,product_expiry"
fi

echo "==> 数据库 $DB，模块 $MODULES"
docker compose --project-directory "$DEVENV" run --rm -T odoo odoo -d "$DB" --db_host=db --db_user=odoo --db_password=odoo \
    --addons-path=/mnt/odoo-src/addons,/mnt/project \
    -i "$MODULES" --test-tags="$TAGS" --stop-after-init --log-level=test --http-port=8072 2>&1 \
    | tee "/tmp/$DB.log" | grep -E "FAIL|ERROR|SUCCEEDED|tests when loading" || true
echo "==> 完整日志: /tmp/$DB.log （容器内数据库 $DB 可用 dropdb 清理）"
EOF
chmod +x "$PROJECT_DIR/scripts/test.sh"
ok "测试脚本: scripts/test.sh"

# ---- 可选：从生产库复制一份数据 ----------------------------------------------
if [[ -n "$SEED_FROM" ]]; then
    log "从生产库 $SEED_FROM 复制数据到开发库 devdb（只读导出，不动生产）"
    docker ps --format '{{.Names}}' | grep -qx "$PROD_PG_CONTAINER" \
        || die "找不到生产数据库容器 $PROD_PG_CONTAINER，用 --prod-pg 指定"
    docker exec "$PROD_PG_CONTAINER" pg_dump -U odoo -Fc "$SEED_FROM" > "$DEV_DIR/seed.dump"
    DBC=barcode-dev-db-1
    docker exec "$DBC" psql -U odoo -d postgres -c "DROP DATABASE IF EXISTS devdb" >/dev/null
    docker exec "$DBC" psql -U odoo -d postgres -c "CREATE DATABASE devdb OWNER odoo" >/dev/null
    docker exec -i "$DBC" pg_restore -U odoo -d devdb < "$DEV_DIR/seed.dump" >/dev/null 2>&1 || true
    rm -f "$DEV_DIR/seed.dump"
    ok "开发库 devdb 已就绪（附件/文件库未复制）"
    echo "     提醒：请在 devdb 里关闭所有定时任务和外发邮件，避免影响真实业务"
fi

cat <<EOF

$(printf '\e[1;32m开发环境就绪\e[0m')

常用命令：
  ./scripts/test.sh                 跑全套测试（约 5-8 分钟）
  ./scripts/test.sh stock_barcode_ce            只测扫码模块
  ./scripts/test.sh --core          跑 Odoo 自带库存测试做回归对照
  ./dev-env.sh --down               停掉开发环境
  cd .devenv && docker compose logs -f odoo     看日志

在 Claude Code 里开始长任务：
  cd $PROJECT_DIR && claude
  第一句建议说：读 CLAUDE.md 和 docs/PROJECT_HISTORY.md，然后跑 ./scripts/test.sh 确认基线

注意：本环境与生产完全隔离（端口 ${ODOO_PORT}/${PG_PORT}、独立数据卷）。
      不要把开发容器指向生产数据库：测试里包含验证、报废、盘点应用等会改库存的操作。
EOF
