# what-to-eat

H5 薄 API 单体（FastAPI + SQLite + Jinja2 SSR 计划中）。当前阶段：W1（M0 预验证）。

- 冒烟：`./scripts/smoke_local.sh`（本地 venv + 临时库，全链路断言）
- 容器：`docker compose up -d --build api`（宿主端口 8881→容器 8000；公网边缘等 X5 载体重评）
- 文档：docs/product/product-plan.md（v4.1）/ docs/tech/implementation-plan.md（v3.1）；文档地图 docs/README.md；执行归档 docs/execution/
