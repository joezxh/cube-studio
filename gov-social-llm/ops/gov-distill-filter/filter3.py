"""gov-distill-filter 三闸过滤核心（spec §2.2 / 计划 Task 4）。

三闸：
  1) gate_format       —— 教师输出可解析为 JSON 且符合任务 schema；
  2) gate_consistency  —— 同 seed 多候选按投票众数 ≥k 保留（self-consistency）；
  3) gate_rules        —— 长度/重复片段/控制字符规则闸。
导出：to_alpaca / to_sharegpt / to_kev 三种训练格式。
"""
import json
import pathlib
import re

from jsonschema import Draft202012Validator

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_output(text):
    """剥离 ```json 围栏后 json.loads；失败返回 None。"""
    if not isinstance(text, str):
        return None
    cleaned = _FENCE.sub("", text.strip())
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def gate_format(rows, schema):
    """闸1：输出可解析且符合 schema。返回 (通过行, 丢弃行)。"""
    validator = Draft202012Validator(schema) if schema else None
    ok, dropped = [], []
    for r in rows:
        parsed = parse_output(r.get("output", ""))
        if parsed is None or (validator is not None and not validator.is_valid(parsed)):
            dropped.append(r)
        else:
            ok.append(r)
    return ok, dropped


def _vote_key(row):
    parsed = parse_output(row.get("output", "")) or {}
    if "label" in parsed:
        return parsed["label"]
    # T3/T4 等无 label：按解析结果全字段规范化值投票
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False)


def gate_consistency(rows, k=2):
    """闸2：同 seed 候选按投票众数计票，众数票数 ≥k 才保留该 seed（仅保留众数候选）。"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("seed_id"), []).append(r)
    ok, dropped = [], []
    for _sid, group in groups.items():
        tally = {}
        for r in group:
            key = _vote_key(r)
            tally.setdefault(key, []).append(r)
        top_key, top_rows = max(tally.items(), key=lambda kv: len(kv[1]))
        if len(top_rows) >= k:
            ok.extend(top_rows)
            dropped.extend([r for r in group if r not in top_rows])
        else:
            dropped.extend(group)   # 无稳定共识，整种子丢弃
    return ok, dropped


def gate_rules(row, max_len=4096):
    """闸3：长度上限、重复片段占比 >30%、控制字符。返回 bool（True=通过）。"""
    out = row.get("output", "")
    if not isinstance(out, str) or len(out) > max_len:
        return False
    if any(ord(c) < 32 and c not in "\n\t\r" for c in out):
        return False
    # 重复片段：以 8 字滑窗检测重复占比
    n = len(out)
    if n >= 32:
        grams = [out[i:i + 8] for i in range(n - 7)]
        unique = len(set(grams))
        if unique / len(grams) < 0.7:   # 重复片段占比 >30%
            return False
    return True


def to_alpaca(row):
    msgs = row.get("messages", [])
    instruction = msgs[0]["content"] if msgs else ""
    return {"instruction": instruction, "input": row.get("state", ""),
            "output": row.get("output", "")}


def to_sharegpt(row):
    msgs = row.get("messages", [])
    human = msgs[-1]["content"] if msgs else row.get("state", "")
    return {"conversations": [{"from": "human", "value": human},
                              {"from": "gpt", "value": row.get("output", "")}]}


def to_kev(row, kev_q, mapping=None):
    parsed = parse_output(row.get("output", "")) or {}
    label = parsed.get("label", "")
    department = (mapping or {}).get(label, "其他")
    return {"state": row.get("state", ""),
            "questions": kev_q["questions"],
            "answers": {"department": department, "escalate": False, "frustration": "平静"}}


def dump(rows, alpaca_path, sharegpt_path, kev_path, kev_q, mapping=None):
    """把通过全部闸的行写成三种训练格式 JSONL。"""
    def _write(path, items):
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    _write(alpaca_path, [to_alpaca(r) for r in rows])
    _write(sharegpt_path, [to_sharegpt(r) for r in rows])
    _write(kev_path, [to_kev(r, kev_q, mapping) for r in rows])
