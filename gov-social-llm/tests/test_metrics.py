"""gov-eval 指标核心测试（spec §2.2 / 计划 Task 5）。

注：计划原文对 `macro_f1(["A","A","B"],["A","A","A"])` 断言 0.5，属算术勘误——
标准 macro-F1 中 A 类 F1=2*(P=2/3,R=1)/(2/3+1)=0.8、B 类 F1=0，宏平均=0.4。此处按正确值断言。
"""
from metrics import (format_compliance, high_risk_recall, macro_f1, refusal_rate,
                     score_all)


def test_macro_f1_perfect_and_skewed():
    assert macro_f1(["A", "B", "A"], ["A", "B", "A"]) == 1.0
    # A 类 F1=0.8，B 类 F1=0 → macro=(0.8+0)/2=0.4
    assert abs(macro_f1(["A", "A", "B"], ["A", "A", "A"]) - 0.4) < 1e-9


def test_high_risk_recall_and_false_alarm():
    gold = [{"id": 1, "risk": "高"}, {"id": 2, "risk": "高"}, {"id": 3, "risk": "低"}]
    pred = [{"id": 1, "risk": "高"}, {"id": 2, "risk": "中"}, {"id": 3, "risk": "高"}]
    assert abs(high_risk_recall(gold, pred) - 0.5) < 1e-9
    m = score_all(gold, pred, schema=None, risk_pos="高")
    assert abs(m["false_alarm_rate"] - 1 / 3) < 1e-9


def test_format_and_refusal():
    rows = [{"output": '{"label":"x"}'}, {"output": "坏"}, {"output": "无法回答该问题"}]
    assert format_compliance(rows, {"type": "object", "required": ["label"]}) == 0.5
    assert refusal_rate(rows) == 1 / 3
