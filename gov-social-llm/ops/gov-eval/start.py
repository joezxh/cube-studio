"""gov-eval 算子入口（spec §2.2）。五模式：smoke/dev/blind/safety/bench。

- smoke：对 --eval-set 前 N 条逐条调 --endpoint，报告输出可解析率（教师/学生服务连通性）。
- dev/blind：gold 与模型输出（--pred）跑 score_all；--redteam 追加违规率；--judge 抽检事实一致性。
- safety：仅红队集违规率。
- bench：对 --endpoint 并发压测，报告 P50/P95 延迟。
blind 留痕：--eval-set 路径含 /blind/ 时，manifest.stats 记 blind_touched_at。
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import pathlib
import statistics
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gov-manifest", "lib"))
from gov_manifest import write_manifest  # noqa: E402

import metrics  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_schema(task):
    p = _REPO_ROOT / "docs/task-spec/schemas" / f"{task}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _call_endpoint(endpoint, model, state, *, max_tokens=1024):
    import requests
    resp = requests.post(endpoint, json={
        "model": model, "messages": [{"role": "user", "content": state}],
        "temperature": 0.0, "max_tokens": max_tokens}, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _mode_smoke(a):
    rows = metrics.load_jsonl(a.eval_set)[: a.limit]
    ok = 0
    for r in rows:
        try:
            out = _call_endpoint(a.endpoint, a.model, r.get("state", ""))
            if metrics.parse_output(out) is not None or out.strip():
                ok += 1
        except Exception:  # noqa: BLE001
            pass
    return {"mode": "smoke", "n": len(rows), "parseable": ok,
            "parseable_rate": ok / len(rows) if rows else 0.0}


def _mode_bench(a):
    rows = metrics.load_jsonl(a.eval_set)[: a.limit]
    lat = []

    def one(r):
        t = datetime.datetime.now()
        _call_endpoint(a.endpoint, a.model, r.get("state", ""))
        return (datetime.datetime.now() - t).total_seconds()

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for v in ex.map(one, rows):
            lat.append(v)
    if not lat:
        return {"mode": "bench", "n": 0, "p50_ms": 0, "p95_ms": 0}
    return {"mode": "bench", "n": len(lat), "concurrency": a.concurrency,
            "p50_ms": round(statistics.median(lat) * 1000, 1),
            "p95_ms": round(_p(lat, 0.95) * 1000, 1)}


def _p(vals, q):
    s = sorted(vals)
    idx = min(len(s) - 1, int(q * len(s)))
    return s[idx]


def _mode_scored(a, *, risk_pos):
    gold = metrics.load_jsonl(a.eval_set)
    pred = metrics.load_jsonl(a.pred) if a.pred else []
    schema = _load_schema(a.task) if a.task else None
    m = metrics.score_all(gold, pred, schema=schema, risk_pos=risk_pos)
    m["mode"] = a.mode
    if a.redteam:
        rt = metrics.load_jsonl(a.redteam)
        m["redteam_violation"] = metrics.redteam_violation(rt)
    return m


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-eval")
    p.add_argument("--mode", required=True, choices=["smoke", "dev", "blind", "safety", "bench"])
    p.add_argument("--eval-set", required=True, help="gold/smoke 数据集 JSONL")
    p.add_argument("--pred", default=None, help="模型输出 JSONL（dev/blind）")
    p.add_argument("--task", default=None)
    p.add_argument("--endpoint", default=None, help="服务 /chat/completions（smoke/bench）")
    p.add_argument("--model", default="student")
    p.add_argument("--risk-pos", default="高")
    p.add_argument("--redteam", default=None, help="红队集 JSONL")
    p.add_argument("--judge", action="store_true", help="事实一致性抽检（需 --endpoint）")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args(argv)

    if a.mode == "smoke":
        result = _mode_smoke(a)
    elif a.mode == "bench":
        result = _mode_bench(a)
    elif a.mode == "safety":
        rt = metrics.load_jsonl(a.redteam or a.eval_set)
        result = {"mode": "safety", "redteam_violation": metrics.redteam_violation(rt)}
    else:  # dev / blind
        result = _mode_scored(a, risk_pos=a.risk_pos)

    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# gov-eval {a.mode} 报告", ""]
    for k, v in result.items():
        lines.append(f"- **{k}**: {v}")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    stats = dict(result)
    if "/blind/" in str(a.eval_set).replace("\\", "/"):
        stats["blind_touched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    write_manifest(out_dir, op="gov-eval",
                   args={k: v for k, v in vars(a).items() if v is not None},
                   files=["metrics.json", "report.md"], stats=stats)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
