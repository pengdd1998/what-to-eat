"""cron/aggregate——02:00 日表聚合（FR-19）：闸门指标口径单一事实源。"""
import json
import statistics
from datetime import datetime, timezone

from ..core import db
from .common import _today, _write_metric


def aggregate(date: str = None) -> dict:
    date = date or _today()
    conn = db.connect()
    q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731

    sessions = q("SELECT * FROM sessions WHERE substr(started_at,1,10)=?", date)
    sids = [s["id"] for s in sessions]
    if not sids:
        with db.tx() as t:
            _write_metric(t, date, "sessions", 0, 0)
        return {"date": date, "sessions": 0}

    marks = ",".join("?" * len(sids))
    ev = lambda typ: q(  # noqa: E731
        f"SELECT * FROM events WHERE session_id IN ({marks}) AND type=? "
        "ORDER BY id", *sids, typ)

    accepts = {e["session_id"]: e for e in ev("accept")}
    jumps = ev("jump")
    jump_of = {}
    for j in jumps:
        jump_of.setdefault(j["session_id"], []).append(j)
    abandons = {e["session_id"] for e in ev("abandon")}
    exhausted = {e["session_id"] for e in ev("swap_exhausted")}

    def ts(e):
        return e["server_ts"]

    north_star, surrender = [], []
    for sid, acc in accepts.items():
        paired = any(
            0 <= (datetime.fromisoformat(ts(j)) -
                  datetime.fromisoformat(ts(acc))).total_seconds() <= 60
            for j in jump_of.get(sid, []))
        if not paired:
            continue
        if sid in abandons or sid in exhausted:   # 投降路径：单列观测不计分子
            surrender.append(sid)
        else:
            north_star.append(sid)

    completed = [s for s in sessions if s["status"] == "accepted"]
    first_accept = [s for s in completed if s["id"] not in
                    {e["session_id"] for e in ev("swap")}]
    # 护栏 3：换一耗尽率（冷/稳态分桶）＝耗尽会话 ÷ 完成会话
    exh_cold = [s for s in sessions if s["id"] in exhausted and s["is_cold_start"]]
    exh_steady = [s for s in sessions if s["id"] in exhausted
                  and not s["is_cold_start"]]
    comp_cold = [s for s in sessions if s["status"] in ("accepted", "swapped_out")
                 and s["is_cold_start"]]
    comp_steady = [s for s in sessions if s["status"] in ("accepted", "swapped_out")
                   and not s["is_cold_start"]]

    durations, steps = [], []
    starts = {e["session_id"]: e for e in ev("session_start")}
    answers = q(f"SELECT session_id, COUNT(*) c FROM events WHERE session_id IN "
                f"({marks}) AND type='answer' GROUP BY session_id", *sids)
    steps_by_sid = {r["session_id"]: r["c"] for r in answers}
    for s in completed:
        if s["id"] in starts and s["id"] in accepts:
            d = (datetime.fromisoformat(ts(accepts[s["id"]])) -
                 datetime.fromisoformat(ts(starts[s["id"]]))).total_seconds()
            if 0 <= d < 3600:
                durations.append(d)
        steps.append(steps_by_sid.get(s["id"], 0))

    active_users = len({s["anon_id"] for s in sessions})
    n_sessions = len(sessions)
    # A 形态运营指标：推荐来源分布与池命中率（护栏/判读依赖，规划 §4）
    served = ev("result_served")
    src_count = {"pool": 0, "realtime": 0, "library": 0, "template": 0}
    for e in served:
        s_src = (json.loads(e["payload"]).get("source")
                 if e["payload"] else "unknown")
        src_count[s_src if s_src in src_count else "library"] += 1
    llm_hits = src_count["pool"] + src_count["realtime"]
    llm_total = llm_hits + src_count["library"] + src_count["template"]
    with db.tx() as t:
        _write_metric(t, date, "active_users", active_users, active_users)
        _write_metric(t, date, "sessions", n_sessions, n_sessions)
        _write_metric(t, date, "completed", len(completed), n_sessions)
        _write_metric(t, date, "abandoned",
                      sum(1 for s in sessions if s["status"] == "abandoned"),
                      n_sessions)
        _write_metric(t, date, "north_star_sessions", len(north_star), n_sessions)
        _write_metric(t, date, "north_star_per_user",
                      round(len(north_star) / active_users, 4) if active_users
                      else 0, active_users)
        _write_metric(t, date, "surrender_sessions", len(surrender), n_sessions)
        _write_metric(t, date, "rec_source_pool", src_count["pool"], len(served))
        _write_metric(t, date, "rec_source_realtime", src_count["realtime"],
                      len(served))
        _write_metric(t, date, "rec_source_library", src_count["library"],
                      len(served))
        _write_metric(t, date, "rec_llm_hit_rate",
                      round(llm_hits / llm_total, 4) if llm_total else None,
                      llm_total)
        # FR-16 回访指标（M2 判读地基：应答率/不满意占比）
        vs = q("SELECT payload FROM events WHERE session_id IN "
               f"({marks}) AND type='visit_report' ORDER BY id", *sids)
        v_ans = [json.loads(e["payload"]).get("answer") for e in vs]
        _write_metric(t, date, "visit_reports",
                      len(v_ans), active_users)
        _write_metric(t, date, "visit_unsatisfied_rate",
                      round(sum(1 for a in v_ans if a == "unsatisfied") / len(v_ans), 4)
                      if v_ans else None, len(v_ans))
        v_show = q("SELECT COUNT(*) c FROM events WHERE session_id IN "
                   f"({marks}) AND type='visit_probe_show'", *sids)
        _write_metric(t, date, "visit_probe_shows",
                      v_show[0]["c"] if v_show else 0, active_users)
        _write_metric(t, date, "first_accept_rate",
                      round(len(first_accept) / len(completed), 4) if completed
                      else None, len(completed))
        _write_metric(t, date, "swap_exhaustion_cold",
                      round(len(exh_cold) / len(comp_cold), 4) if comp_cold
                      else None, len(comp_cold))
        _write_metric(t, date, "swap_exhaustion_steady",
                      round(len(exh_steady) / len(comp_steady), 4) if comp_steady
                      else None, len(comp_steady))
        _write_metric(t, date, "decision_duration_median_sec",
                      round(statistics.median(durations), 1) if durations
                      else None, len(durations))
        _write_metric(t, date, "answer_steps_median",
                      statistics.median(steps) if steps else None, len(steps))
        # M1 狗粮验收口径（2026-09-15 拍板换）：答题完成率＝done 会话/全部 quiz 会话
        # （原「换一耗尽率」数据源随旧链删除恒零；≥70%＝原耗尽<30% 语义反面）
        _qc_total = q(f"SELECT COUNT(*) c FROM quiz_session WHERE state IN "
                      "('active','done') AND substr(updated_at,1,10)=?", date)
        _qc_done = q(f"SELECT COUNT(*) c FROM quiz_session WHERE state='done' "
                     "AND substr(updated_at,1,10)=?", date)
        _write_metric(t, date, "quiz_completion_rate",
                      round(_qc_done[0]["c"] / _qc_total[0]["c"], 4)
                      if _qc_total and _qc_total[0]["c"] else None,
                      _qc_total[0]["c"] if _qc_total else 0)
    return {"date": date, "sessions": n_sessions,
            "north_star": len(north_star), "surrender": len(surrender)}
