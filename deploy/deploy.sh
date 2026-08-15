#!/usr/bin/env bash
# ResumeAgent 云服务器一键部署脚本
# 用法：把整个项目目录上传到服务器后，在项目根目录执行 ./deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 Docker，请先安装：https://docs.docker.com/engine/install/"
  exit 1
fi

if [ ! -f .env ]; then
  echo "缺少 .env（模型密钥配置）。请先执行：cp .env.example .env 并填入 LLM_API_KEY。"
  exit 1
fi

echo ">> 构建并启动容器（此后服务器重启也会自动拉起）…"
docker compose up -d --build

sleep 2
echo
echo "✅ 部署完成。"
if command -v curl >/dev/null 2>&1; then
  PUBLIC_IP=$(curl -s --max-time 8 https://ifconfig.me || echo "")
fi
if [ -n "${PUBLIC_IP:-}" ]; then
  echo "访问地址：http://${PUBLIC_IP}:8000"
else
  echo "访问地址：http://<你的服务器公网IP>:8000"
fi
echo
echo "提示："
echo "  1. 在云控制台「安全组」放行 8000 端口（如使用 Caddy 的 80/443 则放行 80/443）；"
echo "  2. 如需访问口令：在 .env 里加一行 ACCESS_CODE=你的口令，然后重新执行本脚本；"
echo "  3. 数据保存在 ./data 目录，备份只需打包该目录；"
echo "  4. 更新代码后重新执行本脚本即可，数据不丢失。"
