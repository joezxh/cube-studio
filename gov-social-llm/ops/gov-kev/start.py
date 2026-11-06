"""gov-kev 算子入口（计划 Task 7）。

对 kev（system-one 决策微调范式）做薄封装：生成 `python -m kev.train` 命令，真实模式经
subprocess 执行，GOV_KEV_DRYRUN=1 时仅落 train_cmd.sh；完成后写 manifest 登记超参血缘。
serve 命令由平台服务算子单独调用 build_kev_serve_cmd（本入口 --mode serve 亦可打印）。
kev 上游 Apache-2.0；指针头不受 LLaMA-Factory 支持，故此臂不可用 gov-sft 替代（spec §3.4）。
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gov-manifest", "lib"))
from gov_manifest import write_manifest  # noqa: E402

import kev_cmd  # noqa: E402


def _run(cmd):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, check=True)


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-kev")
    p.add_argument("--mode", default="train", choices=["train", "serve"])
    p.add_argument("--data", help="kev_format.jsonl（Task 4 产出）")
    p.add_argument("--base", default="Qwen3.5-0.8B", help="kev 底座")
    p.add_argument("--init-from", default="jaredpalmer/kev-0.8b", help="初始化检查点")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--lr", default="2e-5")
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--accum", type=int, default=8)
    p.add_argument("--output", help="train 产出 run 目录 /mnt/gov/kev/{ver}")
    p.add_argument("--run", default=None, help="serve 模式加载的 run（缺省用 --output）")
    p.add_argument("--port", type=int, default=8009)
    p.add_argument("--data-manifest", default=None, help="上游 kev 数据集 manifest（血缘 parent）")
    a = p.parse_args(argv)

    dry = os.environ.get("GOV_KEV_DRYRUN") == "1"

    if a.mode == "serve":
        cmd = kev_cmd.build_kev_serve_cmd(a.run or a.output, port=a.port)
        print(json.dumps({"mode": "serve", "cmd": " ".join(cmd)}, ensure_ascii=False))
        if not dry:
            _run(cmd)
        return 0

    if not (a.data and a.output):
        p.error("train 模式需 --data 与 --output")

    out_dir = pathlib.Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = kev_cmd.build_kev_train_cmd(
        data=a.data, base=a.base, init_from=a.init_from, epochs=a.epochs,
        lr=a.lr, batch=a.batch, accum=a.accum, output=str(out_dir))
    (out_dir / "train_cmd.sh").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    if dry:
        report = {"dry_run": True, "train_cmd": " ".join(cmd)}
    else:
        _run(cmd)
        report = {"dry_run": False, "train_cmd": " ".join(cmd)}

    parents = []
    if a.data_manifest and pathlib.Path(a.data_manifest).exists():
        pm = json.loads(pathlib.Path(a.data_manifest).read_text(encoding="utf-8"))
        parents.append({"path": str(a.data_manifest), "digest": pm.get("self_digest")})

    hyper = {"base": a.base, "init_from": a.init_from, "epochs": a.epochs,
             "lr": a.lr, "batch": a.batch, "accum": a.accum}
    write_manifest(out_dir, op="gov-kev",
                   args={k: v for k, v in vars(a).items() if v is not None},
                   parents=parents, files=["train_cmd.sh"],
                   stats=report, extra={"hyper": hyper, "license": "Apache-2.0"})
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
