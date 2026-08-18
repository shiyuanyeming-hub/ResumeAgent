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

# 0. 基础工具（Ubuntu/Debian 镜像常缺 git）
if ! command -v git >/dev/null 2>&1; then
  echo ">> 安装 git …"
  sudo apt-get update && sudo apt-get install -y git
fi

# 1. Docker（优先阿里云镜像源，国内速度快；海外可换回 get.docker.com）
if ! command -v docker >/dev/null 2>&1; then
  echo ">> 安装 Docker（阿里云镜像源）…"
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
# Docker Hub 拉镜像加速（国内）
if ! grep -q "registry-mirrors" /etc/docker/daemon.json 2>/dev/null; then
  echo ">> 配置 Docker 镜像加速 …"
  sudo mkdir -p /etc/docker
  sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "registry-mirrors": ["https://docker.m.daocloud.io", "https://hub-mirror.c.163.com"]
}
EOF
  sudo systemctl restart docker || true
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "!! 未检测到 docker compose 插件，请先安装 docker-compose-plugin"
  exit 1
fi

# 2. 代码（GitHub 直连失败时走镜像加速）
if [ ! -d "$APP_DIR/.git" ]; then
  echo ">> 克隆代码到 $APP_DIR …"
  git clone "$REPO_URL" "$APP_DIR" \
    || git clone "https://mirror.ghproxy.com/$REPO_URL" "$APP_DIR" \
    || { echo "!! 代码下载失败，请检查网络或稍后重试"; exit 1; }
else
  echo ">> 更新代码（git pull）…"
  git -C "$APP_DIR" pull || git -C "$APP_DIR" pull || true
fi
cd "$APP_DIR"

# 3. .env（首次运行先生成并停下，等用户填写）
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "=================================================="
  echo "已生成 $APP_DIR/.env,请编辑它(用 nano,比 vim 简单):"
  echo "  nano $APP_DIR/.env"
  echo
  echo "  必填:LLM_API_KEY=<你的千问 Qwen Key>（.env.example 默认已是千问国际版端点）"
  echo "  建议:ACCESS_CODE=<给访问者的口令>(不设则打开即用,但任何人都会消耗你的 API 余额)"
  echo
  echo "  nano 操作:方向键移动光标 → 改内容 → Ctrl+O 回车保存 → Ctrl+X 退出"
  echo "填好保存后,重新执行本脚本即可完成部署。"
  echo "=================================================="
  exit 0
fi

# 4. 一键部署
chmod +x deploy/deploy.sh
./deploy/deploy.sh
