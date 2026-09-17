#!/usr/bin/env python3
"""真机端到端回归（发布检查单必过项；2026-09-15 固化）。

背景：done-bug（收口终裁被前端误判跳回起始页）只有真机前端路径能抓到——
服务器重放绕过前端，pytest 只覆盖 Python 侧。本脚本走真实前端链路。

用法（USB 连手机，隧道旁路或公网均可）：
  python3 scripts/e2e_mobile.py [--base http://127.0.0.1:18444]

前置：adb devices 可见设备；Chrome 已打开任一页面（CDP 通道自动接上）。
      隧道旁路的建立方式见私有运维注记（docs/ops-private/，不入公开仓）。

断言（任一失败 exit 1）：
  1. 全流程走通：bootstrap→问答（真实触摸）→收口（结果屏出现）
  2. 每问非搭配类问题（词表）
  3. 收口后 footnav 贴底（|navBottom - vh| ≤ 2px）
  4. console 零异常
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request

import websocket  # pip install websocket-client


def get_tab():
    tabs = json.load(urllib.request.urlopen("http://localhost:9222/json", timeout=5))
    pages = [t for t in tabs if t["type"] == "page"]
    if not pages:
        raise SystemExit("无页面 tab：先在手机 Chrome 打开任意页面")
    return pages[0]


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40,
                                              max_size=50 * 1024 * 1024,
                                              suppress_origin=True)
        self.mid = 0
        self.console = []

    def send(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method,
                                 "params": params or {}}))
        deadline = time.time() + 40
        while time.time() < deadline:
            m = json.loads(self.ws.recv())
            if m.get("method") == "Runtime.consoleAPICalled":
                self.console.append((m["params"].get("type"),
                                     " ".join(str(a.get("value", "")) for a
                                              in m["params"].get("args", []))))
            if m.get("method") == "Runtime.exceptionThrown":
                d = m["params"].get("exceptionDetails", {})
                self.console.append(("EXCEPTION",
                                     d.get("exception", {}).get("description", "")))
            if m.get("id") == self.mid:
                return m.get("result", {})

    def ev(self, expr):
        r = self.send("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True,
                       "awaitPromise": True})
        res = (r or {}).get("result", {})
        return res.get("value", res.get("description"))

    def touch(self, x, y):
        self.send("Input.dispatchTouchEvent",
                  {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1}]})
        time.sleep(0.15)
        self.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        time.sleep(1.5)


STATE_JS = """(function(){
  var vis = function(id){ var e = document.getElementById(id);
    return e && !e.classList.contains('hidden'); };
  return JSON.stringify({
    screen: vis('screen-quiz') ? 'quiz' : vis('screen-wait') ? 'wait'
          : vis('screen-result') ? 'result' : vis('screen-start') ? 'start' : 'NONE',
    q: (document.getElementById('quiz-q')||{}).textContent || '',
    result: (document.getElementById('dish-name')||{}).textContent || ''});
})()"""

# 搭配词表（与 domain/quiz.SIDE_DISH_WORDS 同源摘要；命中＝失败）
SIDE_WORDS = ("饮料", "奶茶", "啤酒", "配菜", "小菜", "配料", "加蛋", "卤蛋",
              "香菜", "蘸", "收尾", "灵魂伴侣", "加点什么")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18444")
    args = ap.parse_args()

    c = CDP(get_tab()["webSocketDebuggerUrl"])
    fails = []

    def state():
        for _ in range(3):
            r = c.ev(STATE_JS)
            if isinstance(r, str):
                return json.loads(r)
            time.sleep(1)
        return {"screen": "CDP_FAIL"}

    c.ev("localStorage.clear(); 1")
    c.send("Page.navigate", {"url": f"{args.base}/?_e2e={int(time.time())}"})
    time.sleep(6)

    def center(sel):
        r = c.ev(f"""(function(){{var b=document.querySelector('{sel}');
          if(!b)return '';var r=b.getBoundingClientRect();
          return JSON.stringify({{x:Math.round((r.left+r.right)/2),
            y:Math.round((r.top+r.bottom)/2)}})}})()""")
        return json.loads(r) if r else None

    b = center("#btn-privacy-ok")
    if b:
        c.touch(b["x"], b["y"])
    b = center("#btn-start")
    if not b:
        fails.append("无开始按钮（页面未加载？）")
        print("FAIL:", fails)
        return 1
    c.touch(b["x"], b["y"])

    prev_q, steps, reached = "", 0, False
    for i in range(9):
        deadline = time.time() + 35
        s = state()
        while time.time() < deadline:
            s = state()
            if s["screen"] == "quiz" and s["q"] and s["q"] != prev_q:
                break
            if s["screen"] in ("result", "start"):
                break
            time.sleep(1.3)
        if s["screen"] == "result":
            reached = True
            print(f"[OK] 收口: {s['result']}（{steps} 问）")
            break
        if s["screen"] != "quiz":
            break
        steps += 1
        if any(w in s["q"] for w in SIDE_WORDS):
            fails.append(f"搭配类问题: {s['q']}")
        print(f"  问{steps}: {s['q'][:40]}")
        prev_q = s["q"]
        raw = c.ev("""JSON.stringify((function(){var out=[];
          var cs=document.querySelectorAll('.flash-card');
          for(var i=0;i<cs.length;i++){var r=cs[i].getBoundingClientRect();
            out.push({x:Math.round((r.left+r.right)/2),y:Math.round((r.top+r.bottom)/2)});}
          return out})())""")
        cards = json.loads(raw or "[]")
        if not cards:
            fails.append(f"问{steps} 无卡牌")
            break
        c.touch(cards[0]["x"], cards[0]["y"])

    if not reached:
        fails.append("未到达结果屏")

    if reached:
        time.sleep(1.5)
        geo = c.ev("""(function(){var n=document.querySelector('.footnav');
          if(!n)return '';var r=n.getBoundingClientRect();
          return JSON.stringify({b:Math.round(r.bottom),vh:window.innerHeight})})()""")
        g = json.loads(geo) if geo else {}
        if not g or abs(g["b"] - g["vh"]) > 2:
            fails.append(f"footnav 偏移: {g}")

    errs = [x for x in c.console if x[0] in ("error", "EXCEPTION")]
    if errs:
        fails.append(f"console 异常: {errs[:2]}")

    if fails:
        print("== e2e 失败 ==")
        for f in fails:
            print(" FAIL:", f)
        return 1
    print("== e2e 真机回归全过 ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
