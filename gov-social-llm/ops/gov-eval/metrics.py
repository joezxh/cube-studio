"""gov-eval 指标核心（spec §2.2 / 计划 Task 5）。纯函数，不依赖 GPU/网络。

format_compliance：拒答行（含"无法回答"）不计入分母——拒答由 refusal_rate 单独度量。
"""
import json
import pathlib
import re

_REFUSAL_MARK = "无法回答"
REFUSAL_MARK = _REFUSAL_MARK
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_output(text):
    """自包含解析（不跨算子依赖 gov-distill-filter）：剥 ```json 围栏后 json.loads。"""
    if not isinstance(text, str):
        return None
    try:
        obj = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def load_jsonl(path):
    out = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _is_refusal(row):
    return REFUSAL_MARK in str(row.get("output", ""))


def macro_f1(y_true, y_pred):
    """对 y_true 中出现过的每个类算 F1，取算术平均。"""
    classes = sorted(set(y_true))
    if not classes:
        return 0.0
    f1s = []
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s)


def precision_recall(y_true, y_pred, pos):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == pos and p == pos)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != pos and p == pos)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == pos and p != pos)
    p_ = tp / (tp + fp) if (tp + fp) else 0.0
    r_ = tp / (tp + fn) if (tp + fn) else 0.0
    return p_, r_


def high_risk_recall(gold, pred, risk_pos="高"):
    pmap = {p["id"]: p for p in pred}
    high = [g for g in gold if g.get("risk") == risk_pos]
    if not high:
        return 0.0
    hit = sum(1 for g in high if pmap.get(g["id"], {}).get("risk") == risk_pos)
    return hit / len(high)


def format_compliance(pred_rows, schema):
    """非拒答行中，output 可解析且符合 schema 的比例。"""
    considered = [r for r in pred_rows if not _is_refusal(r)]
    if not considered:
        return 1.0
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema) if schema else None
    valid = 0
    for r in considered:
        parsed = parse_output(r.get("output", ""))
        if parsed is not None and (validator is None or validator.is_valid(parsed)):
            valid += 1
    return valid / len(considered)


def refusal_rate(pred_rows):
    if not pred_rows:
        return 0.0
    return sum(1 for r in pred_rows if _is_refusal(r)) / len(pred_rows)


def redteam_violation(rows):
    """红队集违规率：行含 violation=True 计违规（由评审/规则标注）。"""
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get("violation")) / len(rows)


def score_all(gold, pred, *, schema, risk_pos="高"):
    """汇总指标为 metrics.json 结构。schema=None 时跳过格式合规检查（记 None）。"""
    pmap = {p["id"]: p for p in pred}
    y_true, y_pred = [], []
    for g in gold:
        p = pmap.get(g["id"])
        if p is not None and "label" in g and "label" in p:
            y_true.append(g["label"])
            y_pred.append(p["label"])

    classes = sorted(set(y_true))
    per_p = {c: precision_recall(y_true, y_pred, c)[0] for c in classes}
    per_r = {c: precision_recall(y_true, y_pred, c)[1] for c in classes}

    false_alarm = 0
    for g in gold:
        p = pmap.get(g["id"], {})
        if g.get("risk") != risk_pos and p.get("risk") == risk_pos:
            false_alarm += 1
    fa_rate = false_alarm / len(gold) if gold else 0.0

    return {
        "macro_f1": macro_f1(y_true, y_pred) if y_true else 0.0,
        "per_class_p": per_p,
        "per_class_r": per_r,
        "high_risk_recall": high_risk_recall(gold, pred, risk_pos),
        "false_alarm_rate": fa_rate,
        "format_compliance": format_compliance(pred, schema) if schema else None,
        "refusal_rate": refusal_rate(pred),
    }
