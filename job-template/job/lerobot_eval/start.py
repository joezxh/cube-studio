"""lerobot-eval 入口（spec §5；维度校验在任何 subprocess 之前，DRYRUN 不豁免）。"""
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

import eval_cmd as ec  # noqa: E402
import metrics_contract as mc  # noqa: E402
from manifest_util import write_manifest  # noqa: E402


def _find_train_manifest(checkpoint):
    p = pathlib.Path(checkpoint).resolve()
    for _ in range(4):
        p = p.parent
        f = p / "manifest.json"
        if f.is_file():
            try:
                m = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if m.get("op") == "lerobot-train":
                return f, m
    return None, None


def main(argv=None):
    p = argparse.ArgumentParser(prog="lerobot-eval-op")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--env_type", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--n_episodes", type=int, default=50)
    p.add_argument("--batch_size", type=int, default=10)
    p.add_argument("--seed", type=int, default=100000)
    p.add_argument("--video_n_episodes", type=int, default=3)
    a = p.parse_args(argv)
    dry = os.environ.get("ROBOT_DRYRUN") == "1"

    cfg_file = pathlib.Path(a.checkpoint) / "config.json"
    if cfg_file.is_file():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
        ok, reason = ec.check_action_dims(cfg, a.env_type)
        if not ok:
            print("action dim mismatch: %s" % reason, file=sys.stderr)
            return 2

    out = pathlib.Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    cmd = ec.build_eval_cmd(checkpoint=a.checkpoint, env_type=a.env_type,
                            n_episodes=a.n_episodes, batch_size=a.batch_size,
                            seed=a.seed, video_n_episodes=a.video_n_episodes,
                            output_dir=str(out / "eval"))
    cmd_line = shlex.join(cmd)
    (out / "eval_cmd.sh").write_text("#!/bin/sh\n" + cmd_line + "\n",
                                     encoding="utf-8")

    mf_path, mf = _find_train_manifest(a.checkpoint)
    parents = [{"path": str(mf_path), "digest": (mf or {}).get("self_digest")}] \
        if mf else []
    train_digest = (mf or {}).get("self_digest")

    if dry:
        stats = {"dry_run": True, "eval_cmd": cmd_line}
        files = ["eval_cmd.sh"]
    else:
        probe = subprocess.run([sys.executable, "-c", "import mujoco"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            print("MuJoCo/EGL probe failed, check gpu image / MUJOCO_GL=egl: %s"
                  % probe.stderr, file=sys.stderr)
            return 3
        eval_dir = out / "eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(eval_dir / "eval.log", "w", encoding="utf-8") as log:
                proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                      text=True)
            rc = proc.returncode
        except OSError as e:
            with open(eval_dir / "eval.log", "a", encoding="utf-8") as log:
                log.write("launch failed: %s\n" % e)
            rc = 127
        text = (eval_dir / "eval.log").read_text(encoding="utf-8")
        summary = mc.parse_eval_summary(text)
        vdir = eval_dir / "videos"
        videos = sorted(str(f.relative_to(out)) for f in vdir.glob("*.mp4")) \
            if vdir.is_dir() else []
        contract = mc.build_eval_metrics(summary, env=a.env_type,
                                         n_episodes=a.n_episodes, seed=a.seed,
                                         checkpoint=a.checkpoint,
                                         train_manifest_digest=train_digest,
                                         videos=videos, raw_log="eval/eval.log")
        (out / "eval_metrics.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        stats = {"dry_run": False, "eval_cmd": cmd_line,
                 "exit_code": rc, "metrics": contract["metrics"]}
        files = ["eval_cmd.sh", "eval_metrics.json", "eval/eval.log"]

    write_manifest(out, op="lerobot-eval", args=vars(a),
                   parents=parents, files=files, stats=stats,
                   extra={"checkpoint": str(a.checkpoint)})
    print(json.dumps(stats, ensure_ascii=False))
    if not dry and stats["exit_code"] != 0:
        return stats["exit_code"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
