# 具身智能 / VLA 训练（LeRobot 整合）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 LeRobotDataset 数据接入（F2）→ lerobot-train 训练（F1）→ lerobot-eval 仿真评测（F3）的具身智能训练最小闭环，产物与指标全部落平台既有契约。

**Architecture:** 三个独立算子模板（start.py 入口 + 纯函数 cmd/profile/parser 模块 + Dockerfile，复刻 gov-sft 已验证模式），共享一个 manifest 血缘库；GPU/CPU 两镜像切分；指标契约用平台自有 schema（contract_version=1），解析器隔离 lerobot 上游格式；F2 算子不写 DB，产物留 `.cube_dataset_meta` 由 view_dataset 登记识别。

**Tech Stack:** Python 3.11、lerobot==0.6.2、gym-pusht/gym-aloha、MuJoCo EGL、pytest（tests/ conftest 惰性加载基建）、k8s batch Job、cube-studio job-template 体系。

**Spec:** `docs/superpowers/specs/2026-11-08-lerobot-embodied-training-design.md`（实施依据，本计划覆盖其 §1–§8 与附录 A/B）

## Global Constraints

- lerobot 版本锁 `0.6.2`；v1 GPU 锚点单卡 ≤24G（spec §1.3）
- 测试命令统一 `python -m pytest tests/<file> -v`（顶层 `pytest.ini` 已含 `--basetemp=.pytest-tmp`，Windows PowerShell 执行）
- `tests/conftest.py` 只做**增量追加** `_load_module(...)` 行，禁止覆盖既有内容
- 被测 cmd/util 模块禁止 `import myapp.*`；算子目录间禁止互相 import，唯一例外是 `job-template/job/lerobot_shared/`（manifest 共享库，spec §2.2）
- 算子命令组装一律返回 `list[str]`，每个 `--flag value` 为相邻两个单元素（母文档 §7.3 CLI 约定）
- DRYRUN 环境变量 `ROBOT_DRYRUN=1`：只产 `*_cmd.sh`/plan 文件，不执行 subprocess
- 数据集基路径常量 `/data/k8s/kubeflow/global/dataset`（可被 `--base_dir` 参数覆盖，测试用）
- 每个 Task 结束提交一次 commit，`git add` 只加本 Task 文件
- 本地数据集传参形态默认 `--dataset.repo_id + --dataset.root`（spec §4.3 实测锁定项，真机验收时确认，改动收敛在 `lerobot_train_cmd.py` 一处）

---

## 文件结构

```
job-template/job/lerobot_shared/manifest_util.py      # T1 血缘共享库
job-template/job/lerobot_import/import_cmd.py         # T2 纯函数：版本校验/路径解析/ref解析
job-template/job/lerobot_import/profile.py            # T3 纯函数：info.json → 画像
job-template/job/lerobot_import/start.py              # T4 入口
myapp/init/init-job-template.json                     # T11 追加 3 模板（import/train/eval 条目）
job-template/job/lerobot_train/train_cmd.py           # T5 纯函数：训练命令组装
job-template/job/lerobot_train/metrics_parser.py      # T6 纯函数：stdout → metrics
job-template/job/lerobot_train/start.py               # T6 入口
job-template/job/lerobot_eval/eval_cmd.py             # T7 纯函数：评测命令 + 维度校验
job-template/job/lerobot_eval/metrics_contract.py     # T8 纯函数：stdout → 契约 schema
job-template/job/lerobot_eval/start.py                # T9 入口
myapp/utils/lerobot_dataset_meta.py                   # T10 helper（纯标准库）
myapp/views/view_dataset.py                           # T10 hook（登记识别）
images/lerobot/Dockerfile-import                      # T11
images/lerobot/Dockerfile-gpu                         # T11
images/lerobot/build.sh                               # T11
myapp/example/pipeline/lerobot-embodied/              # T12 示例链路 README + demo JSON
tests/test_lerobot_*.py                               # 各 Task 测试
tests/conftest.py                                     # 增量追加加载行
```

---

### Task 1: manifest 共享库

**Files:**
- Create: `job-template/job/lerobot_shared/manifest_util.py`
- Create: `tests/test_lerobot_manifest.py`
- Modify: `tests/conftest.py`（末尾追加一行）

**Interfaces:**
- Consumes: 无
- Produces: `sha256_file(path) -> str | None`；`write_manifest(out_dir, *, op, args, parents, files, stats=None, extra=None) -> dict`（写 `manifest.json`，含 `self_digest`；`files` 按 `out_dir` 相对路径解析 digest，缺失文件 digest=None 不报错；`self_digest` 不含 `created_at`，同输入两次写摘要一致）

- [ ] **Step 1: conftest 追加加载行**

在 `tests/conftest.py` 末尾追加：

```python
_load_module('lerobot_manifest_util', 'job-template/job/lerobot_shared/manifest_util.py')
```

- [ ] **Step 2: 写失败测试**

`tests/test_lerobot_manifest.py`：

```python
import json

import lerobot_manifest_util as mu


def test_write_manifest_fields_and_digest(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    body = mu.write_manifest(tmp_path, op="lerobot-train",
                             args={"steps": 10}, parents=[{"path": "p", "digest": "d"}],
                             files=["a.txt"], stats={"k": 1})
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["op"] == "lerobot-train"
    assert m["parents"] == [{"path": "p", "digest": "d"}]
    assert m["files"][0]["path"] == "a.txt"
    assert m["files"][0]["digest"] == mu.sha256_file(tmp_path / "a.txt")
    assert m["self_digest"] == body["self_digest"]
    assert len(m["self_digest"]) == 64


def test_digest_stable_across_writes(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    b1 = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["a.txt"])
    b2 = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["a.txt"])
    assert b1["self_digest"] == b2["self_digest"]  # created_at 不得进入摘要


def test_missing_file_digest_none(tmp_path):
    body = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["nope.txt"])
    assert body["files"][0]["digest"] is None
```

- [ ] **Step 3: 跑红灯**

Run: `python -m pytest tests/test_lerobot_manifest.py -v`
Expected: ModuleNotFoundError（conftest 对不存在文件 return，测试 import 报错）

- [ ] **Step 4: 实现 manifest_util.py**

```python
"""lerobot 算子共享库：manifest 血缘写入（spec §2.2，唯一允许跨算子引用的模块）。"""
import hashlib
import json
import pathlib
import time


def sha256_file(path):
    p = pathlib.Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(out_dir, *, op, args, parents, files, stats=None, extra=None):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    body = {
        "op": op,
        "args": args,
        "parents": list(parents or []),
        "files": [{"path": f, "digest": sha256_file(out / f)} for f in (files or [])],
        "stats": stats or {},
        "extra": extra or {},
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True)
    body["self_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    body["created_at"] = int(time.time())
    (out / "manifest.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return body
```

- [ ] **Step 5: 跑绿灯**

Run: `python -m pytest tests/test_lerobot_manifest.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add job-template/job/lerobot_shared/manifest_util.py tests/test_lerobot_manifest.py tests/conftest.py
git commit -m "feat(lerobot): manifest 血缘共享库"
```

---

### Task 2: F2 纯函数 import_cmd

**Files:**
- Create: `job-template/job/lerobot_import/import_cmd.py`
- Create: `tests/test_lerobot_import_cmd.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces: 常量 `SUPPORTED_FORMATS=("v2.1","v3")`、`BASE_DIR="/data/k8s/kubeflow/global/dataset"`；`validate_info(info)->str`；`parse_dataset_ref(ref)->(name,version)`；`resolve_paths(source_type, source, target_name, target_version, base_dir=BASE_DIR, link_mode=False)->{"kind","src","dst"}`（kind ∈ copy/link/hub）

- [ ] **Step 1: conftest 追加 + 写失败测试**

conftest 追加：

```python
_load_module('lerobot_import_cmd', 'job-template/job/lerobot_import/import_cmd.py')
```

`tests/test_lerobot_import_cmd.py`：

```python
import pytest

import lerobot_import_cmd as ic


def test_validate_info_ok_versions():
    assert ic.validate_info({"codebase_version": "v3"}) == "v3"
    assert ic.validate_info({"codebase_version": "v2.1"}) == "v2.1"


def test_validate_info_reject_unknown():
    with pytest.raises(ValueError, match="codebase_version"):
        ic.validate_info({"codebase_version": "v1"})
    with pytest.raises(ValueError):
        ic.validate_info({})


def test_parse_dataset_ref():
    assert ic.parse_dataset_ref("pusht_demo:v1") == ("pusht_demo", "v1")
    for bad in ("noColon", ":v1", "n:", ""):
        with pytest.raises(ValueError):
            ic.parse_dataset_ref(bad)


def test_resolve_paths_kinds():
    p = ic.resolve_paths("hub_repo_id", "lerobot/pusht", "n", "v1")
    assert p == {"kind": "hub", "src": "lerobot/pusht",
                 "dst": "/data/k8s/kubeflow/global/dataset/n/v1"}
    assert ic.resolve_paths("local_path", "/mnt/x", "n", "v1")["kind"] == "copy"
    assert ic.resolve_paths("local_path", "/mnt/x", "n", "v1", link_mode=True)["kind"] == "link"
    with pytest.raises(ValueError):
        ic.resolve_paths("ftp", "x", "n", "v1")
```

- [ ] **Step 2: 跑红灯**

Run: `python -m pytest tests/test_lerobot_import_cmd.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 import_cmd.py**

```python
"""lerobot-import 纯函数命令层（spec §3，单测对象；禁止 import myapp.*）。"""

SUPPORTED_FORMATS = ("v2.1", "v3")
BASE_DIR = "/data/k8s/kubeflow/global/dataset"


def validate_info(info):
    v = str((info or {}).get("codebase_version", ""))
    if v not in SUPPORTED_FORMATS:
        raise ValueError(
            "unsupported codebase_version: %r, expect one of %s" % (v, SUPPORTED_FORMATS))
    return v


def parse_dataset_ref(ref):
    parts = str(ref).split(":")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError("dataset_ref must be name:version, got %r" % (ref,))
    return parts[0].strip(), parts[1].strip()


def resolve_paths(source_type, source, target_name, target_version,
                  base_dir=BASE_DIR, link_mode=False):
    if source_type not in ("local_path", "hub_repo_id"):
        raise ValueError("source_type must be local_path/hub_repo_id, got %r" % (source_type,))
    dst = "%s/%s/%s" % (str(base_dir).rstrip("/"), target_name, target_version)
    if source_type == "hub_repo_id":
        return {"kind": "hub", "src": str(source), "dst": dst}
    return {"kind": "link" if link_mode else "copy", "src": str(source), "dst": dst}
```

- [ ] **Step 4: 跑绿灯**

Run: `python -m pytest tests/test_lerobot_import_cmd.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_import/import_cmd.py tests/test_lerobot_import_cmd.py tests/conftest.py
git commit -m "feat(lerobot): import 算子纯函数层（版本校验/路径解析/ref）"
```

---

### Task 3: F2 画像生成 profile.py

**Files:**
- Create: `job-template/job/lerobot_import/lerobot_profile.py`（命名避开标准库 `profile`，防 sys.path 遮蔽隐患）
- Create: `tests/test_lerobot_profile.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: LeRobotDataset `meta/info.json` 的 dict 形态（v3：`codebase_version/total_episodes/total_frames/fps/features{name:{dtype,shape}}`）
- Produces: `build_profile(info: dict, task_counts: dict | None) -> dict`（键：`format_version/total_episodes/total_frames/fps/video_keys/action_dim/state_dim/task_distribution/video_total_sec`）

- [ ] **Step 1: conftest 追加 + 写失败测试**

conftest 追加 `_load_module('lerobot_profile', 'job-template/job/lerobot_import/lerobot_profile.py')`。

`tests/test_lerobot_profile.py`：

```python
import lerobot_profile as pr

INFO = {
    "codebase_version": "v3", "total_episodes": 20, "total_frames": 4000, "fps": 20,
    "features": {
        "action": {"dtype": "float32", "shape": [2]},
        "observation.state": {"dtype": "float32", "shape": [4]},
        "observation.images.image": {"dtype": "video", "shape": [480, 640, 3]},
    },
}


def test_build_profile_core():
    p = pr.build_profile(INFO, {"push a": 12, "push b": 8})
    assert p["format_version"] == "v3"
    assert p["total_episodes"] == 20 and p["total_frames"] == 4000
    assert p["fps"] == 20.0
    assert p["video_keys"] == ["observation.images.image"]
    assert p["action_dim"] == 2 and p["state_dim"] == 4
    assert p["task_distribution"] == {"push a": 12, "push b": 8}
    assert p["video_total_sec"] == 200.0


def test_no_tasks_and_zero_fps_safe():
    p = pr.build_profile({"codebase_version": "v2.1", "total_frames": 10, "fps": 0,
                          "total_episodes": 1, "features": {}}, None)
    assert p["task_distribution"] is None
    assert p["video_total_sec"] is None
    assert p["action_dim"] is None
```

- [ ] **Step 2: 跑红灯** — Run: `python -m pytest tests/test_lerobot_profile.py -v`，Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 lerobot_profile.py**

```python
"""lerobot-import 画像纯函数（spec §3.2 步骤3；仅依赖 info.json dict，无 parquet 硬依赖）。"""


def build_profile(info, task_counts=None):
    feats = (info or {}).get("features", {}) or {}

    def dim_of(name):
        shape = (feats.get(name) or {}).get("shape") or []
        return int(shape[0]) if shape else None

    video_keys = sorted(k for k, v in feats.items()
                        if str(v.get("dtype", "")) in ("video", "image"))
    frames = int(info.get("total_frames", 0))
    fps = float(info.get("fps", 0) or 0)
    return {
        "format_version": info.get("codebase_version"),
        "total_episodes": int(info.get("total_episodes", 0)),
        "total_frames": frames,
        "fps": fps,
        "video_keys": video_keys,
        "action_dim": dim_of("action"),
        "state_dim": dim_of("observation.state"),
        "task_distribution": task_counts or None,
        "video_total_sec": round(frames / fps, 2) if fps else None,
    }
```

- [ ] **Step 4: 跑绿灯** — Expected: 2 passed
- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_import/lerobot_profile.py tests/test_lerobot_profile.py tests/conftest.py
git commit -m "feat(lerobot): LeRobotDataset 画像生成纯函数"
```

---

### Task 4: F2 start.py 入口（拷贝/软链/Hub、拒绝覆盖、产物落盘）

**Files:**
- Create: `job-template/job/lerobot_import/start.py`
- Create: `tests/test_lerobot_import_start.py`

**Interfaces:**
- Consumes: Task 2 `import_cmd`、Task 3 `profile`、Task 1 `manifest_util`（同目录 sibling + `lerobot_shared` 路径注入）
- Produces: CLI `python start.py --source_type --source --target_name --target_version [--hub_endpoint ""] [--link_mode] [--base_dir <基路径>]`；产物全部落在 `{dst}`（数据集目录）内：`.cube_dataset_meta`（`{"format":"lerobot","version","source","profile"}`）、`lerobot_profile.json`、`manifest.json`；`ROBOT_DRYRUN=1` 时只产 `{dst}.dryrun/import_plan.json` + manifest（不触碰正式数据集目录，避免凭空创建/覆写真实血缘），不拷贝；退出码：2=目标非空拒绝覆盖，3=格式不支持/缺 info.json/Hub 拉取失败

- [ ] **Step 1: 写失败测试**

`tests/test_lerobot_import_start.py`（subprocess 驱动，fixture 用纯 json 假数据集目录）：

```python
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
```

- [ ] **Step 2: 跑红灯** — Run: `python -m pytest tests/test_lerobot_import_start.py -v`，Expected: 5 failed（start.py 不存在）

- [ ] **Step 3: 实现 start.py**

```python
"""lerobot-import 入口（spec §3；DRYRUN 只产 import_plan.json；算子不写 DB）。"""
import argparse
import json
import os
import pathlib
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lerobot_shared"))

import import_cmd  # noqa: E402
import lerobot_profile as profile_mod  # noqa: E402
from manifest_util import write_manifest  # noqa: E402


def _task_counts(dst):
    """v3 任务分布在 meta/tasks.parquet；pyarrow/pandas 缺失或文件不存在时返回 None。"""
    p = pathlib.Path(dst) / "meta" / "tasks.parquet"
    if not p.is_file():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        if "task_index" not in df.columns:
            return None
        return {str(k): int(v) for k, v in df["task_index"].value_counts().items()}
    except Exception:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(prog="lerobot-import")
    p.add_argument("--source_type", required=True, choices=["local_path", "hub_repo_id"])
    p.add_argument("--source", required=True)
    p.add_argument("--target_name", required=True)
    p.add_argument("--target_version", default="v1")
    p.add_argument("--hub_endpoint", default="")
    p.add_argument("--link_mode", action="store_true")
    p.add_argument("--base_dir", default=import_cmd.BASE_DIR)
    a = p.parse_args(argv)
    dry = os.environ.get("ROBOT_DRYRUN") == "1"

    plan = import_cmd.resolve_paths(a.source_type, a.source, a.target_name,
                                    a.target_version, a.base_dir, a.link_mode)
    dst = pathlib.Path(plan["dst"])

    if dry:
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "import_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        write_manifest(dst, op="lerobot-import", args=vars(a), parents=[],
                       files=["import_plan.json"], stats={"dry_run": True})
        print(json.dumps({"dry_run": True, "plan": plan}))
        return 0

    if plan["kind"] == "hub":
        if dst.exists() and any(dst.iterdir()):
            print("target %s not empty, overwrite refused" % dst, file=sys.stderr)
            return 2
        dst.parent.mkdir(parents=True, exist_ok=True)
        if a.hub_endpoint:
            os.environ["HF_ENDPOINT"] = a.hub_endpoint
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=plan["src"], repo_type="dataset",
                          local_dir=str(dst), allow_patterns=None)
    else:
        src = pathlib.Path(plan["src"])
        info_file = src / "meta" / "info.json"
        if not info_file.is_file():
            print("missing meta/info.json in %s" % src, file=sys.stderr)
            return 3
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            import_cmd.validate_info(info)
        except (ValueError, json.JSONDecodeError) as e:
            print(str(e), file=sys.stderr)
            return 3
        if dst.exists() and any(dst.iterdir()):
            print("target %s not empty, overwrite refused" % dst, file=sys.stderr)
            return 2
        dst.parent.mkdir(parents=True, exist_ok=True)
        if plan["kind"] == "link":
            os.symlink(str(src.resolve()), str(dst))
        else:
            shutil.copytree(str(src), str(dst))

    info = json.loads((dst / "meta" / "info.json").read_text(encoding="utf-8"))
    prof = profile_mod.build_profile(info, _task_counts(dst))
    (dst / "lerobot_profile.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = {"format": "lerobot", "version": prof["format_version"],
            "source": plan["src"], "profile": prof}
    (dst / ".cube_dataset_meta").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest(dst, op="lerobot-import",
                   args={k: v for k, v in vars(a).items() if v not in (None, "", False)},
                   parents=[], files=["meta/info.json", ".cube_dataset_meta",
                                      "lerobot_profile.json"],
                   stats={"dry_run": False, "total_frames": prof["total_frames"],
                          "total_episodes": prof["total_episodes"]},
                   extra={"dataset_dir": str(dst)})
    print(json.dumps({"dst": str(dst), "profile": prof}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑绿灯** — Run: `python -m pytest tests/test_lerobot_import_start.py -v`，Expected: 5 passed
- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_import/start.py tests/test_lerobot_import_start.py
git commit -m "feat(lerobot): import 算子入口（拷贝/Hub/拒绝覆盖/画像落盘）"
```

---

### Task 5: F1 train_cmd 纯函数

**Files:**
- Create: `job-template/job/lerobot_train/train_cmd.py`
- Create: `tests/test_lerobot_train_cmd.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: Task 2 的 `parse_dataset_ref` 语义（`name:version`；本模块自带等价实现，禁止跨算子 import）
- Produces: `build_train_cmd(*, dataset_ref, output_dir, policy_type=None, policy_path=None, batch_size=8, steps=10000, save_freq=5000, log_freq=200, lr=None, resume=False, wandb_enable=False, extra_args="", base_dir="/data/k8s/kubeflow/global/dataset") -> list[str]`；异常：`ValueError`（policy 互斥 / dataset_ref 非法 / extra_args 违规）；本地数据集形态 `--dataset.repo_id local/{name}_{version}` + `--dataset.root {base_dir}/{name}/{version}`（spec §4.3 实测锁定项）

- [ ] **Step 1: conftest 追加 `_load_module('lerobot_train_cmd', 'job-template/job/lerobot_train/train_cmd.py')` + 写失败测试**

`tests/test_lerobot_train_cmd.py`：

```python
import pytest

import lerobot_train_cmd as tc


def test_basic_act_pairwise_flags():
    cmd = tc.build_train_cmd(policy_type="act", dataset_ref="demo:v1",
                             output_dir="/mnt/train/j1")
    assert cmd[0] == "lerobot-train"
    assert cmd[1] == "--policy.type" and cmd[2] == "act"
    # 每个 flag 后必须紧跟一个 value：奇偶位校验
    assert all(str(c).startswith("--") for c in cmd[1::2])
    assert all(not str(c).startswith("--") for c in cmd[2::2])
    assert cmd[cmd.index("--dataset.root") + 1] == \
        "/data/k8s/kubeflow/global/dataset/demo/v1"
    assert cmd[cmd.index("--dataset.repo_id") + 1] == "local/demo_v1"
    assert cmd[cmd.index("--output_dir") + 1] == "/mnt/train/j1"
    assert cmd[cmd.index("--batch_size") + 1] == "8"
    assert cmd[cmd.index("--steps") + 1] == "10000"
    assert cmd[cmd.index("--wandb.enable") + 1] == "false"
    assert cmd[cmd.index("--resume") + 1] == "false"


def test_policy_exclusive():
    with pytest.raises(ValueError):
        tc.build_train_cmd(dataset_ref="d:v1", output_dir="/o")
    with pytest.raises(ValueError):
        tc.build_train_cmd(policy_type="act", policy_path="/ckpt",
                           dataset_ref="d:v1", output_dir="/o")


def test_policy_path_skips_type():
    cmd = tc.build_train_cmd(policy_path="lerobot/smolvla_base",
                             dataset_ref="d:v1", output_dir="/o")
    assert "--policy.path" in cmd and "--policy.type" not in cmd


def test_optional_and_extra_args():
    cmd = tc.build_train_cmd(policy_type="smolvla", dataset_ref="d:v1", output_dir="/o",
                             lr="1e-4", resume=True, wandb_enable=True,
                             extra_args="--policy.chunk_size 50 --env.type pusht")
    assert cmd[cmd.index("--optimizer.lr") + 1] == "1e-4"
    assert cmd[cmd.index("--resume") + 1] == "true"
    assert cmd[cmd.index("--wandb.enable") + 1] == "true"
    assert cmd[-4:] == ["--policy.chunk_size", "50", "--env.type", "pusht"]


def test_extra_args_rejected():
    for bad in ("rm -rf /", "ls;whoami", "--ok $(x)", "echo hi"):
        with pytest.raises(ValueError):
            tc.build_train_cmd(policy_type="act", dataset_ref="d:v1",
                               output_dir="/o", extra_args=bad)
```

- [ ] **Step 2: 跑红灯** — Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 train_cmd.py**

```python
"""lerobot-train 命令组装纯函数（spec §4；本地数据集默认 --dataset.repo_id + --dataset.root，
spec §4.3 实测锁定项，如需改形态只改本函数拼装两处）。"""
import shlex

BASE_DIR = "/data/k8s/kubeflow/global/dataset"
_META_CHARS = set(";|&$<>`\n'\"")


def parse_dataset_ref(ref):
    parts = str(ref).split(":")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError("dataset_ref must be name:version, got %r" % (ref,))
    return parts[0].strip(), parts[1].strip()


def _validate_extra(extra_args):
    tokens = shlex.split(str(extra_args)) if extra_args else []
    if len(tokens) % 2 != 0:
        raise ValueError("extra_args must be flag-value pairs")
    for i, tok in enumerate(tokens):
        if i % 2 == 0 and not tok.startswith("--"):
            raise ValueError("extra flag must start with --: %r" % (tok,))
        if i % 2 == 1 and _META_CHARS & set(tok):
            raise ValueError("shell metacharacters forbidden in value: %r" % (tok,))
    return tokens


def build_train_cmd(*, dataset_ref, output_dir, policy_type=None, policy_path=None,
                    batch_size=8, steps=10000, save_freq=5000, log_freq=200,
                    lr=None, resume=False, wandb_enable=False,
                    extra_args="", base_dir=BASE_DIR):
    if bool(policy_type) == bool(policy_path):
        raise ValueError("exactly one of policy_type/policy_path required")
    name, version = parse_dataset_ref(dataset_ref)
    cmd = ["lerobot-train"]
    if policy_type:
        cmd += ["--policy.type", str(policy_type)]
    else:
        cmd += ["--policy.path", str(policy_path)]
    cmd += ["--dataset.repo_id", "local/%s_%s" % (name, version),
            "--dataset.root", "%s/%s/%s" % (str(base_dir).rstrip("/"), name, version),
            "--output_dir", str(output_dir),
            "--batch_size", str(batch_size), "--steps", str(steps),
            "--save_freq", str(save_freq), "--log_freq", str(log_freq),
            "--resume", "true" if resume else "false",
            "--wandb.enable", "true" if wandb_enable else "false"]
    if lr:
        cmd += ["--optimizer.lr", str(lr)]
    cmd += _validate_extra(extra_args)
    return cmd
```

- [ ] **Step 4: 跑绿灯** — Expected: 5 passed
- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_train/train_cmd.py tests/test_lerobot_train_cmd.py tests/conftest.py
git commit -m "feat(lerobot): train 命令组装纯函数（互斥校验/extra 白名单）"
```

---

### Task 6: F1 stdout 解析 + start.py

**Files:**
- Create: `job-template/job/lerobot_train/metrics_parser.py`
- Create: `job-template/job/lerobot_train/start.py`
- Create: `tests/test_lerobot_train_start.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: Task 5 `build_train_cmd`/`parse_dataset_ref`（同目录 sibling）；Task 1 `write_manifest`/`sha256_file`
- Produces: `parse_train_metrics(text: str) -> dict`（`{steps_run:int|None, final_train_loss:float|None, wall_time_sec:float|None}`，容错取最后一次匹配）；train `start.py` CLI：`--policy_type --policy_path --dataset_ref --output [--batch_size 8 --steps 10000 --save_freq 5000 --log_freq 200 --lr "" --resume false --wandb_enable false --extra_args "" --base_dir <基路径>]`（bool 串值接受 true/1/yes）；产物 `{output}/train_cmd.sh`、真实模式另有 `{output}/train.log`、`{output}/metrics.json`；退出码 2=参数非法（互斥/ref/extra），非 0=训练透传

- [ ] **Step 1: conftest 追加 `_load_module('lerobot_train_metrics', 'job-template/job/lerobot_train/metrics_parser.py')` + 写失败测试**

`tests/test_lerobot_train_start.py`：

```python
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
```

- [ ] **Step 2: 跑红灯** — Run: `python -m pytest tests/test_lerobot_train_start.py -v`，Expected: 6 failed（metrics_parser 缺 + start.py 不存在）

- [ ] **Step 3: 实现 metrics_parser.py**

```python
"""lerobot-train stdout → metrics.json 纯函数解析（spec §4.2；上游日志漂移只改这里）。"""
import re

_STEP = re.compile(r"step[:=\s]+(\d+)", re.I)
_LOSS = re.compile(r"loss[:=\s]+([-+0-9.eE]+)", re.I)
_TIME = re.compile(r"(?:elapsed|total_time|wall)[^\d]*([0-9]+(?:\.[0-9]+)?)", re.I)


def parse_train_metrics(text):
    steps = _STEP.findall(text or "")
    losses = _LOSS.findall(text or "")
    times = _TIME.findall(text or "")
    return {"steps_run": int(steps[-1]) if steps else None,
            "final_train_loss": float(losses[-1]) if losses else None,
            "wall_time_sec": float(times[-1]) if times else None}
```

- [ ] **Step 4: 实现 train start.py**

```python
"""lerobot-train 入口（spec §4；DRYRUN 只产 train_cmd.sh）。"""
import argparse
import json
import os
import pathlib
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
    p.add_argument("--resume", default="false")
    p.add_argument("--wandb_enable", default="false")
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

    (out / "train_cmd.sh").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    name, version = train_cmd.parse_dataset_ref(a.dataset_ref)
    dataset_meta = pathlib.Path(a.base_dir) / name / version / ".cube_dataset_meta"
    parents = [{"path": str(dataset_meta), "digest": sha256_file(dataset_meta)}]

    if dry:
        stats = {"dry_run": True, "train_cmd": " ".join(cmd)}
        files = ["train_cmd.sh"]
    else:
        with open(out / "train.log", "w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
        text = (out / "train.log").read_text(encoding="utf-8")
        metrics = parse_train_metrics(text)
        metrics.update({"policy_type": a.policy_type, "dataset_ref": a.dataset_ref})
        (out / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        stats = {"dry_run": False, "train_cmd": " ".join(cmd),
                 "exit_code": proc.returncode}
        files = ["train_cmd.sh", "metrics.json", "train.log"]

    write_manifest(out, op="lerobot-train",
                   args={k: v for k, v in vars(a).items() if v != ""},
                   parents=parents, files=files, stats=stats)
    print(json.dumps(stats, ensure_ascii=False))
    return 0 if dry or stats["exit_code"] == 0 else stats["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 跑绿灯** — Run: `python -m pytest tests/test_lerobot_train_start.py -v`，Expected: 6 passed
- [ ] **Step 6: Commit**

```bash
git add job-template/job/lerobot_train/metrics_parser.py job-template/job/lerobot_train/start.py tests/test_lerobot_train_start.py tests/conftest.py
git commit -m "feat(lerobot): train 算子入口与 metrics 解析"
```

---

### Task 7: F3 eval_cmd + 动作维度校验

**Files:**
- Create: `job-template/job/lerobot_eval/eval_cmd.py`
- Create: `tests/test_lerobot_eval_cmd.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces: 常量 `ENV_ACTION_DIM={"pusht":2,"aloha":14}`；`build_eval_cmd(*, checkpoint, env_type, n_episodes=50, batch_size=10, seed=100000, video_n_episodes=3, output_dir) -> list[str]`；`extract_action_dim(policy_config: dict) -> int|None`（查找顺序 `shape_metadata` 各条目 shape[0] → `features.action.shape[0]` → `output_features.action[0]`）；`check_action_dims(policy_config, env_type) -> (ok: bool, reason: str)`（env 未预设或维度不可得 → ok=True 跳过）

- [ ] **Step 1: conftest 追加 `_load_module('lerobot_eval_cmd', 'job-template/job/lerobot_eval/eval_cmd.py')` + 写失败测试**

`tests/test_lerobot_eval_cmd.py`：

```python
import lerobot_eval_cmd as ec


def test_build_eval_cmd_pairs():
    cmd = ec.build_eval_cmd(checkpoint="/ckpt/p", env_type="pusht",
                            n_episodes=5, output_dir="/e")
    assert cmd[0] == "lerobot-eval"
    assert cmd[1] == "--policy.path" and cmd[2] == "/ckpt/p"
    assert cmd[cmd.index("--env.type") + 1] == "pusht"
    assert cmd[cmd.index("--eval.n_episodes") + 1] == "5"
    assert cmd[cmd.index("--seed") + 1] == "100000"
    assert cmd[cmd.index("--eval.video.n_episodes") + 1] == "3"
    assert all(str(c).startswith("--") for c in cmd[1::2])


def test_zero_video_skips_flag():
    cmd = ec.build_eval_cmd(checkpoint="/c", env_type="aloha",
                            video_n_episodes=0, output_dir="/e")
    assert "--eval.video.n_episodes" not in cmd


def test_dims_mismatch_detected():
    cfg = {"shape_metadata": {"a": {"type": "action", "shape": [14], "names": None}}}
    ok, reason = ec.check_action_dims(cfg, "pusht")
    assert not ok and "14" in reason and "2" in reason


def test_dims_match_or_skip():
    cfg = {"features": {"action": {"dtype": "float32", "shape": [2]}}}
    assert ec.check_action_dims(cfg, "pusht")[0]
    assert ec.check_action_dims({}, "pusht")[0]      # 维度不可得 → 跳过
    assert ec.check_action_dims(
        {"shape_metadata": {"a": {"shape": [99]}}}, "custom_env")[0]  # 未预设 env → 跳过
```

- [ ] **Step 2: 跑红灯** — Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 eval_cmd.py**

```python
"""lerobot-eval 命令组装与启动前动作维度校验（spec §5.3；代替静态兼容矩阵）。"""

ENV_ACTION_DIM = {"pusht": 2, "aloha": 14}


def build_eval_cmd(*, checkpoint, env_type, n_episodes=50, batch_size=10,
                   seed=100000, video_n_episodes=3, output_dir):
    cmd = ["lerobot-eval", "--policy.path", str(checkpoint),
           "--env.type", str(env_type),
           "--eval.n_episodes", str(n_episodes),
           "--eval.batch_size", str(batch_size),
           "--seed", str(seed), "--eval.output_dir", str(output_dir)]
    if int(video_n_episodes) > 0:
        cmd += ["--eval.video.n_episodes", str(video_n_episodes)]
    return cmd


def extract_action_dim(policy_config):
    cfg = policy_config or {}
    for entry in (cfg.get("shape_metadata") or {}).values():
        shape = (entry or {}).get("shape")
        if shape:
            return int(shape[0])
    feats = cfg.get("features") or {}
    shape = (feats.get("action") or {}).get("shape")
    if shape:
        return int(shape[0])
    out_dim = (cfg.get("output_features") or {}).get("action")
    if isinstance(out_dim, (list, tuple)) and out_dim:
        return int(out_dim[0])
    return None


def check_action_dims(policy_config, env_type):
    env_dim = ENV_ACTION_DIM.get(env_type)
    if env_dim is None:
        return True, "env %r not preset, skip dim check" % env_type
    p_dim = extract_action_dims(policy_config)
    if p_dim is None:
        return True, "action shape not found, skip dim check"
    if p_dim != env_dim:
        return False, ("action dim mismatch: policy=%d env=%s=%d"
                       % (p_dim, env_type, env_dim))
    return True, "ok"
```

- [ ] **Step 4: 跑绿灯** — Expected: 4 passed
- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_eval/eval_cmd.py tests/test_lerobot_eval_cmd.py tests/conftest.py
git commit -m "feat(lerobot): eval 命令组装与动作维度启动前校验"
```

---

### Task 8: F3 指标契约解析器

**Files:**
- Create: `job-template/job/lerobot_eval/metrics_contract.py`
- Create: `tests/test_lerobot_metrics_contract.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces: `parse_eval_summary(text: str) -> dict`（`{success_rate:float|None(0-1), mean_return, mean_episode_len, n_evaluated:int|None, n_success:int|None}`）；`build_eval_metrics(summary, *, env, n_episodes, seed, checkpoint, train_manifest_digest=None, videos=None, raw_log="eval.log") -> dict`（契约 v1 全结构，与 spec §5.2 schema 逐字段一致）

- [ ] **Step 1: conftest 追加 `_load_module('lerobot_metrics_contract', 'job-template/job/lerobot_eval/metrics_contract.py')` + 写失败测试**

`tests/test_lerobot_metrics_contract.py`：

```python
import lerobot_metrics_contract as mc

TEXT = ("Success rate: 82.00% (41/50)\n"
        "mean return: 14.6\nmean episode length: 96.3\n")


def test_parse_summary():
    s = mc.parse_eval_summary(TEXT)
    assert abs(s["success_rate"] - 0.82) < 1e-9
    assert s["n_success"] == 41 and s["n_evaluated"] == 50
    assert s["mean_return"] == 14.6 and s["mean_episode_len"] == 96.3


def test_parse_empty_safe():
    s = mc.parse_eval_summary("nothing here")
    assert s == {"success_rate": None, "mean_return": None,
                 "mean_episode_len": None, "n_evaluated": None, "n_success": None}


def test_contract_shape():
    c = mc.build_eval_metrics(mc.parse_eval_summary(TEXT), env="pusht",
                              n_episodes=50, seed=100000, checkpoint="/ck/last",
                              train_manifest_digest="abc123", videos=["v0.mp4"])
    assert c["contract_version"] == "1"
    assert c["source"] == {"type": "lerobot-eval", "env": "pusht",
                           "n_episodes": 50, "seed": 100000}
    assert c["policy_ref"]["checkpoint_path"] == "/ck/last"
    assert c["policy_ref"]["train_manifest_digest"] == "abc123"
    assert c["metrics"]["success_rate"] == 0.82
    assert c["artifacts"]["videos"] == ["v0.mp4"] and c["artifacts"]["raw_log"] == "eval.log"


def test_gap_recorded():
    s = mc.parse_eval_summary("Success rate: 80.00% (40/50)\n")
    s["n_evaluated"] = 45  # 上游崩溃缺口
    c = mc.build_eval_metrics(s, env="pusht", n_episodes=50, seed=1, checkpoint="/ck")
    assert c["metrics"]["n_evaluated"] == 45
    assert c["policy_ref"]["train_manifest_digest"] is None
```

- [ ] **Step 2: 跑红灯** — Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 metrics_contract.py**

```python
"""lerobot-eval stdout → 平台自有指标契约 v1（spec §5.2；上游漂移只改解析器）。"""
import re

_RATE = re.compile(r"success[_ ]?rate[:=\s]+([0-9]+(?:\.[0-9]+)?)\s*%?", re.I)
_CNT = re.compile(r"\((\d+)\s*/\s*(\d+)\)", re.I)
_RET = re.compile(r"(?:mean|avg)[_ ]?(?:return|reward)[:=\s]+([-+0-9.eE]+)", re.I)
_LEN = re.compile(r"(?:mean|avg)[_ ]?ep(?:isode)[_ ]?len(?:gth)?[:=\s]+([-+0-9.eE]+)", re.I)


def parse_eval_summary(text):
    text = text or ""
    m = _RATE.search(text)
    rate = float(m.group(1)) if m else None
    if rate is not None and rate > 1:
        rate = rate / 100.0
    cnt = _CNT.search(text)
    succ = int(cnt.group(1)) if cnt else None
    ev = int(cnt.group(2)) if cnt else None
    if succ is not None and rate is None and ev:
        rate = succ / ev
    m = _RET.search(text)
    ret = float(m.group(1)) if m else None
    m = _LEN.search(text)
    elen = float(m.group(1)) if m else None
    return {"success_rate": rate, "mean_return": ret, "mean_episode_len": elen,
            "n_evaluated": ev, "n_success": succ}


def build_eval_metrics(summary, *, env, n_episodes, seed, checkpoint,
                       train_manifest_digest=None, videos=None, raw_log="eval.log"):
    return {
        "contract_version": "1",
        "source": {"type": "lerobot-eval", "env": env,
                   "n_episodes": n_episodes, "seed": seed},
        "policy_ref": {"checkpoint_path": str(checkpoint),
                       "train_manifest_digest": train_manifest_digest},
        "metrics": {k: summary.get(k) for k in
                    ("success_rate", "mean_return", "mean_episode_len",
                     "n_evaluated", "n_success")},
        "artifacts": {"videos": list(videos or []), "raw_log": raw_log},
    }
```

- [ ] **Step 4: 跑绿灯** — Expected: 4 passed
- [ ] **Step 5: Commit**

```bash
git add job-template/job/lerobot_eval/metrics_contract.py tests/test_lerobot_metrics_contract.py tests/conftest.py
git commit -m "feat(lerobot): 评测指标契约 v1 解析器"
```

---

### Task 9: F3 eval start.py（维度拦截接线 + 血缘 + EGL 探针）

**Files:**
- Create: `job-template/job/lerobot_eval/start.py`
- Create: `tests/test_lerobot_eval_start.py`

**Interfaces:**
- Consumes: Task 7 `eval_cmd`（同目录 sibling，名 `import eval_cmd as ec`）、Task 8 `metrics_contract`、Task 1 `manifest_util`
- Produces: CLI `--checkpoint --env_type --output [--n_episodes 50 --batch_size 10 --seed 100000 --video_n_episodes 3]`；退出码 2=维度错配（在任何 subprocess 之前，DRYRUN 不豁免）、3=渲染探针失败（仅真实模式）；产物 `{output}/eval_cmd.sh`、真实模式另有 `{output}/eval/eval.log`、`{output}/eval_metrics.json`；`_find_train_manifest(checkpoint)` 从 checkpoint 向上找 4 层含 `op=="lerobot-train"` 的 `manifest.json`；manifest.parents 记录其 digest

- [ ] **Step 1: 写失败测试**

`tests/test_lerobot_eval_start.py`：

```python
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
```

- [ ] **Step 2: 跑红灯** — Run: `python -m pytest tests/test_lerobot_eval_start.py -v`，Expected: 4 failed（start.py 不存在）

- [ ] **Step 3: 实现 start.py**

```python
"""lerobot-eval 入口（spec §5；维度校验在任何 subprocess 之前，DRYRUN 不豁免）。"""
import argparse
import json
import os
import pathlib
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
    (out / "eval_cmd.sh").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    mf_path, mf = _find_train_manifest(a.checkpoint)
    parents = [{"path": str(mf_path), "digest": (mf or {}).get("self_digest")}] \
        if mf else []
    train_digest = (mf or {}).get("self_digest")

    if dry:
        stats = {"dry_run": True, "eval_cmd": " ".join(cmd)}
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
        with open(eval_dir / "eval.log", "w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
        text = (eval_dir / "eval.log").read_text(encoding="utf-8")
        summary = mc.parse_eval_summary(text)
        vdir = eval_dir / "videos"
        videos = sorted(str(f.relative_to(out)) for f in vdir.glob("*.mp4")) \
            if vdir.is_dir() else []
        contract = mc.build_eval_metrics(summary, env=a.env_type,
                                         n_episodes=a.n_episodes, seed=a.seed,
                                         checkpoint=a.checkpoint,
                                         train_manifest_digest=train_digest,
                                         videos=videos)
        (out / "eval_metrics.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        stats = {"dry_run": False, "eval_cmd": " ".join(cmd),
                 "exit_code": proc.returncode, "metrics": contract["metrics"]}
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
```

- [ ] **Step 4: 跑绿灯** — Run: `python -m pytest tests/test_lerobot_eval_start.py -v`，Expected: 4 passed
- [ ] **Step 5: 全量回归** — Run: `python -m pytest tests/ -v`，Expected: 既有回归（≥36 条）+ 本计划新增全 passed
- [ ] **Step 6: Commit**

```bash
git add job-template/job/lerobot_eval/start.py tests/test_lerobot_eval_start.py
git commit -m "feat(lerobot): eval 算子入口（维度拦截/契约落盘/血缘）"
```

---

### Task 10: Dataset 登记识别（helper + view_dataset hook）

**Files:**
- Create: `myapp/utils/lerobot_dataset_meta.py`
- Modify: `myapp/views/view_dataset.py`（登记链路插 hook）
- Create: `tests/test_lerobot_dataset_meta.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: Task 4 产物 `.cube_dataset_meta`（`{"format":"lerobot","version","source","profile"}`）
- Produces: `read_cube_dataset_meta(dataset_dir) -> dict | None`；`apply_lerobot_meta(obj, dataset_dir) -> bool`（命中时设 `obj.file_type='lerobot'` 并在 `obj.describe` 前加 `[lerobot {ver} ep=N frames=M]` 标签（已有 `[lerobot` 前缀则不重复加），返回 True；未命中返回 False 不改 obj）

- [ ] **Step 1: conftest 追加 `_load_module('myapp.utils.lerobot_dataset_meta', 'myapp/utils/lerobot_dataset_meta.py')` + 写失败测试**

`tests/test_lerobot_dataset_meta.py`：

```python
import json
import types

from myapp.utils.lerobot_dataset_meta import read_cube_dataset_meta, apply_lerobot_meta


def test_read_ok(tmp_path):
    (tmp_path / ".cube_dataset_meta").write_text(
        json.dumps({"format": "lerobot", "version": "v3", "profile": {}}),
        encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path)["version"] == "v3"


def test_read_absent_bad_format_broken(tmp_path):
    assert read_cube_dataset_meta(tmp_path) is None
    (tmp_path / ".cube_dataset_meta").write_text('{"format":"other"}', encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path) is None
    (tmp_path / ".cube_dataset_meta").write_text("{broken", encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path) is None


def test_apply_mutates_obj(tmp_path):
    (tmp_path / ".cube_dataset_meta").write_text(json.dumps(
        {"format": "lerobot", "version": "v3",
         "profile": {"total_episodes": 20, "total_frames": 4000,
                     "action_dim": 2, "fps": 20}}), encoding="utf-8")
    obj = types.SimpleNamespace(file_type="parquet", describe="demo")
    assert apply_lerobot_meta(obj, tmp_path) is True
    assert obj.file_type == "lerobot"
    assert obj.describe.startswith("[lerobot v3 ep=20 frames=4000]")
    assert apply_lerobot_meta(obj, tmp_path) is True  # 幂等：不重复加标签
    assert obj.describe.count("[lerobot") == 1


def test_apply_no_meta_untouched(tmp_path):
    obj = types.SimpleNamespace(file_type="parquet", describe="d")
    assert apply_lerobot_meta(obj, tmp_path) is False
    assert obj.file_type == "parquet" and obj.describe == "d"
```

- [ ] **Step 2: 跑红灯** — Expected: ModuleNotFoundError

- [ ] **Step 3: 实现 helper**

```python
"""LeRobotDataset 目录元信息识别（spec §3.3；纯标准库，禁止 import myapp.*）。"""
import json
import pathlib

META_FILENAME = ".cube_dataset_meta"


def read_cube_dataset_meta(dataset_dir):
    p = pathlib.Path(str(dataset_dir)) / META_FILENAME
    if not p.is_file():
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return meta if isinstance(meta, dict) and meta.get("format") == "lerobot" else None


def apply_lerobot_meta(obj, dataset_dir):
    meta = read_cube_dataset_meta(dataset_dir)
    if not meta:
        return False
    prof = meta.get("profile") or {}
    tag = "[lerobot %s ep=%s frames=%s]" % (
        meta.get("version", "?"), prof.get("total_episodes", "?"),
        prof.get("total_frames", "?"))
    obj.file_type = "lerobot"
    desc = getattr(obj, "describe", "") or ""
    if not desc.startswith("[lerobot"):
        obj.describe = "%s %s" % (tag, desc)
    return True
```

- [ ] **Step 4: 跑绿灯** — Expected: 4 passed

- [ ] **Step 5: view_dataset hook 接线**

读 `myapp/views/view_dataset.py`，定位数据集新增入库位置（惯例参照：`import_from_labelstudio` 内 `Dataset(...)` 构造 + `db.session.add` 的同型路径；UI 通用新增若走基类 add，则参照该文件已有自定义 API 方法的写法在类中扩展）。在 Dataset 对象落库前（拿到最终 `path` 之后）插入固定两行：

```python
from myapp.utils.lerobot_dataset_meta import apply_lerobot_meta

apply_lerobot_meta(obj, obj.path)   # db.session.add(obj) 之前；非 lerobot 目录零影响
```

若定位到多个入库点（UI add + 自定义 API），每个落库点前都加同一行。

- [ ] **Step 6: 语法与回归验证**

Run: `python -c "import ast;ast.parse(open(r'myapp/views/view_dataset.py',encoding='utf-8').read())"` → 无输出
Run: `python -m pytest tests/ -v` → 全 passed（view 接线为薄 hook，行为覆盖在 helper 单测 + §8 手工清单）

- [ ] **Step 7: Commit**

```bash
git add myapp/utils/lerobot_dataset_meta.py myapp/views/view_dataset.py tests/test_lerobot_dataset_meta.py tests/conftest.py
git commit -m "feat(lerobot): Dataset 登记识别 .cube_dataset_meta（file_type=lerobot）"
```

---

### Task 11: 镜像与模板注册

**Files:**
- Create: `images/lerobot/Dockerfile-import`、`images/lerobot/Dockerfile-gpu`、`images/lerobot/build.sh`
- Modify: `myapp/init/init-job-template.json`（追加 3 个模板条目）

**Interfaces:**
- Consumes: Task 4/6/9 的三个 `start.py` CLI（flag 名逐字对齐，start.py 参数名用下划线：`--source_type`/`--policy_type`/`--env_type` 等）
- Produces: 模板 `lerobot-import`（project 数据导入导出）、`lerobot-train`、`lerobot-eval`（project 深度学习）；镜像引用名 `ccr.ccs.tencentyun.com/cube-studio/lerobot:import-cpu` 与 `.../lerobot:gpu-0.6.2`

- [ ] **Step 1: 实现两个 Dockerfile 与 build.sh**

`images/lerobot/Dockerfile-import`：

```dockerfile
# lerobot 数据接入轻镜像（spec §6：不装 torch，仅 parquet/json 搬运+画像+Hub 拉取）
FROM python:3.11-slim
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple
RUN pip install --no-cache-dir pyarrow pandas huggingface_hub opencv-python-headless
COPY job-template/job/lerobot_shared /opt/lerobot_shared
COPY job-template/job/lerobot_import /opt/lerobot_import
WORKDIR /opt/lerobot_import
ENTRYPOINT ["python", "start.py"]
```

`images/lerobot/Dockerfile-gpu`：

```dockerfile
# lerobot 训练/评测 GPU 镜像（spec §6：锁 0.6.2，升级走新 tag 不 in-place）
FROM nvidia/cuda:12.6.0-base-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip git ffmpeg libsdl2-dev cmake build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple \
    && pip3 install --no-cache-dir "lerobot==0.6.2" "gym-pusht" "gym-aloha" mujoco
COPY job-template/job/lerobot_shared /opt/lerobot_shared
COPY job-template/job/lerobot_train /opt/lerobot_train
COPY job-template/job/lerobot_eval /opt/lerobot_eval
ENV MUJOCO_GL=egl HF_HOME=/mnt/.cache/huggingface
```

`images/lerobot/build.sh`：

```bash
#!/bin/bash
# 从仓库根目录构建两个 lerobot 镜像（spec §6）
set -e
docker build -f images/lerobot/Dockerfile-import -t ccr.ccs.tencentyun.com/cube-studio/lerobot:import-cpu .
docker build -f images/lerobot/Dockerfile-gpu    -t ccr.ccs.tencentyun.com/cube-studio/lerobot:gpu-0.6.2 .
```

- [ ] **Step 2: 用脚本向 init-job-template.json 追加 3 条目**

手写 JSON 易错，用临时 python 脚本追加（参数 schema 字段集对齐既有 `dataset`/`pytorchjob` 条目：`choice/default/describe/editable/item_type/label/placeholder/range/require/type`；bool/int 类型用 E2 已交付的 `type: bool/int`）。创建 `images/lerobot/register_templates.py`（保留入库供异地部署复用）：

```python
"""向 init-job-template.json 追加 lerobot 三模板（幂等：已存在则跳过）。"""
import json

PATH = "myapp/init/init-job-template.json"


def arg(label, typ="str", default="", choice=None, require=0, describe="", item="str"):
    return {"choice": choice or [], "default": default, "describe": describe,
            "editable": 1, "item_type": item, "label": label,
            "placeholder": "", "range": "", "require": require, "type": typ}


def main():
    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)
    img_cpu = "ccr.ccs.tencentyun.com/cube-studio/lerobot:import-cpu"
    img_gpu = "ccr.ccs.tencentyun.com/cube-studio/lerobot:gpu-0.6.2"
    new = {
        "lerobot-import": {
            "gitpath": "/job-template/job/lerobot_import",
            "image_describe": "LeRobotDataset 接入轻镜像", "image_name": img_cpu,
            "job_template_account": "",
            "job_template_args": {"数据集接入": {
                "--source_type": arg("数据集来源", default="local_path",
                                     choice=["local_path", "hub_repo_id"], require=1,
                                     describe="local_path=共享存储目录；hub_repo_id=HuggingFace 数据集 id"),
                "--source": arg("来源路径或repo_id", default="", require=1,
                                describe="如 /data/k8s/kubeflow/global/raw/pusht_v3 或 lerobot/pusht"),
                "--target_name": arg("数据集名称", require=1, default="pusht_demo"),
                "--target_version": arg("数据集版本", default="v1"),
                "--hub_endpoint": arg("HF镜像源", describe="内网可填 https://hf-mirror.com，仅 hub 来源生效"),
                "--link_mode": arg("软链免拷贝", "bool", default="false",
                                   describe="仅 local_path 同盘生效，默认拷贝")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobotDataset 接入与画像(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-import",
            "job_template_volume": "",
            "project_name": "数据导入导出"},
        "lerobot-train": {
            "gitpath": "/job-template/job/lerobot_train",
            "image_describe": "lerobot训练镜像 0.6.2", "image_name": img_gpu,
            "job_template_account": "",
            "job_template_args": {"策略与数据": {
                "--policy_type": arg("策略类型", default="act",
                                     choice=["act", "diffusion", "vqbet", "smolvla"],
                                     require=0, describe="与加载权重二选一；smolvla 需单卡≥24G"),
                "--policy_path": arg("加载权重路径", describe="预训练/续训 checkpoint 目录或 Hub 模型 id，与策略类型互斥"),
                "--dataset_ref": arg("数据集引用", default="pusht_demo:v1", require=1,
                                     describe="已登记的 lerobot 数据集 name:version"),
                "--output": arg("输出目录", default="/mnt/{{creator}}/lerobot/train",
                                require=1)},
                "训练参数": {
                    "--batch_size": arg("batch_size", "int", default="8"),
                    "--steps": arg("训练步数", "int", default="10000"),
                    "--save_freq": arg("保存频率", "int", default="5000"),
                    "--log_freq": arg("日志频率", "int", default="200"),
                    "--lr": arg("学习率", describe="留空用策略默认，如 1e-4"),
                    "--resume": arg("断点续训", "bool", default="false"),
                    "--wandb_enable": arg("wandb记录", "bool", default="false",
                                          describe="内网建议关闭，指标落 metrics.json"),
                    "--extra_args": arg("透传参数",
                                        describe="逃生舱，仅 --flag value 偶数对，如 --policy.chunk_size 50")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobot 策略训练(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-train",
            "job_template_volume": "",
            "project_name": "深度学习"},
        "lerobot-eval": {
            "gitpath": "/job-template/job/lerobot_eval",
            "image_describe": "lerobot评测镜像 0.6.2", "image_name": img_gpu,
            "job_template_account": "",
            "job_template_args": {"仿真评测": {
                "--checkpoint": arg("checkpoint路径", require=1,
                                   describe="上游训练产物 checkpoints/{step}/pretrained_model 或 Hub 模型 id"),
                "--env_type": arg("仿真环境", default="pusht",
                                  choice=["pusht", "aloha"], require=1,
                                  describe="自定义环境名透传，预设环境启动前校验动作维度"),
                "--output": arg("输出目录", default="/mnt/{{creator}}/lerobot/eval",
                                require=1),
                "--n_episodes": arg("评测回合数", "int", default="50"),
                "--batch_size": arg("并行环境数", "int", default="10"),
                "--seed": arg("随机种子", "int", default="100000",
                              describe="同 seed 同 checkpoint 结果可复现"),
                "--video_n_episodes": arg("录视频数", "int", default="3",
                                          describe="置 0 关闭录制")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobot 仿真评测(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-eval",
            "job_template_volume": "",
            "project_name": "深度学习"},
    }
    changed = False
    for k, v in new.items():
        if k not in d:
            d[k] = v
            changed = True
    if changed:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=4)
    print("templates ready:", list(new))


if __name__ == "__main__":
    main()
```

Run: `python images/lerobot/register_templates.py`
Expected: `templates ready: ['lerobot-import', 'lerobot-train', 'lerobot-eval']`

注意：下拉选项按仓库存例用 `type: "str"` + 非空 `choice` 表达（对齐 `dataset --src_type` 条目形态，已核实）；bool/int 用 E2 已交付的 `type: bool/int`。不发明新的控件类型语义。

- [ ] **Step 3: JSON 合法与模板参数验证**

Run: `python -c "import json;d=json.load(open(r'myapp/init/init-job-template.json',encoding='utf-8'));assert all(k in d for k in ('lerobot-import','lerobot-train','lerobot-eval'));print(len(d))"`
Expected: 模板总数（112+3=115）

- [ ] **Step 4: Commit**

```bash
git add images/lerobot myapp/init/init-job-template.json
git commit -m "feat(lerobot): CPU/GPU 双镜像与三模板注册"
```

---

### Task 12: 示例 pipeline + 全量回归 + spec 回写

**Files:**
- Create: `myapp/example/pipeline/lerobot-embodied/README.md`
- Create: `myapp/example/pipeline/lerobot-embodied/lerobot-demo.json`
- Modify: `docs/superpowers/specs/2026-11-08-lerobot-embodied-training-design.md`（§4.3 实测锁定项回写实现默认值与验收归属）

**Interfaces:**
- Consumes: Task 11 的三模板名（`lerobot-import`/`lerobot-train`/`lerobot-eval`）
- Produces: 可导入的示例 pipeline JSON + 手工验收清单文档（对应 spec §8）

- [ ] **Step 1: 示例 pipeline JSON**

先读 `myapp/example/pipeline/chatglm/identity.json` 确认平台 pipeline 导出格式（dag 节点/连线字段结构），按同构格式手工组装三节点链路 `lerobot-demo.json`：节点1 `lerobot-import`（参数同 Task 11 默认值），节点2 `lerobot-train`（`dataset_ref=pusht_demo:v1`，`steps=10000`），节点3 `lerobot-eval`（`checkpoint` 引用节点2 输出目录的 `checkpoints/10000/pretrained_model` 路径串），连线 import→train→eval。**结构字段以 identity.json 为准，不发明第二套 schema。**

Run: `python -c "import json;json.load(open(r'myapp/example/pipeline/lerobot-embodied/lerobot-demo.json',encoding='utf-8'));print('ok')"` → `ok`

- [ ] **Step 2: README（手工验收清单，对应 spec §8）**

`myapp/example/pipeline/lerobot-embodied/README.md` 内写：导入方法（pipeline 页面上导入 JSON）、6 项 GPU 手工验收清单（spec §8 逐条复制），其中含一条：验证 `--dataset.repo_id local/... + --dataset.root` 形态在 lerobot 0.6.2 实镜中可离线读数据，失败则按 spec §4.3 只改 `lerobot_train_cmd.py` 一处并重跑 `python -m pytest tests/test_lerobot_train_cmd.py -v`。

- [ ] **Step 3: spec 回写**

在 spec §4.3 第一条实测锁定项末尾追加一句：`实施默认已锁定 repo_id+root 形态（lerobot_train_cmd.py 单测锁定），真机验收时确认，见 plans/2026-11-08-lerobot-embodied-training.md Task 12。`

- [ ] **Step 4: 全量回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed（既有 ≥36 条 + 本计划新增 ≥26 条）

- [ ] **Step 5: Commit**

```bash
git add myapp/example/pipeline/lerobot-embodied docs/superpowers/specs/2026-11-08-lerobot-embodied-training-design.md
git commit -m "docs(lerobot): 示例 pipeline、验收清单与 spec 实测项回写"
```
