"""lerobot-train 入口（spec §4；DRYRUN 只产 train_cmd.sh）。"""
import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lerobot_shared"))

import train_cmd  # noqa: E402
from manifest_util import write_manifest, sha256_file  # noqa: E402
from metrics_parser import parse_train_metrics  # noqa: E402


def _bool(s):
    return str(s).lower() in ("true", "1", "yes")


def main(argv=None):
    p = argparse.ArgumentParser(prog="lerobot-train-op")
    p.add_argument("--policy_type", default="")
    p.add_argument("--policy_path", default="")
    p.add_argument("--dataset_ref", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--batch_size", type=int, default=8)
    p.add_argument("--steps", type=int, default=10000)
    p.add_argument("--save_freq", type=int, default=5000)
    p.add_argument("--log_freq", type=int, default=200)
    p.add_argument("--lr", default="")
    p.add_argument("--resume", nargs="?", const="true", default="false")
    p.add_argument("--wandb_enable", nargs="?", const="true", default="false")
    p.add_argument("--extra_args", default="")
    p.add_argument("--base_dir", default=train_cmd.BASE_DIR)
    a = p.parse_args(argv)
    dry = os.environ.get("ROBOT_DRYRUN") == "1"
    out = pathlib.Path(a.output)
    out.mkdir(parents=True, exist_ok=True)

    try:
        cmd = train_cmd.build_train_cmd(
            policy_type=a.policy_type or None, policy_path=a.policy_path or None,
            dataset_ref=a.dataset_ref, output_dir=str(out),
            batch_size=a.batch_size, steps=a.steps, save_freq=a.save_freq,
            log_freq=a.log_freq, lr=a.lr or None, resume=_bool(a.resume),
            wandb_enable=_bool(a.wandb_enable), extra_args=a.extra_args,
            base_dir=a.base_dir)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    cmd_line = shlex.join(cmd)
    (out / "train_cmd.sh").write_text("#!/bin/sh\n" + cmd_line + "\n", encoding="utf-8")
    name, version = train_cmd.parse_dataset_ref(a.dataset_ref)
    dataset_meta = pathlib.Path(a.base_dir) / name / version / ".cube_dataset_meta"
    parents = [{"path": str(dataset_meta), "digest": sha256_file(dataset_meta)}]

    if dry:
        stats = {"dry_run": True, "train_cmd": cmd_line}
        files = ["train_cmd.sh"]
    else:
        with open(out / "train.log", "w", encoding="utf-8") as log:
            try:
                proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
                rc = proc.returncode
            except OSError as e:  # 镜像内无 lerobot-train 等拉起失败：显式记录并留血缘
                log.write("launch failed: %s\n" % e)
                rc = 127
        text = (out / "train.log").read_text(encoding="utf-8")
        metrics = parse_train_metrics(text)
        metrics.update({"policy_type": a.policy_type, "dataset_ref": a.dataset_ref})
        (out / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        stats = {"dry_run": False, "train_cmd": cmd_line, "exit_code": rc}
        files = ["train_cmd.sh", "metrics.json", "train.log"]

    write_manifest(out, op="lerobot-train",
                   args={k: v for k, v in vars(a).items() if v != ""},
                   parents=parents, files=files, stats=stats)
    print(json.dumps(stats, ensure_ascii=False))
    return 0 if dry or stats["exit_code"] == 0 else stats["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
