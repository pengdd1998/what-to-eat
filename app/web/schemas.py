"""web/schemas——公共面 Pydantic 请求模型（阶段3自 main.py 迁出）。"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------- 请求模型 ----------

class VisitReportIn(BaseModel):
    anon_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    answer: str = Field(pattern="^(satisfied|neutral|unsatisfied)$")
    ordered: Optional[bool] = None             # M3 起自报下单（评审 #11）
    nps: Optional[int] = Field(default=None, ge=0, le=10)
    dish_slug: Optional[str] = Field(default=None, max_length=64)


class EventIn(BaseModel):
    client_event_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    type: str
    step: Optional[int] = Field(default=None, ge=1, le=9)
    payload: Optional[dict] = None
    client_ts: Optional[str] = Field(default=None, max_length=40)

    @field_validator("type")
    @classmethod
    def type_allowed(cls, v):
        if v not in CLIENT_ALLOWED:            # 服务端专属类型禁前端上报（防口径污染）
            raise ValueError(f"event type not client-allowed: {v}")
        return v


class EventsBatchIn(BaseModel):
    events: List[EventIn] = Field(min_length=1, max_length=50)  # §4.1 ≤50 条/批


class PasscodeIn(BaseModel):
    action: str = Field(pattern="^(set|recover)$")
    anon_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    passcode: str = Field(min_length=6, max_length=64)


class FakeDoorRegisterIn(BaseModel):
    anon_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    anchor_x: Optional[int] = Field(default=None, ge=0, le=10000)  # 展示时所见锚点（对账用）
