"""core/notify——告警双通道（Server酱/ntfy），P0-2 收口自 cron/common.py。

任何失败只打 stderr 不抛（告警通道故障不得炸断 cron/降级链主流程）。
依赖方向：core 零依赖（仅标准库）——llm/cron/web 均可安全调用。
"""
import json
import os
import sys
import urllib.request

def notify(title: str, body: str = "", priority: str = "P1") -> bool:
    """X6 个人告警发送（U10）：Server酱 / ntfy 双通道，key 仅环境变量注入。

    任一通道成功即返回 True；双通道失败打 stderr（不抛——告警失败不掩盖主流程）。
    P1＝立即触达；P2＝随日结批处理顺带（调用方自定频率）。
    """
    import urllib.parse
    sent = False
    key = os.environ.get("SERVERCHAN_SENDKEY", "")
    if key:                                    # Server酱（微信）
        try:
            data = urllib.parse.urlencode(
                {"title": f"[{priority}] {title}", "desp": body}).encode()
            req = urllib.request.Request(
                f"https://sctapi.ftqq.com/{key}.send", data=data)
            urllib.request.urlopen(req, timeout=5).read()
            sent = True
        except Exception as e:
            print(f"[notify] serverchan fail: {e}", file=sys.stderr)
    topic = os.environ.get("NTFY_TOPIC", "")
    if topic:                                  # ntfy（Android 应用订阅）
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}",
                data=f"[{priority}] {title}\n{body}".encode(),
                headers={"Title": f"[{priority}] {title}",
                         "Priority": "high" if priority == "P1" else "default"})
            urllib.request.urlopen(req, timeout=5).read()
            sent = True
        except Exception as e:
            print(f"[notify] ntfy fail: {e}", file=sys.stderr)
    if not sent:
        print(f"[notify] no channel configured (SERVERCHAN_SENDKEY/NTFY_TOPIC)",
              file=sys.stderr)
    return sent
