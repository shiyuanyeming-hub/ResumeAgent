# ResumeAgent 云服务器部署指南

目标：把 ResumeAgent 跑在你的云服务器上，得到一个私发链接、打开即用的公网简历导师。

## 一、准备（本地电脑）

1. 在项目根目录确认 `.env` 已配置模型密钥（服务器上也需要它，但**不要提交到 GitHub**）。
2. 把整个项目目录打包上传到服务器（.env 一起传，注意别传到公开仓库）：

```bash
# 本地执行（替换 服务器IP）
rsync -av --exclude '.venv' --exclude 'data' --exclude '__pycache__' \
  ./ root@服务器IP:/opt/resumeagent/
```

或直接在服务器上 `git clone https://github.com/shiyuanyeming-hub/ResumeAgent.git /opt/resumeagent`，
再把 `.env` 单独用 scp 传上去。

## 二、服务器上部署（以 Ubuntu 为例）

```bash
# 1. 安装 Docker（已装可跳过）
curl -fsSL https://get.docker.com | sh

# 2. 进入项目目录
cd /opt/resumeagent
cp .env.example .env      # 如果还没配置
vim .env                  # 填入 LLM_API_KEY 等；可选加 ACCESS_CODE=你的口令

# 3. 一键部署
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

部署完成后访问 `http://服务器公网IP:8000`。

## 三、云控制台必做

在阿里云/腾讯云等的**安全组**里放行端口：`8000`（HTTP 直连）或 `80/443`（配合 Caddy 用域名）。

## 四、访问口令（可选，推荐开启）

`.env` 里加一行：

```
ACCESS_CODE=你想要的口令
```

重新执行 `./deploy/deploy.sh`。之后任何人打开链接都需要输入口令，你私发链接时把口令一起告诉对方即可。不设置则完全打开即用。

## 五、域名 + HTTPS（可选）

1. 把域名 A 记录解析到服务器公网 IP；
2. 在 `docker-compose.yml` 里加一个 caddy 服务（见 `deploy/Caddyfile.example` 顶部注释），
   或在服务器上另装 Caddy/Nginx 反代到 `127.0.0.1:8000`。

## 六、日常维护

- 更新代码：`git pull`（或重新 rsync）→ `./deploy/deploy.sh`，数据不丢失；
- 备份数据：打包 `data/` 目录即可（含 SQLite 数据库、照片、模板）；
- 查看日志：`docker compose logs -f resumeagent`；
- 停止服务：`docker compose down`。

## 七、安全提示

- 当前没有账号体系：有链接（和口令）即可使用，请只发给信任的人；
- `.env` 含模型密钥，不要提交到公开仓库、不要在聊天里转发；
- 需要真正的多用户账号/权限体系时，再在此基础上加注册登录。
