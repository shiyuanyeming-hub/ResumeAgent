#!/usr/bin/env bash
# ResumeAgent 一键启动：绑定 0.0.0.0，局域网内其他人可通过 http://<本机IP>:8000 访问
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if [ ! -d ".venv" ]; then
  echo "未找到虚拟环境，正在创建并安装依赖…"
  python3 -m venv .venv
  .venv/bin/pip install -e '.[agents,web]'
fi

if [ ! -f ".env" ]; then
  echo "提示：未配置 .env，AI 功能将使用离线兜底。可复制 .env.example 并填入 API Key。"
fi

echo "ResumeAgent 启动中：http://${HOST}:${PORT}"
echo "本机访问：http://127.0.0.1:${PORT}"
IP=$(ipconfig getifaddr en0 2>/dev/null || true)
[ -n "$IP" ] && echo "局域网访问：http://${IP}:${PORT}"

exec .venv/bin/uvicorn resume_agent.api.main:app --host "$HOST" --port "$PORT"
