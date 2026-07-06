#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# deploy.sh — 一键部署飞书增量流式卡片到 Hermes Agent
# ============================================================
# 用法: bash deploy.sh [--target-dir <路径>]
# 默认目标: ~/.hermes/hermes-agent
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- 检测目标目录 ---
TARGET_DIR="${1:-}"
if [ -z "$TARGET_DIR" ]; then
    # 自动检测
    for candidate in "$HOME/.hermes/hermes-agent" "$HOME/hermes-agent" "$PWD"; do
        if [ -f "$candidate/plugins/platforms/feishu/adapter.py" ]; then
            TARGET_DIR="$candidate"
            break
        fi
    done
fi

if [ -z "$TARGET_DIR" ] || [ ! -f "$TARGET_DIR/plugins/platforms/feishu/adapter.py" ]; then
    log_error "找不到 Hermes Agent 目录。请指定路径："
    echo "  bash deploy.sh /path/to/hermes-agent"
    exit 1
fi

log_info "目标: $TARGET_DIR"
cd "$TARGET_DIR"

# --- 1. 备份 ---
BACKUP_DIR="$HOME/.hermes/backups/feishu-adapter-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp plugins/platforms/feishu/adapter.py "$BACKUP_DIR/adapter.py"
log_ok "已备份原 adapter.py → $BACKUP_DIR/adapter.py"

# --- 2. 确定补丁来源 ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_FILE="$SCRIPT_DIR/feishu-streaming-card.patch"
if [ ! -f "$PATCH_FILE" ]; then
    log_warn "补丁文件不存在: $PATCH_FILE"
    log_info "尝试从 src/adapter.py 直接覆盖..."
    if [ -f "$SCRIPT_DIR/src/adapter.py" ]; then
        cp "$SCRIPT_DIR/src/adapter.py" plugins/platforms/feishu/adapter.py
        log_ok "已直接覆盖 adapter.py"
    else
        log_error "找不到 src/adapter.py 或补丁文件。"
        exit 1
    fi
else
    # --- 3. 检查 git 是否干净 ---
    if git rev-parse --git-dir > /dev/null 2>&1; then
        git stash push -m "feishu-streaming-card-backup-$(date +%s)" 2>/dev/null || true
        if git apply "$PATCH_FILE" 2>/dev/null; then
            log_ok "补丁应用成功（git apply）"
        else
            log_warn "git apply 失败，尝试直接覆盖..."
            cp "$SCRIPT_DIR/src/adapter.py" plugins/platforms/feishu/adapter.py
            log_ok "已直接覆盖 adapter.py"
        fi
    else
        cp "$SCRIPT_DIR/src/adapter.py" plugins/platforms/feishu/adapter.py
        log_ok "已直接覆盖 adapter.py（非 git 仓库）"
    fi
fi

# --- 4. Python 语法验证 ---
if python3 -c "import ast; ast.parse(open('plugins/platforms/feishu/adapter.py').read())" 2>/dev/null; then
    log_ok "Python 语法验证通过"
else
    log_error "adapter.py 语法错误！正在恢复备份..."
    cp "$BACKUP_DIR/adapter.py" plugins/platforms/feishu/adapter.py
    exit 1
fi

# --- 5. 重启提示 ---
log_info "补丁已部署。请重启 Gateway 加载新代码："
echo ""
echo -e "  ${GREEN}hermes gateway restart${NC}"
echo -e "  或"
echo -e "  ${GREEN}sudo systemctl restart hermes-gateway${NC}"
echo ""
log_warn "Gateway 无法从内部重启。请从另一个终端窗口执行以上命令。"

# --- 6. 清理旧备份（保留最近 5 个） ---
BACKUP_DIR="$HOME/.hermes/backups"
if [ -d "$BACKUP_DIR" ]; then
    count=$(ls -1 "$BACKUP_DIR" 2>/dev/null | wc -l)
    if [ "$count" -gt 5 ]; then
        ls -1t "$BACKUP_DIR" | tail -n +6 | while read -r old; do
            rm -rf "$BACKUP_DIR/$old"
        done
        log_info "已清理旧备份（保留最近 5 个）"
    fi
fi

log_ok "部署完成！"
