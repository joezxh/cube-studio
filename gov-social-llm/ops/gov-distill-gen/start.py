"""gov-distill-gen 算子入口（spec §2.1/§2.2）。

读取种子 JSONL，按任务加载 prompt 模板，批量调用教师服务生成蒸馏原始数据。
产出：out_dir/raw.jsonl + gen_report.json + manifest.json（血缘）。
教师 5xx 超过重试的种子记入 gen_report.failed[]，不中断整体。
"""
import argparse
import json
import os
import pathlib
import sys

# 兄弟目录依赖：gov-manifest 共享库
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gov-manifest", "lib"))
from gov_manifest import write_manifest  # noqa: E402

import gen  # noqa: E402


def _load_seeds(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-distill-gen")
    p.add_argument("--seeds", required=True, help="种子 JSONL 路径")
    p.add_argument("--task", required=True, help="任务标识 T1..T4")
    p.add_argument("--prompt-version", default="v1")
    p.add_argument("--docs-dir", default=None, help="prompt 模板目录，缺省用仓库 docs/prompts")
    p.add_argument("--endpoint", required=True, help="教师 OpenAI 兼容 /chat/completions 地址")
    p.add_argument("--model", default="teacher")
    p.add_argument("--n-candidates", type=int, default=3)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--out-dir", required=True, help="产出目录 /mnt/gov/distill/{task}/{ver}")
    p.add_argument("--seed-manifest", default=None, help="上游种子 manifest.json（血缘 parent）")
    a = p.parse_args(argv)

    docs_dir = a.docs_dir or str(pathlib.Path(__file__).resolve().parents[2] / "docs" / "prompts")
    prompt = gen.load_prompt(docs_dir, a.task, a.prompt_version)
    seeds = _load_seeds(a.seeds)
    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "raw.jsonl"

    # 逐种子生成，隔离失败（某种子重试耗尽仅记入 failed，不影响其余）
    succeeded = 0
    failed = []
    for s in seeds:
        try:
            gen.gen_batch([s], prompt, a.endpoint, a.model, a.n_candidates,
                          a.temperature, a.top_p, a.max_tokens, raw,
                          resume=not a.no_resume, concurrency=a.concurrency)
            succeeded += 1
        except Exception as e:  # noqa: BLE001
            failed.append({"seed_id": s.get("seed_id"), "error": str(e)})

    total_rows = sum(1 for _ in open(raw, encoding="utf-8")) if raw.exists() else 0
    report = {"task": a.task, "prompt_version": a.prompt_version,
              "seeds_total": len(seeds), "seeds_ok": succeeded,
              "seeds_failed": len(failed), "failed": failed, "total_rows": total_rows}
    (out_dir / "gen_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    parents = []
    if a.seed_manifest and pathlib.Path(a.seed_manifest).exists():
        pm = json.loads(pathlib.Path(a.seed_manifest).read_text(encoding="utf-8"))
        parents.append({"path": str(a.seed_manifest), "digest": pm.get("self_digest")})

    write_manifest(out_dir, op="gov-distill-gen",
                   args={k: v for k, v in vars(a).items() if v is not None},
                   parents=parents, files=["raw.jsonl", "gen_report.json"],
                   stats={"seeds_total": len(seeds), "seeds_failed": len(failed),
                          "total_rows": total_rows})
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
