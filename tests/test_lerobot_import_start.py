import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = ROOT / "job-template" / "job" / "lerobot_import" / "start.py"


def _make_src(tmp_path):
    src = tmp_path / "src"
    (src / "meta").mkdir(parents=True)
    (src / "meta" / "info.json").write_text(json.dumps({
        "codebase_version": "v3", "total_episodes": 2, "total_frames": 100,
        "fps": 10, "features": {"action": {"dtype": "float32", "shape": [2]}}}),
        encoding="utf-8")
    (src / "data").mkdir()
    (src / "data" / "f000.chunk.parquet").write_bytes(b"PAR1fake")
    return src


def _run(args, env=None):
    return subprocess.run([sys.executable, str(START)] + args,
                          capture_output=True, text=True, env=env)


def test_copy_flow_produces_meta(tmp_path):
    src = _make_src(tmp_path)
    base = tmp_path / "datasetbase"
    r = _run(["--source_type", "local_path", "--source", str(src),
              "--target_name", "n1", "--target_version", "v1", "--base_dir", str(base)])
    assert r.returncode == 0, r.stderr
    dst = base / "n1" / "v1"
    meta = json.loads((dst / ".cube_dataset_meta").read_text(encoding="utf-8"))
    assert meta["format"] == "lerobot" and meta["profile"]["total_frames"] == 100
    assert (dst / "data" / "f000.chunk.parquet").exists()
    m = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    assert m["op"] == "lerobot-import"


def test_overwrite_refused(tmp_path):
    src = _make_src(tmp_path)
    base = tmp_path / "b"
    args = ["--source_type", "local_path", "--source", str(src), "--target_name", "n",
            "--target_version", "v", "--base_dir", str(base)]
    assert _run(args).returncode == 0
    r = _run(args)
    assert r.returncode == 2 and "overwrite" in (r.stderr + r.stdout).lower()


def test_unsupported_version_exit3(tmp_path):
    src = _make_src(tmp_path)
    (src / "meta" / "info.json").write_text('{"codebase_version": "v1"}', encoding="utf-8")
    r = _run(["--source_type", "local_path", "--source", str(src), "--target_name", "n",
              "--target_version", "v", "--base_dir", str(tmp_path / "b")])
    assert r.returncode == 3


def test_missing_info_exit3(tmp_path):
    r = _run(["--source_type", "local_path", "--source", str(tmp_path / "nope"),
              "--target_name", "n", "--target_version", "v",
              "--base_dir", str(tmp_path / "b")])
    assert r.returncode == 3


def test_dryrun_plan_only(tmp_path):
    src = _make_src(tmp_path)
    base = tmp_path / "b"
    env = dict(os.environ, ROBOT_DRYRUN="1")
    r = _run(["--source_type", "local_path", "--source", str(src), "--target_name", "n",
              "--target_version", "v", "--base_dir", str(base)], env)
    assert r.returncode == 0, r.stderr
    plan = json.loads((base / "n" / "v" / "import_plan.json").read_text(encoding="utf-8"))
    assert plan["kind"] == "copy"
    assert not (base / "n" / "v" / "data").exists()  # 未拷贝
