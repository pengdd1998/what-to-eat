"""web/pages——页面路由（只做渲染，业务全走 API——§1.1 强制分层）。"""
import os

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from ..core import db

_BASE = os.path.join(os.path.dirname(__file__), "..")   # → app/（templates/ 与 static/ 所在）
templates = Jinja2Templates(directory=os.path.join(_BASE, "templates"))
_VERSION = lambda: f"{db.APP_VERSION}+{db.GIT_SHA}"
router = APIRouter()


# ---------- 页面路由（只做渲染，业务全走 API——§1.1 强制分层） ----------

@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html",
                                      {"version": _VERSION()})


@router.get("/identity")
def identity_page(request: Request):
    return templates.TemplateResponse(request, "identity.html", {
        "version": _VERSION()})


@router.get("/memory")
def memory_page(request: Request):
    """味觉记忆页（真机事故 2026-09-15：移植时漏挂页面路由，footnav 404）。"""
    return templates.TemplateResponse(request, "memory.html", {
        "version": _VERSION()})

