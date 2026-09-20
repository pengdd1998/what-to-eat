#!/usr/bin/env python3
"""CI 树卫生门禁（ci-cd-plan §2.4）：扫公开树 B 级模式，白名单豁免。

误红优于漏放——新豁免＝在下方 WHITELIST 加一行（文件级）。
"""
import re
import subprocess
import sys

PATTERNS = [
    (re.compile(r"\b175\.178\.\d+\.\d+\b"), "生产 VPS IP"),
    (re.compile(r"\btencent-cloud\b"), "ssh 别名"),
    (re.compile(r"/srv/what-to-eat"), "部署路径"),
    (re.compile(r"/srv/app\b"), "容器内路径"),
]
WHITELIST = {
    "docs/tech/ci-cd-plan.md",          # 方案文档自述脱敏策略（含模式举例）
    "scripts/ci_tree_hygiene.py",       # 本文件
    "AGENTS.md",                        # 已脱敏（中性措辞提及）
    "Dockerfile",                       # WORKDIR /srv/app＝镜像内路径（架构信息）
    "scripts/cron.md",                  # cron 说明的容器内路径示例（非宿主拓扑）
}

# 扫公开仓跟踪集（git ls-files）——工作区另有不入公开树的敏感子树
# （docs/execution 等，被 gitignore 挡住），文件系统 rglob 会误扫它们。
# --staged：扫暂存集（git diff --cached，含新 add 的未跟踪文件）——pre-commit 本地拦截层用
if "--staged" in sys.argv:
    tracked = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True).stdout.splitlines()
else:
    tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True, check=True).stdout.splitlines()
hits = []
for rel in tracked:
    if rel in WHITELIST:
        continue
    try:
        text = open(rel, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for pat, label in PATTERNS:
        for m in pat.finditer(text):
            hits.append(f"{rel}: [{label}] {m.group(0)!r}")

if hits:
    print("树卫生门禁 FAIL（误红请加白名单——误红优于漏放）：")
    for h in hits[:20]:
        print(" ", h)
    sys.exit(1)
print("树卫生 PASS：公开树零 B 级模式")
