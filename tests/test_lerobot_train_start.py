import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = ROOT / "job-template" / "job" / "lerobot_train" / "start.py"


def test_parse_train_metrics():
    import lerobot_train_metrics as mp
    text = ("step: 100 loss: 0.9\nstep: 200 loss: 0.5\n"
            "step: 300 loss: 0.25\nelapsed time: 120.5 s\n")
    m = mp.parse_train_metrics(text)
    assert m == {"steps_run": 300, "final_train_loss": 0.25, "wall_time_sec": 120.5}
    assert mp.parse_train_metrics("") == {"steps_run": None,
                                          "final_train_loss": None, "wall_time_sec": None}


def _run(args, env=None):
    return subprocess.run([sys.executable, str(START)] + args,
                          capture_output=True, text=True, env=env)


def _base_args(out):
    return ["--policy_type", "act", "--dataset_ref", "d:v1", "--output", str(out)]


def test_dryrun_writes_cmd_sh_and_manifest(tmp_path):
    out = tmp_path / "run1"
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(_base_args(out), env)
    assert r.returncode == 0, r.stderr
    text = (out / "train_cmd.sh").read_text(encoding="utf-8")
    assert "lerobot-train" in text and "--policy.type act" in text
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["op"] == "lerobot-train"


def test_policy_exclusive_exit2(tmp_path):
    r = _run(["--dataset_ref", "d:v1", "--output", str(tmp_path / "o")])
    assert r.returncode == 2


def test_bool_string_values_accepted(tmp_path):
    out = tmp_path / "o2"
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(_base_args(out) + ["--resume", "true", "--wandb_enable", "false",
                                "--extra_args", "--policy.chunk_size 50"], env)
    assert r.returncode == 0, r.stderr
    assert "--resume true" in (out / "train_cmd.sh").read_text(encoding="utf-8")


def test_dataset_parent_recorded(tmp_path):
    # 数据集目录下存在 .cube_dataset_meta 时，manifest.parents 记录其 digest
    base = tmp_path / "dsbase" / "d" / "v1"
    base.mkdir(parents=True)
    (base / ".cube_dataset_meta").write_text('{"format": "lerobot"}', encoding="utf-8")
    out = tmp_path / "o3"
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(_base_args(out) + ["--base_dir", str(tmp_path / "dsbase")], env)
    assert r.returncode == 0, r.stderr
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(m["parents"]) == 1 and m["parents"][0]["digest"]
