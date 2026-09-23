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
    # W-4：兜底 500 统一契约（不漏栈给前端）；audit 留痕（P2-2：观测出口，
    # 单日 50 条上限防异常风暴；detail 只 exc 类型名＋path，脱敏从紧）
    import sys
    print(f"[WTE-ERROR] unhandled {request.url.path} {type(exc).__name__}: {exc}",
          file=sys.stderr)
    try:
        from .core.util import now_iso
        _today_s = now_iso()[:10]
        _n = db.connect().execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='app_error' "
            "AND substr(ts,1,10)=?", (_today_s,)).fetchone()["c"]
        if _n < 50:
            with db.tx() as _t:
                _t.execute(
                    "INSERT INTO audit_log(ts,actor,action,target,detail,"
                    "created_at) VALUES(?,?,?,?,?,?)",
                    (now_iso(), "system:api", "app_error", request.url.path,
                     type(exc).__name__, now_iso()))
    except Exception:
        pass                                     # 观测留痕不得影响错误契约
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
            # P5 修复（评审 R3）：同步 db.tx 移出事件循环（async 中间件内阻塞
            # 写锁＝洪峰下放大）；线程化执行，失败不阻断拒绝响应
            import asyncio as _aio
            def _count_429():
                from .core.util import now_iso as _ni
                _d = _ni()[:10]
                with db.tx() as _t:
                    _prev = _t.execute(
                        "SELECT value FROM daily_metrics WHERE metric_date=? "
                        "AND metric='app_429_count'", (_d,)).fetchone()
                    _v = (float(_prev["value"]) + 1) if _prev else 1
                    _t.execute(
                        "INSERT INTO daily_metrics(metric_date,metric,value,n) "
                        "VALUES(?, 'app_429_count', ?, 0) "
                        "ON CONFLICT(metric_date, metric) DO UPDATE SET "
                        "value=excluded.value",
                        (_d, int(_v)))
            try:
                await _aio.to_thread(_count_429)
            except Exception:
                pass
            return _err(429, "rate_limited", "请求太频繁，稍后再试")
    return await call_next(request)
