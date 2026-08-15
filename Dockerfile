# ResumeAgent 生产镜像：单进程 FastAPI + SQLite
FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用构建缓存
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir '.[agents]'

COPY resume_agent ./resume_agent

EXPOSE 8000

ENV RESUME_AGENT_DB=/app/data/resume_agent.db

CMD ["uvicorn", "resume_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
