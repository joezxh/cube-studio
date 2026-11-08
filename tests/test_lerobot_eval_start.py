import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = ROOT / "job-template" / "job" / "lerobot_eval" / "start.py"


def _run(args, env=None):
    return subprocess.run([sys.executable, str(START)] + args,
                          capture_output=True, text=True, env=env)


def _ckpt(tmp_path, action_dim):
    ck = tmp_path / "checkpoints" / "100" / "pretrained_model"
    ck.mkdir(parents=True)
    (ck / "config.json").write_text(json.dumps(
        {"features": {"action": {"dtype": "float32", "shape": [action_dim]}}}),
        encoding="utf-8")
    return ck


def test_dryrun_ok(tmp_path):
    ck = _ckpt(tmp_path, 2)
    out = tmp_path / "e"
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(["--checkpoint", str(ck), "--env_type", "pusht", "--output", str(out)], env)
    assert r.returncode == 0, r.stderr
    assert "lerobot-eval" in (out / "eval_cmd.sh").read_text(encoding="utf-8")
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["op"] == "lerobot-eval"


def test_dims_mismatch_exit2_before_dryrun(tmp_path):
    ck = _ckpt(tmp_path, 14)  # aloha 维度喂 pusht
    env = dict(os.environ, ROBOT_DRYRUN="1")  # 即使 DRYRUN 也必须拦
    r = _run(["--checkpoint", str(ck), "--env_type", "pusht",
              "--output", str(tmp_path / "e")], env)
    assert r.returncode == 2 and "mismatch" in r.stderr


def test_train_lineage_found(tmp_path):
    ck = _ckpt(tmp_path, 2)
    train_root = ck.parents[2]  # {output}/checkpoints/100/pretrained_model 上溯 3 层
    (train_root / "manifest.json").write_text(json.dumps(
        {"op": "lerobot-train", "self_digest": "deadbeef"}), encoding="utf-8")
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(["--checkpoint", str(ck), "--env_type", "pusht",
              "--output", str(tmp_path / "e")], env)
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path / "e" / "manifest.json").read_text(encoding="utf-8"))
    assert any("deadbeef" in str(p) for p in m["parents"])


def test_unknown_env_skips_check(tmp_path):
    ck = _ckpt(tmp_path, 99)
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(["--checkpoint", str(ck), "--env_type", "mycustom",
              "--output", str(tmp_path / "e")], env)
    assert r.returncode == 0, r.stderr
