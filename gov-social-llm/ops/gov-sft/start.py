"""gov-sft 算子入口（spec §2.2 / 计划 Task 6）。

用 LLaMA-Factory 对学生底座做 LoRA/QLoRA 微调。本算子只负责：
  1) 生成 dataset_info.json（指向 /mnt/gov 下已过滤的 sharegpt/alpaca 数据）；
  2) 组装训练命令；
  3) 真实模式经 subprocess 执行；GOV_SFT_DRYRUN=1 时仅落 train_cmd.sh 供平台/人工核阅；
  4) 写 train_manifest.json 记录超参血缘（parents=数据集 manifest）。
不在镜像内打入权重；底座与数据集均在运行时由 volume 挂载提供。
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

import sft_cmd  # noqa: E402


def _run(cmd):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, check=True)


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-sft")
    p.add_argument("--base", required=True, help="学生底座权重路径（挂载点下）")
    p.add_argument("--dataset", required=True, help="训练数据 JSONL 绝对路径（sharegpt/alpaca）")
    p.add_argument("--dataset-name", default="gov", help="dataset_info.json 中的注册名")
    p.add_argument("--method", default="lora", choices=["lora", "qlora"])
    p.add_argument("--lora-rank", type=int, default=32)
    p.add_argument("--lr", default="1e-4")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--seq-len", type=int, default=4096)
    p.add_argument("--deepspeed", default=None)
    p.add_argument("--output", required=True, help="adapter 输出目录 /mnt/gov/sft/{ver}")
    p.add_argument("--merge", action="store_true", help="训练后合并导出全量权重")
    p.add_argument("--dataset-manifest", default=None, help="上游数据集 manifest.json（血缘 parent）")
    a = p.parse_args(argv)

    out_dir = pathlib.Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    dry = os.environ.get("GOV_SFT_DRYRUN") == "1"

    info = sft_cmd.build_dataset_info(a.dataset, a.dataset_name)
    (out_dir / "dataset_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    train = sft_cmd.build_train_cmd(
        method=a.method, base=a.base, dataset_name=a.dataset_name,
        lora_r=a.lora_rank, lr=a.lr, epochs=a.epochs, seq_len=a.seq_len,
        output=str(out_dir), deepspeed=a.deepspeed)
    merged = None
    if a.merge:
        merged = sft_cmd.merge_cmd(a.base, str(out_dir), str(out_dir) + "-merged")

    (out_dir / "train_cmd.sh").write_text(
        "\n".join([" ".join(train)] + ([" ".join(merged)] if merged else [])) + "\n",
        encoding="utf-8")

    if dry:
        report = {"dry_run": True, "train_cmd": " ".join(train),
                  "merge_cmd": " ".join(merged) if merged else None}
    else:
        # LLaMA-Factory 读取 dataset_info.json 需位于其 data 目录或 --dataset_dir；
        # 平台镜像内通过环境变量指向本 out_dir。
        os.environ.setdefault("LLAMAFACTORY_DATA", str(out_dir))
        _run(train)
        if merged:
            _run(merged)
        report = {"dry_run": False, "train_cmd": " ".join(train),
                  "merge_cmd": " ".join(merged) if merged else None}

    parents = []
    if a.dataset_manifest and pathlib.Path(a.dataset_manifest).exists():
        pm = json.loads(pathlib.Path(a.dataset_manifest).read_text(encoding="utf-8"))
        parents.append({"path": str(a.dataset_manifest), "digest": pm.get("self_digest")})

    hyper = {"method": a.method, "lora_rank": a.lora_rank, "lr": a.lr,
             "epochs": a.epochs, "seq_len": a.seq_len, "base": a.base,
             "template": "default"}
    write_manifest(out_dir, op="gov-sft",
                   args={k: v for k, v in vars(a).items() if v is not None},
                   parents=parents, files=["dataset_info.json", "train_cmd.sh"],
                   stats=report, extra={"hyper": hyper})
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
