"""gov-distill-filter 算子入口（spec §2.2）。

读取 gov-distill-gen 的 raw.jsonl，依次过三闸（格式/一致性/规则），
导出 alpaca/sharegpt/kev 三格式训练集，产出 filter_report.json + manifest.json。
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gov-manifest", "lib"))
from gov_manifest import write_manifest  # noqa: E402

import filter3  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_jsonl(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-distill-filter")
    p.add_argument("--raw", required=True, help="gov-distill-gen 产出 raw.jsonl")
    p.add_argument("--task", required=True, help="任务标识，用于加载 schema 与 kev_q")
    p.add_argument("--schema", default=None, help="任务 schema 路径，缺省 docs/task-spec/schemas/{task}.json")
    p.add_argument("--k", type=int, default=2, help="一致性投票最小票数")
    p.add_argument("--kev-questions", default=str(_REPO_ROOT / "docs/task-spec/schemas/kev-questions.json"))
    p.add_argument("--kev-mapping", default=str(_REPO_ROOT / "docs/task-spec/kev-mapping.json"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--raw-manifest", default=None, help="上游 raw manifest（血缘 parent）")
    a = p.parse_args(argv)

    schema_path = a.schema or str(_REPO_ROOT / "docs/task-spec/schemas" / f"{a.task}.json")
    schema = json.loads(pathlib.Path(schema_path).read_text(encoding="utf-8"))
    kev_q = json.loads(pathlib.Path(a.kev_questions).read_text(encoding="utf-8"))
    mapping = json.loads(pathlib.Path(a.kev_mapping).read_text(encoding="utf-8")) if pathlib.Path(a.kev_mapping).exists() else {}
    mapping = {k: v for k, v in mapping.items() if not k.startswith("_")}

    rows = _load_jsonl(a.raw)
    ok1, drop1 = filter3.gate_format(rows, schema)
    ok2, drop2 = filter3.gate_consistency(ok1, k=a.k)
    ok3 = [r for r in ok2 if filter3.gate_rules(r)]
    drop3 = [r for r in ok2 if not filter3.gate_rules(r)]

    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    alp = out_dir / "train_alpaca.jsonl"
    sg = out_dir / "train_sharegpt.jsonl"
    kv = out_dir / "kev_format.jsonl"
    filter3.dump(ok3, alp, sg, kv, kev_q, mapping)

    label_dist = {}
    for r in ok3:
        parsed = filter3.parse_output(r.get("output", "")) or {}
        lbl = parsed.get("label")
        if lbl:
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

    report = {"task": a.task, "input_rows": len(rows),
              "gate1_pass": len(ok1), "gate2_pass": len(ok2), "gate3_pass": len(ok3),
              "dropped": {"gate1": len(drop1), "gate2": len(drop2), "gate3": len(drop3)},
              "label_dist": label_dist,
              "pass_rate": round(len(ok3) / len(rows), 4) if rows else 0.0}
    (out_dir / "filter_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    parents = []
    if a.raw_manifest and pathlib.Path(a.raw_manifest).exists():
        pm = json.loads(pathlib.Path(a.raw_manifest).read_text(encoding="utf-8"))
        parents.append({"path": str(a.raw_manifest), "digest": pm.get("self_digest")})

    write_manifest(out_dir, op="gov-distill-filter",
                   args={k: v for k, v in vars(a).items() if v is not None},
                   parents=parents,
                   files=["train_alpaca.jsonl", "train_sharegpt.jsonl", "kev_format.jsonl", "filter_report.json"],
                   stats={"gate_pass": [len(ok1), len(ok2), len(ok3)], "label_dist": label_dist})
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
