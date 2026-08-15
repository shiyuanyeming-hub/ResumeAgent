# ResumeAgent 生产镜像：单进程 FastAPI + SQLite
FROM python:3.12-slim

WORKDIR /app

# 先拷贝源码再安装（pip install . 需要包文件在场）
COPY pyproject.toml README.md ./
COPY resume_agent ./resume_agent
RUN pip install --no-cache-dir '.[agents]'

EXPOSE 8000

ENV RESUME_AGENT_DB=/app/data/resume_agent.db

CMD ["uvicorn", "resume_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
