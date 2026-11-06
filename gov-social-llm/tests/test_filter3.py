"""gov-distill-filter 三闸过滤测试（spec §2.2 / 计划 Task 4）。"""
import json
import pathlib

import filter3

SCHEMA = {"type": "object", "required": ["label"], "properties": {"label": {"type": "string"}}}
KEV_Q = json.loads((pathlib.Path(__file__).parents[1] / "docs/task-spec/schemas/kev-questions.json").read_text(encoding="utf-8"))


def _row(sid, cid, out, state="s"):
    return {"seed_id": sid, "candidate_id": cid, "task": "T1", "state": state,
            "output": out, "messages": [{"role": "user", "content": state}]}


def test_gates():
    rows = [_row("a", 0, '{"label":"x"}'), _row("a", 1, '{"label":"x"}'), _row("a", 2, '坏格式'),
            _row("b", 0, '{"label":"y"}'), _row("b", 1, '{"label":"z"}'), _row("b", 2, '{"label":"z"}')]
    ok1, d1 = filter3.gate_format(rows, SCHEMA)
    assert len(ok1) == 5 and len(d1) == 1
    ok2, d2 = filter3.gate_consistency(ok1, k=2)
    assert {r["seed_id"] for r in ok2} == {"a", "b"}
    assert filter3.gate_rules(_row("c", 0, '{"label":"x"}')) is True
    assert filter3.gate_rules(_row("c", 0, '{"label":"' + "啊" * 5000 + '"}')) is False


def test_outputs_three_formats(tmp_path):
    rows = [_row("a", 0, '{"label":"x"}')]
    alp = tmp_path / "train_alpaca.jsonl"
    sg = tmp_path / "train_sharegpt.jsonl"
    kv = tmp_path / "kev_format.jsonl"
    filter3.dump(rows, alp, sg, kv, KEV_Q)
    a = json.loads(alp.read_text(encoding="utf-8").splitlines()[0])
    assert {"instruction", "input", "output"} <= set(a)
    k = json.loads(kv.read_text(encoding="utf-8").splitlines()[0])
    assert k["state"] == "s" and set(k["questions"]) == {"department", "escalate", "frustration"}
