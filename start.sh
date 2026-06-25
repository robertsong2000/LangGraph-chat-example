#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  LangGraph Multi-Agent Chat — one-command launcher
# ─────────────────────────────────────────────────────────────
#  用法:
#    ./start.sh            # 用默认 GLM-5.2 启动
#    ./start.sh --mock     # 强制使用 Mock 模式（不调用真实模型）
#
#  也可通过环境变量覆盖任何配置，例如:
#    MODEL_NAME=glm-4-flash ./start.sh
#    PORT=9000 ./start.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

# ---- 默认配置 ---------------------------------------------------
# API key: 从环境变量或 .env 读取，不在此硬编码（避免泄露）
export API_BASE="${API_BASE:-https://open.bigmodel.cn/api/coding/paas/v4}"
export MODEL_NAME="${MODEL_NAME:-glm-5.2}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export TEMPERATURE="${TEMPERATURE:-0.7}"

# 加载本地 .env（若存在），用于填入 OPENAI_API_KEY 等
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# --mock 标志：不设置 key，触发 MockLLM 降级
if [[ "${1:-}" == "--mock" ]]; then
  unset OPENAI_API_KEY
  MODE="MOCK"
elif [[ -z "${OPENAI_API_KEY:-}" ]]; then
  MODE="MOCK（未配置 OPENAI_API_KEY，请创建 .env）"
else
  MODE="$MODEL_NAME"
fi

# ---- 虚拟环境 ---------------------------------------------------
if [[ ! -d "venv" ]]; then
  echo "📦 首次运行，正在创建虚拟环境并安装依赖…"
  python3 -m venv venv
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt --quiet
  echo "✅ 依赖安装完成"
else
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

# ---- 启动 -------------------------------------------------------
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   LangGraph Multi-Agent Chat  🌟         ║"
echo "  ╠══════════════════════════════════════════╣"
printf "  ║  模式   : %-31s║\n" "$MODE"
printf "  ║  模型   : %-31s║\n" "$MODEL_NAME"
printf "  ║  端点   : %-31s║\n" "${API_BASE:-default}"
printf "  ║  地址   : %-31s║\n" "http://localhost:$PORT"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  按 Ctrl+C 停止服务"
echo ""

exec python run.py
