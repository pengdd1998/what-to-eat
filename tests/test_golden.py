"""golden set 回归（图谱§11.7）：每条用例过 validate_question（链维度的 tags
须与维度相交/正交须命中取值域/选项数 2~4）——维度树改动的活体防线。"""
import json
import os

import pytest

from app.domain import dimensions as D

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "docs", "eval", "golden-v1.jsonl")


def _cases():
    with open(GOLDEN, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _state_for(dim):
    """构造使 dim ∈ 可用集的最小状态：直接锁其父链（若在树中）或空状态。"""
    node = D.find_node(dim)
    if node is None:                      # 正交维度 → 空状态即可用
        return {"chain": [], "ortho": {}}
    # 找从根到该节点的祖先链
    path = []

    def walk(n, trail):
        if n["id"] == dim:
            path.extend(trail)
            return True
        for ch in n.get("children", []):
            if walk(ch, trail + [n["id"]]):
                return True
        for ch in n.get("optional_children", []):
            if walk(ch, trail + [n["id"]]):
                return True
        return False

    walk(D.CHAIN, [])
    return {"chain": path, "ortho": {}}


@pytest.mark.parametrize("case", list(_cases()), ids=lambda c: c["dimension"])
def test_golden_validate(case):
    st = _state_for(case["dimension"])
    if not st["chain"] and D.find_node(case["dimension"]):
        pytest.skip("链节点不在根可达路径（树结构调整后需更新用例）")
    ok, why = D.validate_question(case, st)
    assert ok, (case["dimension"], why)
    # 选项 tags 与维度 tags 相交（防跨类漂移的机读防线）
    node = D.find_node(case["dimension"])
    if node and node.get("tags") and node["id"] != "form":
        for o in case["options"]:
            assert set(o["tags"]) & set(node["tags"]), (o["text"], o["tags"], node["id"])
