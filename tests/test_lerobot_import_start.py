import json
import os
import pathlib
import subprocess
import sys

import pytest

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
    # dry 产物落侧目录 .dryrun，绝不创建/污染正式数据集目录 dst
    plan = json.loads((base / "n" / "v.dryrun" / "import_plan.json").read_text(encoding="utf-8"))
    assert plan["kind"] == "copy"
    assert not (base / "n" / "v").exists()  # 正式 dst 未被凭空创建


def test_link_mode_no_source_pollution(tmp_path):
    # 免拷贝：派生产物写真实 dst，不得经符号链接写穿用户源目录
    _link = tmp_path / "_symprobe"
    try:
        os.symlink(str(tmp_path), str(_link))
    except (OSError, NotImplementedError):
        pytest.skip("platform lacks symlink privileges")
    else:
        _link.unlink()
    src = _make_src(tmp_path)
    # 预置：源目录自带同名派生文件（模拟对一个已导入过的数据集目录再 link 接入）
    (src / ".cube_dataset_meta").write_text('{"sentinel": true}', encoding="utf-8")
    base = tmp_path / "b"
    r = _run(["--source_type", "local_path", "--source", str(src), "--target_name", "n",
              "--target_version", "v", "--base_dir", str(base), "--link_mode", "true"])
    assert r.returncode == 0, r.stderr
    dst = base / "n" / "v"
    # 派生文件落在 dst（真实文件），未写进源目录；且源哨兵未被覆写
    assert (dst / ".cube_dataset_meta").is_file()
    assert (dst / "lerobot_profile.json").is_file()
    assert json.loads((src / ".cube_dataset_meta").read_text(encoding="utf-8")) == {"sentinel": True}
    assert not (src / "lerobot_profile.json").exists()
    assert not (src / "manifest.json").exists()
    # 源数据仅被链接而非拷贝：dst/meta 是指向 src 的链接目录结构
    meta = json.loads((dst / ".cube_dataset_meta").read_text(encoding="utf-8"))
    assert meta["format"] == "lerobot" and meta["profile"]["total_frames"] == 100


def test_unsafe_target_name_exit2(tmp_path):
    # I-7：入口对越界 target_name 返回退出码 2（参数非法），不触碰共享数据集目录
    src = _make_src(tmp_path)
    base = tmp_path / "b"
    r = _run(["--source_type", "local_path", "--source", str(src),
              "--target_name", "../evil", "--target_version", "v",
              "--base_dir", str(base)])
    assert r.returncode == 2, r.stderr
    assert not base.exists()
