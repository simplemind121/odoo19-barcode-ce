#!/usr/bin/env bash
# =============================================================================
# 把本项目推送到 GitHub 开源仓库（首次发布 / 后续更新都用它）
#
#   前提：本机装了 git，并且能以你的 GitHub 账号推送
#         （已登录 gh CLI，或配置了 SSH key，或推送时输入 用户名 + Personal Access Token）
#
#   用法：
#     ./publish-to-github.sh                       # 推到 simplemind121/odoo19-barcode-ce
#     ./publish-to-github.sh --repo 别的仓库名
#     ./publish-to-github.sh --owner 组织名 --repo 仓库名
#     ./publish-to-github.sh --ssh                 # 用 SSH 方式推送
#     ./publish-to-github.sh --message "修了 xxx"  # 自定义提交说明
# =============================================================================
set -euo pipefail

OWNER="simplemind121"
REPO="odoo19-barcode-ce"
BRANCH="main"
USE_SSH=0
MESSAGE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --owner) OWNER="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --branch) BRANCH="$2"; shift 2 ;;
        --ssh) USE_SSH=1; shift ;;
        --message|-m) MESSAGE="$2"; shift 2 ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log() { printf '\e[1;36m==>\e[0m %s\n' "$*"; }
ok()  { printf '  \e[32m✓\e[0m %s\n' "$*"; }
die() { printf '\e[1;31m✗ %s\e[0m\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "找不到 git"
[[ -f README.md && -d stock_barcode_ce ]] || die "请在项目根目录下运行（或用 scripts/ 里的这个脚本）"

# 补全 LGPL-3 全文（开源仓库需要完整许可证文本）
if ! grep -q "GNU LESSER GENERAL PUBLIC LICENSE" LICENSE 2>/dev/null; then
    log "下载 LGPL-3 许可证全文"
    if curl -fsSL https://www.gnu.org/licenses/lgpl-3.0.txt -o /tmp/lgpl-3.0.txt; then
        cat /tmp/lgpl-3.0.txt > LICENSE
        ok "LICENSE 已写入完整文本"
    else
        ok "下载失败，保留原有 LICENSE 说明（可稍后在 GitHub 上用许可证模板补）"
    fi
fi

if [[ "$USE_SSH" == "1" ]]; then
    REMOTE="git@github.com:$OWNER/$REPO.git"
else
    REMOTE="https://github.com/$OWNER/$REPO.git"
fi

if [[ ! -d .git ]]; then
    log "初始化 git 仓库"
    git init -q
    git symbolic-ref HEAD "refs/heads/$BRANCH"
fi

if git remote | grep -qx origin; then
    git remote set-url origin "$REMOTE"
else
    git remote add origin "$REMOTE"
fi
ok "远端: $REMOTE"

# 别把编译产物和发布包传上去
find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

log "提交变更"
git add -A
if git diff --cached --quiet; then
    ok "没有需要提交的变更"
else
    if [[ -z "$MESSAGE" ]]; then
        VERSION=$(python3 - <<'PY' 2>/dev/null || echo ""
import ast
print(ast.literal_eval(open("stock_barcode_ce/__manifest__.py").read()).get("version", ""))
PY
)
        MESSAGE="Odoo 19 barcode suite ${VERSION}"
    fi
    git -c user.name="${GIT_AUTHOR_NAME:-$OWNER}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-$OWNER@users.noreply.github.com}" \
        commit -q -m "$MESSAGE"
    ok "已提交: $MESSAGE"
fi

log "推送到 $OWNER/$REPO ($BRANCH)"
echo "  如果提示输入密码，请粘贴 GitHub Personal Access Token（不是账号密码）"
git push -u origin "$BRANCH"
ok "完成: https://github.com/$OWNER/$REPO"

cat <<EOF

接下来可以在本机用 Claude Code 继续开发：
    git clone $REMOTE && cd $REPO && claude
仓库里的 CLAUDE.md 已写好项目结构、开发约定、测试环境搭建和后续路线。
EOF
