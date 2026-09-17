"""公共面入口（阶段3重组后＝薄装配：创建 app/中间件/异常处理/lifespan/挂路由）。

业务与路由实现在 app/web/*；领域引擎在 app/domain/*；基础设施在 app/core/*；
环境上下文在 app/providers/*；定时任务在 app/cron/*。
对外引用冻结：`app.main:app`（docker-compose/smoke/crontab 引用不随重组漂移）。
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core import db, ratelimit, umami
from .domain import jump
from .web.support import CONFIG_DEFAULTS, _err, _guard_insecure_secret
from .web import go, identity_api, misc_api, pages, quiz_api


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """初始化 schema＋密钥守卫＋缺省补齐＋Umami 补发（游标重放）。"""
    db.init_schema()
    _guard_insecure_secret("GO_SECRET", jump.SECRET, "dev-only-insecure")
    for key, value in CONFIG_DEFAULTS.items():   # 仅缺省补齐，不覆盖 Admin 改动
        db.ensure_config(key, value)
    umami.forward_async()                        # 启动补发断流期间的事件
    yield


app = FastAPI(title="what-to-eat", version=db.APP_VERSION, lifespan=lifespan)

_BASE_DIR = os.path.join(os.path.dirname(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
          name="static")

app.include_router(pages.router)
app.include_router(misc_api.router)
app.include_router(go.router)
app.include_router(quiz_api.router)
app.include_router(identity_api.router)


# ---------- 异常处理（错误契约 {error:{code,message}}，§1.2） ----------
@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return _err(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return _err(422, "validation_error", str(exc.errors()[:3]))


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    # W-4：兜底 500 统一契约（不漏栈给前端）；audit 留痕
    import sys
    print(f"[WTE-ERROR] unhandled {request.url.path} {type(exc).__name__}: {exc}",
          file=sys.stderr)
    return JSONResponse(status_code=500,
                        content={"error": {"code": "internal",
                                           "message": "服务开小差了，稍后再试"}})


# ---------- 限流中间件（SUP-03；D-4 单机内存实现） ----------
@app.middleware("http")
async def rate_limit_mw(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        if not ratelimit.allow(f"ip:{ip}", 60, 60.0):       # 60 req/min/IP [假设]
            return _err(429, "rate_limited", "请求太频繁，稍后再试")
    return await call_next(request)
