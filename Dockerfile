FROM python:3.11-slim
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY migrations/ migrations/
ENV PYTHONUNBUFFERED=1
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}
EXPOSE 8000 8001
# 健康检查按服务定义在 docker-compose（api=8000 / admin=8001，路径同 /api/health）
# ——Dockerfile 内单一 HEALTHCHECK 曾致 admin 常驻 unhealthy（端口硬编码教训）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
