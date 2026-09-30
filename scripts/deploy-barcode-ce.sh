#!/usr/bin/env bash
# =============================================================================
# Odoo 19 扫码套件 部署脚本
#
#   用法:
#     ./deploy-barcode-ce.sh                     # 用下面的默认值部署（staging）
#     ./deploy-barcode-ce.sh --prod              # 部署到生产
#     ./deploy-barcode-ce.sh --db letaoge --container prod-odoo
#     ./deploy-barcode-ce.sh --check             # 只做环境检查，不改任何东西
#
#   要求: 本脚本与 odoo19_barcode_ce_*.zip 放在同一目录下。
# =============================================================================
set -euo pipefail

# ---- 默认值（按需修改）-------------------------------------------------------
CONTAINER="staging-odoo"
DB="staging"
ADDONS_DIR="/opt/prod-apps/odoo/addons"
CONTAINER_ADDONS="/mnt/extra-addons"
BACKUP_DIR="/opt/prod-apps/backups"
PROD_CONTAINER="prod-odoo"
PROD_DB="letaoge"
DO_BACKUP=1
CHECK_ONLY=0

MODULES_INSTALL="stock_barcode_ce,stock_barcode_print_ce"
MODULES_ALL="barcode_camera_ce,product_barcode_quick,stock_barcode_ce,stock_barcode_print_ce,sale_barcode_ce,purchase_barcode_ce,pos_barcode_ce"

# ---- 参数 -------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prod) CONTAINER="$PROD_CONTAINER"; DB="$PROD_DB"; shift ;;
        --container) CONTAINER="$2"; shift 2 ;;
        --db) DB="$2"; shift 2 ;;
        --addons) ADDONS_DIR="$2"; shift 2 ;;
        --no-backup) DO_BACKUP=0; shift ;;
        --check) CHECK_ONLY=1; shift ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 模块来源：优先用同目录/上级目录/dist 里的 zip；没有 zip 就直接用项目源码目录
ZIP="$(ls -1 "$SCRIPT_DIR"/odoo19_barcode_ce_*.zip "$SCRIPT_DIR"/dist/odoo19_barcode_ce_*.zip \
        "$SCRIPT_DIR"/../odoo19_barcode_ce_*.zip "$SCRIPT_DIR"/../dist/odoo19_barcode_ce_*.zip \
        2>/dev/null | sort | tail -1 || true)"
SRC_DIR=""
if [[ -z "$ZIP" ]]; then
    for cand in "$SCRIPT_DIR" "$SCRIPT_DIR/.."; do
        [[ -d "$cand/stock_barcode_ce" ]] && SRC_DIR="$(cd "$cand" && pwd)" && break
    done
fi
log()  { printf '\e[1;36m==>\e[0m %s\n' "$*"; }
ok()   { printf '  \e[32m✓\e[0m %s\n' "$*"; }
warn() { printf '  \e[33m!\e[0m %s\n' "$*"; }
die()  { printf '\e[1;31m✗ %s\e[0m\n' "$*" >&2; exit 1; }

# ---- 1. 环境检查 -------------------------------------------------------------
log "检查环境"
command -v docker >/dev/null || die "找不到 docker"
if [[ -n "$ZIP" ]]; then
    ok "模块来源: 安装包 $(basename "$ZIP")"
elif [[ -n "$SRC_DIR" ]]; then
    ok "模块来源: 源码目录 $SRC_DIR"
else
    die "找不到模块：既没有 odoo19_barcode_ce_*.zip，也不在项目源码目录里"
fi
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || die "容器 $CONTAINER 没有在运行"
ok "容器: $CONTAINER"
[[ -d "$ADDONS_DIR" ]] || die "addons 目录不存在: $ADDONS_DIR"
ok "addons 目录: $ADDONS_DIR"

DB_EXISTS=$(docker exec "$CONTAINER" bash -lc "psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw '$DB' && echo yes || echo unknown")
[[ "$DB_EXISTS" == "unknown" ]] && warn "无法在容器内确认数据库 $DB（通常正常，数据库在另一个容器里）"

WK=$(docker exec "$CONTAINER" wkhtmltopdf --version 2>/dev/null | head -1 || true)
if [[ "$WK" == *"with patched qt"* ]]; then
    ok "PDF 工具: $WK"
else
    warn "wkhtmltopdf 不是 patched qt 版本（$WK），热敏标签 PDF 尺寸可能不准；直连打印不受影响"
fi

PY_PIL=$(docker exec "$CONTAINER" python3 -c "import PIL, sys; sys.stdout.write(PIL.__version__)" 2>/dev/null || true)
[[ -n "$PY_PIL" ]] && ok "Pillow: $PY_PIL（标签文字渲染需要）" || warn "容器内没有 Pillow，标签直连打印会失败"

WORKERS=$(docker exec "$CONTAINER" bash -lc "grep -E '^workers' /etc/odoo/odoo.conf 2>/dev/null | head -1" || true)
[[ -n "$WORKERS" ]] && ok "并发配置: ${WORKERS// /}（实时刷新需要 workers>0）" || warn "odoo.conf 里没有 workers 设置，实时刷新会退回为定时刷新"

if [[ "$CHECK_ONLY" == "1" ]]; then
    log "只做检查，未做任何修改"
    exit 0
fi

# ---- 2. 备份 ----------------------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ "$DO_BACKUP" == "1" ]]; then
    log "备份现有模块目录"
    mkdir -p "$BACKUP_DIR"
    BACKUP="$BACKUP_DIR/barcode-addons-$STAMP.tar.gz"
    EXISTING=()
    for m in ${MODULES_ALL//,/ }; do
        [[ -d "$ADDONS_DIR/$m" ]] && EXISTING+=("$m")
    done
    if [[ ${#EXISTING[@]} -gt 0 ]]; then
        tar -czf "$BACKUP" -C "$ADDONS_DIR" "${EXISTING[@]}"
        ok "已备份到 $BACKUP"
    else
        ok "首次安装，无需备份"
    fi
    warn "数据库没有备份：正式库请先自行 pg_dump 再继续"
fi

# ---- 3. 解压模块 -------------------------------------------------------------
log "复制模块到 $ADDONS_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [[ -n "$ZIP" ]]; then
    unzip -q "$ZIP" -d "$TMP"
else
    for m in ${MODULES_ALL//,/ }; do
        cp -r "$SRC_DIR/$m" "$TMP/" 2>/dev/null || true
    done
    cp "$SRC_DIR/docs/README_安装与验收.md" "$TMP/" 2>/dev/null || true
    find "$TMP" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
fi
for m in ${MODULES_ALL//,/ }; do
    [[ -d "$TMP/$m" ]] || die "包里缺少模块 $m"
    rm -rf "${ADDONS_DIR:?}/$m"
    cp -r "$TMP/$m" "$ADDONS_DIR/"
    ok "$m $(python3 - "$ADDONS_DIR/$m/__manifest__.py" <<'PY' 2>/dev/null || echo ""
import ast, sys
print(ast.literal_eval(open(sys.argv[1]).read()).get("version", ""))
PY
)"
done
cp "$TMP/README_安装与验收.md" "$ADDONS_DIR/" 2>/dev/null || true
cp "$TMP/stock_barcode_print_ce/tools/label_print_agent.py" "$SCRIPT_DIR/" 2>/dev/null && \
    ok "打印代理脚本已复制到 $SCRIPT_DIR/label_print_agent.py"
chown -R "$(stat -c '%u:%g' "$ADDONS_DIR")" "$ADDONS_DIR" 2>/dev/null || true

# ---- 4. 安装 / 升级 ----------------------------------------------------------
INSTALLED=$(docker exec "$CONTAINER" bash -lc "true" >/dev/null 2>&1 && echo ok || echo fail)
[[ "$INSTALLED" == "ok" ]] || die "无法在容器内执行命令"

log "更新模块列表并安装/升级（数据库 $DB）"
warn "这会短暂中断 Odoo 服务，请确认扫码员已暂停作业"
docker exec "$CONTAINER" odoo -d "$DB" --stop-after-init --log-level=warn \
    -i "$MODULES_INSTALL" -u "$MODULES_ALL" \
    || die "安装/升级失败，请查看上面的日志；模块目录已备份在 $BACKUP_DIR"
ok "安装/升级完成"

# ---- 5. 重启并检查 -----------------------------------------------------------
log "重启 $CONTAINER"
docker restart "$CONTAINER" >/dev/null
for i in $(seq 1 30); do
    sleep 2
    if docker logs --since 1m "$CONTAINER" 2>&1 | grep -q "HTTP service (werkzeug) running"; then
        ok "Odoo 已启动"
        break
    fi
    [[ $i == 30 ]] && warn "未在 60 秒内看到启动日志，请手动检查 docker logs $CONTAINER"
done

ERRORS=$(docker logs --since 2m "$CONTAINER" 2>&1 | grep -c " ERROR " || true)
[[ "$ERRORS" == "0" ]] && ok "启动日志无报错" || warn "启动日志有 $ERRORS 条 ERROR，请检查: docker logs --since 2m $CONTAINER"

cat <<EOF

$(printf '\e[1;32m部署完成\e[0m')  容器=$CONTAINER  数据库=$DB

接下来：
  1. 浏览器打开 Odoo → 顶部菜单「条码」，用手机扫一单验收。
  2. 标签直连打印：在「条码 → 配置 → 标签打印」里新建打印代理和打印机，
     然后在仓库电脑上运行（本目录已备好脚本）：
       python3 label_print_agent.py --url https://<你的 Odoo 域名> --token <代理令牌> --db $DB
  3. 验收清单见 $ADDONS_DIR/README_安装与验收.md
  4. 如需回滚：
$( [[ "$DO_BACKUP" == "1" && -f "${BACKUP:-}" ]] \
     && echo "       tar -xzf $BACKUP -C $ADDONS_DIR && docker restart $CONTAINER" \
     || echo "       本次未备份（--no-backup 或首次安装），回滚请重新部署上一版模块包" )
EOF
