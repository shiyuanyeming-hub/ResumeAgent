#!/usr/bin/env bash
# ResumeAgent 服务器首次部署助手
# 用法（在服务器上）：
#   curl -fsSL https://raw.githubusercontent.com/shiyuanyeming-hub/ResumeAgent/main/deploy/server-setup.sh | bash
# 或者下载后执行：
#   bash deploy/server-setup.sh
# 说明：
#   - 自动安装 Docker（已装则跳过）
#   - 自动克隆/更新代码到 $HOME/resumeagent
#   - 首次运行会生成 .env 并提示你填写密钥；填好后再次运行本脚本即完成部署
set -euo pipefail

REPO_URL="https://github.com/shiyuanyeming-hub/ResumeAgent.git"
APP_DIR="${1:-$HOME/resumeagent}"

# 1. Docker（Ubuntu/Debian）
if ! command -v docker >/dev/null 2>&1; then
  echo ">> 未检测到 Docker，开始安装…"
  curl -fsSL https://get.docker.com | sh
  sudo systemctl enable --now docker || true
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "!! 未检测到 docker compose 插件，请先安装 docker-compose-plugin"
  exit 1
fi

# 2. 代码
if [ ! -d "$APP_DIR/.git" ]; then
  echo ">> 克隆代码到 $APP_DIR …"
  git clone "$REPO_URL" "$APP_DIR"
else
  echo ">> 更新代码（git pull）…"
  git -C "$APP_DIR" pull
fi
cd "$APP_DIR"

# 3. .env（首次运行先生成并停下，等用户填写）
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "=================================================="
  echo "已生成 $APP_DIR/.env，请先编辑它："
  echo "  vim $APP_DIR/.env"
  echo
  echo "  必填：LLM_API_KEY=<你的 DeepSeek Key>"
  echo "  建议：ACCESS_CODE=<给访问者的口令>（不设则打开即用，但任何人都会消耗你的 API 余额）"
  echo
  echo "填好保存后，重新执行本脚本即可完成部署。"
  echo "=================================================="
  exit 0
fi

# 4. 一键部署
chmod +x deploy/deploy.sh
./deploy/deploy.sh
