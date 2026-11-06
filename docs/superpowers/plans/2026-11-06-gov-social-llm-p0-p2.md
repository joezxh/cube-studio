# gov-social-llm P0–P2 实物交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `gov-social-llm/` 顶层目录内交付 6 个自定义算子代码包（含 Dockerfile）、gov-manifest 血缘共享库、3 条可导入 cube-studio 的 Pipeline JSON、本地校验脚本与任务 schema/prompt 文档。

**Architecture:** 方案 A「薄算子+标准开源框架」：算子=可 build 镜像应用（入口 `python start.py --args`），平台只做调度；数据经 `/mnt/gov` JSONL 文件 + `manifest.json` 血缘传递；gov-sft/gov-kev 为 LLaMA-Factory / kev 的薄封装（本计划交付到"dry-run 命令生成正确"深度，GPU 实跑属平台侧 P4）。

**Tech Stack:** Python 3.10、pytest、requests、jsonschema（算子运行时仅标准库+requests）、Docker（CUDA 镜像分层）、cube-studio Pipeline JSON（`{pipeline, tasks}` 格式，参照 `myapp/init/init-pipeline.json` 中 deepseek 示例）。

**Spec:** `docs/superpowers/specs/2026-11-06-gov-social-llm-distill-design.md`（本计划实现其 §1.2、§2、§3.1 全部实物与 §3.5 的 P0 行）

## Global Constraints

- 所有代码位于 `gov-social-llm/`，**不得修改** cube-studio 上游任何文件（spec §1.3 原则 3）
- 算子镜像入口一律 `python start.py`；退出码 0=成功（spec §2.1）
- 数据路径以 `/mnt/gov/` 为根；Pipeline JSON 中 `volume_mount` 统一 `gov-nfs(pvc):/mnt`，`global_env` 含 `DATA_ROOT=/mnt/gov`（spec §2.3）
- 每个产出目录必须调用共享库 `gov_manifest.write_manifest` 落 `manifest.json`（spec §3.1）
- 镜像构建统一 `TORCH_CUDA_ARCH_LIST="8.9;12.0"`、CUDA≥12.8 基础镜像 tag 记录在各 Dockerfile 头部注释（spec §3.2）
- 本地测试必须跨平台（Windows 开发机 + Linux 镜像），不依赖 GPU、不依赖网络（HTTP 全部 mock）
- 提交信息中文，前缀 `feat(gov-llm)/test(gov-llm)/docs(gov-llm)/chore(gov-llm)`

## File Structure（全量清单）

```
gov-social-llm/
├── README.md                          # Task 9
├── requirements-dev.txt               # Task 1: pytest, requests, jsonschema
├── pytest.ini                         # Task 1
├── conftest.py                        # Task 1: 把 ops/*/ 与 lib 注入 sys.path
├── docs/
│   ├── task-spec/schemas/T1.json T2.json T3.json T4.json kev-questions.json   # Task 1
│   └── prompts/distill-T1-v1.md … distill-T4-v1.md judge-fact-v1.md           # Task 1
├── ops/
│   ├── gov-manifest/lib/gov_manifest/__init__.py   # Task 2（唯一被其他算子 import 的库）
│   ├── gov-manifest/{start.py,Dockerfile,requirements.txt,README.md}          # Task 2
│   ├── gov-distill-gen/{start.py,gen.py,Dockerfile,requirements.txt,README.md}# Task 3
│   ├── gov-distill-filter/{start.py,filter3.py,Dockerfile,…}                  # Task 4
│   ├── gov-eval/{start.py,metrics.py,Dockerfile,…}                            # Task 5
│   ├── gov-sft/{start.py,sft_cmd.py,Dockerfile,…}                             # Task 6
│   └── gov-kev/{start.py,kev_cmd.py,Dockerfile,…}                             # Task 7
├── serving/gov-teacher-serve/args.json               # Task 9（deploy-service 参数包）
├── pipelines/gov-p0-env-check.json                   # Task 8
├── pipelines/gov-p1-eval-build.json                  # Task 8
├── pipelines/gov-p2-distill-line.json                # Task 8
└── scripts/validate_pipelines.py                     # Task 8
tests/（与上分离，均在 gov-social-llm/tests/）
├── test_manifest.py test_distill_gen.py test_filter3.py test_metrics.py
├── test_sft_cmd.py test_kev_cmd.py test_validate_pipelines.py
└── fixtures/（小型 JSONL/prompt 样例，各 Task 自带）
```

依赖顺序：Task1 → Task2 →（Task3、Task4、Task5 可并行）→（Task6、Task7 需 Task2）→ Task8 → Task9。

---

### Task 1: 目录骨架 + 任务 schema + prompt 模板 + 测试脚手架

**Files:**
- Create: `gov-social-llm/requirements-dev.txt`、`gov-social-llm/pytest.ini`、`gov-social-llm/conftest.py`
- Create: `gov-social-llm/docs/task-spec/schemas/T1.json`、`T2.json`、`T3.json`、`T4.json`、`kev-questions.json`
- Create: `gov-social-llm/docs/prompts/distill-T1-v1.md` … `distill-T4-v1.md`、`judge-fact-v1.md`
- Test: `gov-social-llm/tests/test_schemas.py`

**Interfaces:**
- Produces: schema 文件路径常量 `DOCS_ROOT`；`kev-questions.json` 结构被 Task 4 `to_kev()` 消费；prompt 文件名模式 `distill-{task}-v{version}.md` 被 Task 3 `load_prompt()` 消费。

- [ ] **Step 1: 写失败测试** `tests/test_schemas.py`

```python
import json, pathlib, pytest
from jsonschema import Draft202012Validator

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "task-spec" / "schemas"

@pytest.mark.parametrize("name", ["T1", "T2", "T3", "T4"])
def test_schema_valid_and_example_passes(name):
    schema = json.loads((SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    example = json.loads(schema["$meta"]["example"])   # 每个 schema 内嵌一条合法示例
    Draft202012Validator(schema).validate(example)

def test_kev_questions_shape():
    q = json.loads((SCHEMA_DIR / "kev-questions.json").read_text(encoding="utf-8"))
    assert {"department", "escalate", "frustration"} <= set(q["questions"])
```

- [ ] **Step 2: 运行确认失败** — `pytest gov-social-llm/tests/test_schemas.py -v` → FAIL（文件不存在）

- [ ] **Step 3: 写 5 个 schema 文件**（要点完整，标签枚举用社会治理示例值，后续与业务方替换仅改此目录）

`T1.json`（事件/工单分类）:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$meta": {"example": "{\"label\": \"矛盾纠纷/邻里纠纷\", \"confidence\": 0.93, \"reason\": \"噪音引发的邻里矛盾\"}"},
  "type": "object",
  "required": ["label", "confidence", "reason"],
  "properties": {
    "label": {"type": "string", "pattern": "^[^/]+/[^/]+(\\|[^/]+/[^/]+)*$"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "reason": {"type": "string", "minLength": 1, "maxLength": 200}
  }
}
```
`T2.json`（风险预警）：`required=["risk_level","evidences","escalate"]`，`risk_level enum ["高","中","低"]`，`evidences` 为 1–5 条字符串数组，`escalate` boolean。
`T3.json`（调解辅助）：`required=["disputes","policy_points","suggestion"]`，`disputes`/`policy_points` 为字符串数组（≤8），`suggestion` 字符串 10–800 字。
`T4.json`（要素抽取）：`required=["entities","relations"]`；`entities` 元素 `{type enum[时间,地点,主体,行为,对象], text}`；`relations` 元素 `{head, type, tail}`。
`kev-questions.json`：
```json
{"questions": {
  "department": {"type": "choice", "instructions": "该事件应由哪个条线承办？", "criteria": {"城管执法": "市容、违建、噪音", "公安": "治安、交通、危管", "住建": "物业、房屋安全", "信访": "重复信访、跨部门", "民政": "救助、基层治理"}},
  "escalate": {"type": "noul", "instructions": "是否需要紧急人工介入（对应风险=高）？"},
  "frustration": {"type": "score", "instructions": "当事人情绪烈度？", "criteria": ["平静", "不满", "愤怒"]}
}}
```

- [ ] **Step 4: 写 5 个 prompt 模板文件**，统一结构（Task 3 按此提取 system 与 few-shot）：

`docs/prompts/distill-T1-v1.md`:
````markdown
# distill-T1-v1
## system
你是社会治理事件分类器。阅读案情后只输出 JSON，符合 schema：{"label":"一级/二级","confidence":0-1,"reason":"≤50字"}。
## fewshot
输入：楼下KTV夜间噪音反复投诉无果。
输出：{"label": "矛盾纠纷/邻里纠纷", "confidence": 0.93, "reason": "噪音引发的邻里矛盾"}
## input
{{state}}
````
`distill-T2-v1.md`（风险预警，输出 T2 schema）、`distill-T3-v1.md`（调解辅助）、`distill-T4-v1.md`（要素抽取）同构；`judge-fact-v1.md` 为事实一致性评审模板（输入案情+候选答案，输出 `{"consistent": true/false, "issue": ""}`）。

- [ ] **Step 5: 写脚手架**

`requirements-dev.txt`: `pytest>=8.0` `requests>=2.31` `jsonschema>=4.21`
`pytest.ini`: `testpaths = tests`（工作目录为 `gov-social-llm/`）
`conftest.py`:
```python
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
for p in [ROOT / "ops" / "gov-manifest" / "lib",
          ROOT / "ops" / "gov-distill-gen", ROOT / "ops" / "gov-distill-filter",
          ROOT / "ops" / "gov-eval", ROOT / "ops" / "gov-sft", ROOT / "ops" / "gov-kev",
          ROOT / "scripts"]:
    sys.path.insert(0, str(p))
```

- [ ] **Step 6: 运行通过** — `pytest gov-social-llm/tests/test_schemas.py -v` → 5 个测试 PASS

- [ ] **Step 7: Commit** — `git add gov-social-llm; git commit -m "feat(gov-llm): 目录骨架、T1-T4 schema 与蒸馏 prompt v1"`

---

### Task 2: gov-manifest 共享库 + CLI 算子（血缘核心，≈spec §3.1）

**Files:**
- Create: `ops/gov-manifest/lib/gov_manifest/__init__.py`、`ops/gov-manifest/start.py`、`ops/gov-manifest/Dockerfile`、`ops/gov-manifest/requirements.txt`（空，纯标准库）、`ops/gov-manifest/README.md`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces（其他所有算子 Task 3–7 消费的确切签名）:
  - `sha256_file(path: str|Path) -> str`（返回 `"<hex>"`，64 位小写）
  - `jsonl_stats(path) -> dict`（`{"rows": int, "sha256": str, "label_dist": {label,count}}`，行内无 `label` 则 label_dist 为空）
  - `write_manifest(out_dir, *, op: str, args: dict, parents: list[str] = [], files: list[str] = [], stats: dict = {}, extra: dict = {}) -> dict`（写 `out_dir/manifest.json`，schema 见 spec §3.1：`dataset/producer{op,image,git_commit,args}/parents[{path,digest}]/files[{path,sha256,rows}]/stats/sealed:false`；`image`/`git_commit` 从环境变量 `GOV_IMAGE`/`GOV_GIT_COMMIT` 读取，缺省 `"unknown"`）
  - `read_manifest(out_dir) -> dict | None`
  - `verify_manifest(dir_) -> tuple[bool, list[str]]`（校验：manifest 中每个 files.sha256 与现存文件一致；每个 parents 引用的 manifest 可读且其 `self_digest` 一致。manifest 写入时额外字段 `"self_digest"` = 除该字段外规范化 JSON 的 sha256）
  - `seal(dir_) -> dict`（置 `sealed=true`、重写 manifest，并对数据文件 `os.chmod(0o444)`）
- Consumes: 无（纯标准库）

- [ ] **Step 1: 写失败测试** `tests/test_manifest.py`

```python
import json, hashlib, pathlib, pytest
from gov_manifest import (sha256_file, jsonl_stats, write_manifest,
                          read_manifest, verify_manifest, seal)

def _mk_jsonl(p: pathlib.Path, rows=3):
    p.write_text("\n".join(json.dumps({"label": f"L{i%2}", "x": i}) for i in range(rows)), encoding="utf-8")

def test_sha256(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("abc", encoding="utf-8")
    assert sha256_file(f) == hashlib.sha256(b"abc").hexdigest()

def test_stats(tmp_path):
    f = tmp_path / "d.jsonl"; _mk_jsonl(f, 3)
    s = jsonl_stats(f)
    assert s["rows"] == 3 and s["label_dist"] == {"L0": 2, "L1": 1}

def test_write_read_verify(tmp_path):
    d = tmp_path / "distill/T1/v1"; d.mkdir(parents=True)
    _mk_jsonl(d / "train.jsonl")
    m = write_manifest(d, op="gov-test", args={"--x": 1}, files=["train.jsonl"],
                       stats={"rows": 3})
    assert m["sealed"] is False and read_manifest(d)["producer"]["op"] == "gov-test"
    ok, problems = verify_manifest(d); assert ok, problems
    (d / "train.jsonl").write_text("tampered", encoding="utf-8")
    ok, problems = verify_manifest(d); assert not ok and any("train.jsonl" in p for p in problems)

def test_parent_lineage_and_seal(tmp_path):
    parent = tmp_path / "seeds/T1/v1"; parent.mkdir(parents=True); _mk_jsonl(parent / "s.jsonl", 2)
    write_manifest(parent, op="gov-x", args={}, files=["s.jsonl"])
    child = tmp_path / "distill/T1/v1"; child.mkdir(parents=True); _mk_jsonl(child / "c.jsonl")
    pref = {"path": str(parent / "manifest.json"),
            "digest": read_manifest(parent)["self_digest"]}
    write_manifest(child, op="gov-y", args={}, files=["c.jsonl"], parents=[pref])
    ok, problems = verify_manifest(child); assert ok, problems
    seal(parent)
    assert read_manifest(parent)["sealed"] is True
    assert not (parent / "s.jsonl").is_dir()   # 文件仍存在，仅只读

def test_sealed_detect_in_verify(tmp_path):
    d = tmp_path / "ds"; d.mkdir(); _mk_jsonl(d / "a.jsonl")
    write_manifest(d, op="o", args={}, files=["a.jsonl"]); seal(d)
    ok, problems = verify_manifest(d)          # seal 后 self_digest 已更新，仍应通过
    assert ok, problems
```

- [ ] **Step 2: 运行** — `pytest gov-social-llm/tests/test_manifest.py -v` → FAIL（模块不存在）

- [ ] **Step 3: 实现 `gov_manifest/__init__.py`**（要点）:

```python
import hashlib, json, os, stat, pathlib, datetime

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def jsonl_stats(path):
    rows, labels = 0, {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows += 1
        lbl = json.loads(line).get("label")
        if lbl is not None:
            labels[str(lbl)] = labels.get(str(lbl), 0) + 1
    return {"rows": rows, "sha256": sha256_file(path), "label_dist": labels}

def _canon(m):
    return json.dumps({k: v for k, v in m.items() if k != "self_digest"},
                      sort_keys=True, ensure_ascii=False).encode("utf-8")

def write_manifest(out_dir, *, op, args, parents=(), files=(), stats=None, extra=None):
    d = pathlib.Path(out_dir); d.mkdir(parents=True, exist_ok=True)
    m = {"dataset": str(out_dir).replace("\\", "/"),
         "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "producer": {"op": op, "image": os.environ.get("GOV_IMAGE", "unknown"),
                      "git_commit": os.environ.get("GOV_GIT_COMMIT", "unknown"), "args": args},
         "parents": list(parents),
         "files": [{"path": f, **jsonl_stats(d / f)} for f in files],
         "stats": stats or {}, "sealed": False}
    m.update(extra or {})
    m["self_digest"] = hashlib.sha256(_canon(m)).hexdigest()
    (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m

def read_manifest(dir_):
    p = pathlib.Path(dir_) / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def verify_manifest(dir_):
    m = read_manifest(dir_); problems = []
    if m is None:
        return False, [f"{dir_}: manifest.json 缺失"]
    if hashlib.sha256(_canon(m)).hexdigest() != m.get("self_digest"):
        problems.append(f"{dir_}: manifest 自身被篡改")
    d = pathlib.Path(dir_)
    for f in m.get("files", []):
        p = d / f["path"]
        if not p.exists():
            problems.append(f"{f['path']}: 文件缺失")
        elif sha256_file(p) != f["sha256"]:
            problems.append(f"{f['path']}: 内容漂移(sha256 不一致)")
    for pr in m.get("parents", []):
        pm = read_manifest(pathlib.Path(pr["path"]).parent)
        if pm is None or pm.get("self_digest") != pr["digest"]:
            problems.append(f"parent {pr['path']}: 上游血缘断裂")
    return (not problems), problems

def seal(dir_):
    m = read_manifest(dir_); d = pathlib.Path(dir_)
    m["sealed"] = True
    for f in m.get("files", []):
        p = d / f["path"]
        if p.exists():
            p.chmod(stat.S_IREAD)
    m.pop("self_digest", None)
    m["self_digest"] = hashlib.sha256(_canon(m)).hexdigest()
    (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "manifest.json").chmod(stat.S_IREAD)
    return m
```

- [ ] **Step 4: 运行通过** — `pytest gov-social-llm/tests/test_manifest.py -v` → 5 PASS

- [ ] **Step 5: 写 CLI `start.py`**（argparse 子命令 `generate <dir> --files a.jsonl --op NAME` / `verify <dir> --parents ...` / `seal <dir>`；失败 exit 2 并打印 problems）与 **Dockerfile**：

```dockerfile
# 纯 CPU 算子；python:3.10-slim（无 CUDA 需求）
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENTRYPOINT ["python", "start.py"]
```

- [ ] **Step 6: 手工冒烟** — `python gov-social-llm/ops/gov-manifest/start.py verify gov-social-llm/tests/tmp_manual` 输出可读（无 traceback）；删除临时目录

- [ ] **Step 7: Commit** — `git commit -am "feat(gov-llm): gov-manifest 血缘库与 CLI（digest/verify/seal）"`

---

### Task 3: gov-distill-gen 蒸馏生成算子

**Files:**
- Create: `ops/gov-distill-gen/{gen.py,start.py,Dockerfile,requirements.txt(requests),README.md}`
- Test: `tests/test_distill_gen.py`、`tests/fixtures/seeds_mini.jsonl`（3 行：`{"seed_id":"s1","task":"T1","state":"楼下KTV夜间噪音..."}`）

**Interfaces:**
- Consumes: Task 1 的 prompt 文件名模式与 `{{state}}` 占位；Task 2 `write_manifest`
- Produces: `load_prompt(docs_dir, task, version) -> dict{system, fewshot, tail}`；`build_messages(prompt, state) -> list[dict]`；`call_teacher(endpoint, model, messages, *, temperature, top_p, max_tokens, timeout=60, retries=3) -> str`（OpenAI `/v1/chat/completions`）；`gen_batch(seeds, prompt, endpoint, model, n_candidates, temperature, top_p, max_tokens, out_path, resume=True, concurrency=4) -> int`；raw.jsonl 行结构 `{"seed_id","task","prompt_version","candidate_id","messages","output","meta":{"temperature","top_p","max_tokens","endpoint","ts"}}`

- [ ] **Step 1: 写失败测试**（HTTP 用 monkeypatch 假 `requests.post`，含重试与断点用例）

```python
import json, pathlib, pytest
import gen

class FakeResp:
    def __init__(self, payload, status=200): self._p, self.status_code = payload, status
    def raise_for_status(self):
        if self.status_code != 200: raise RuntimeError(self.status_code)
    def json(self): return self._p

@pytest.fixture
def prompt_dict(tmp_path):
    f = tmp_path / "distill-T1-v1.md"
    f.write_text("# x\n## system\nSYS\n## fewshot\nFS\n## input\n{{state}}", encoding="utf-8")
    return gen.load_prompt(tmp_path, "T1", "v1")

def test_load_build(prompt_dict):
    assert prompt_dict["system"] == "SYS"
    msgs = gen.build_messages(prompt_dict, "案情ABC")
    assert msgs[-1]["content"].endswith("案情ABC")

def test_gen_batch_writes_all_candidates(tmp_path, prompt_dict, monkeypatch):
    calls = []
    def fake_post(url, **kw):
        calls.append(kw["json"])
        return FakeResp({"choices": [{"message": {"content": '{"label":"矛盾纠纷/邻里纠纷"}'} }]})
    monkeypatch.setattr(gen.requests, "post", fake_post)
    seeds = [{"seed_id": f"s{i}", "task": "T1", "state": "x"} for i in range(2)]
    out = tmp_path / "raw.jsonl"
    n = gen.gen_batch(seeds, prompt_dict, "http://t/v1/chat/completions", "m",
                      2, 0.7, 0.95, 512, out)
    assert n == 4 and len(out.read_text(encoding="utf-8").splitlines()) == 4

def test_resume_skips_done(tmp_path, prompt_dict, monkeypatch):
    monkeypatch.setattr(gen.requests, "post",
                        lambda url, **kw: FakeResp({"choices": [{"message": {"content": "y"}}]}))
    out = tmp_path / "raw.jsonl"
    out.write_text(json.dumps({"seed_id": "s0", "candidate_id": 0}) + "\n", encoding="utf-8")
    seeds = [{"seed_id": "s0", "task": "T1", "state": "x"}]
    assert gen.gen_batch(seeds, prompt_dict, "http://t/v1", "m", 1, 0.7, 0.95, 512, out) == 0

def test_retry_then_fail(monkeypatch):
    state = {"n": 0}
    def flaky(url, **kw):
        state["n"] += 1
        return FakeResp({}, status=500)
    monkeypatch.setattr(gen.requests, "post", flaky)
    with pytest.raises(RuntimeError):
        gen.call_teacher("http://t/v1", "m", [{"role": "user", "content": "x"}],
                         temperature=0.7, top_p=0.95, max_tokens=8, retries=2)
    assert state["n"] == 3   # 1+2 次重试
```

- [ ] **Step 2: 运行** → FAIL（`No module named gen`）

- [ ] **Step 3: 实现 `gen.py`**：`load_prompt` 按 `## system/## fewshot/## input` 分节解析；`call_teacher` 循环 `retries+1` 次请求 `{"model","messages","temperature","top_p","max_tokens"}`；`gen_batch` 用 `concurrent.futures.ThreadPoolExecutor(concurrency)`，resume 读已有 out 的 `(seed_id,candidate_id)` 集合跳过；每行 flush 落盘（断点安全）。实现 `start.py`：argparse 全部参数（spec §2.2 表）→ 调用 → `gen_report.json`（成功/失败种子计数）→ `write_manifest(..., op="gov-distill-gen", files=["raw.jsonl","gen_report.json"], parents=[seed manifest 引用], stats={total_rows})`；教师 5xx 超过重试的种子记入 `gen_report.failed[]` 不中断整体。

- [ ] **Step 4: 运行通过** → 4 PASS

- [ ] **Step 5: Dockerfile**（`FROM python:3.10-slim`，同 Task 2 骨架；README 记录注册为平台算子后的示例 args）

- [ ] **Step 6: Commit** — `"feat(gov-llm): gov-distill-gen 教师蒸馏批量生成算子(限流/断点续跑)"`

---

### Task 4: gov-distill-filter 三闸过滤算子

**Files:**
- Create: `ops/gov-distill-filter/{filter3.py,start.py,Dockerfile,requirements.txt(jsonschema,requests不需要),README.md}`
- Test: `tests/test_filter3.py`、`tests/fixtures/raw_mini.jsonl`（6 行：3 候选×2 种子，其中 1 行格式非法、1 对种子投票分歧）

**Interfaces:**
- Consumes: Task 1 schema 文件、`kev-questions.json`；Task 2 `write_manifest`
- Produces: `parse_output(text) -> dict|None`；`gate_format(rows, schema) -> (ok_rows, dropped)`；`gate_consistency(ok_rows, k=2) -> (ok_rows, dropped)`（同 `seed_id` 候选按 `label` 众数 ≥k 票保留，T3/T4 无 label 时按 schema 全字段等值）；`gate_rules(row, max_len=4096) -> bool`（长度、重复片段 >30%、控制字符）；`to_alpaca/to_sharegpt/to_kev(row, kev_q)`；输出三文件 + `filter_report.json` `{"gate1_pass":n,"gate2_pass":n,"gate3_pass":n,"label_dist":{},"pass_rate":f}`

- [ ] **Step 1: 写失败测试**

```python
import json, pathlib, pytest
import filter3

SCHEMA = {"type": "object", "required": ["label"], "properties": {"label": {"type": "string"}}}
KEV_Q = json.loads((pathlib.Path(__file__).parents[1] / "docs/task-spec/schemas/kev-questions.json").read_text(encoding="utf-8"))

def _row(sid, cid, out, state="s"):
    return {"seed_id": sid, "candidate_id": cid, "task": "T1", "state": state,
            "output": out, "messages": [{"role": "user", "content": state}]}

def test_gates():
    rows = [_row("a", 0, '{"label":"x"}'), _row("a", 1, '{"label":"x"}'), _row("a", 2, '坏格式'),
            _row("b", 0, '{"label":"y"}'), _row("b", 1, '{"label":"z"}'), _row("b", 2, '{"label":"z"}')]
    ok1, d1 = filter3.gate_format(rows, SCHEMA); assert len(ok1) == 5 and len(d1) == 1
    ok2, d2 = filter3.gate_consistency(ok1, k=2); assert {r["seed_id"] for r in ok2} == {"a", "b"}
    assert filter3.gate_rules(_row("c", 0, '{"label":"x"}')) is True
    assert filter3.gate_rules(_row("c", 0, '{"label":"' + "啊" * 5000 + '"}')) is False

def test_outputs_three_formats(tmp_path):
    rows = [_row("a", 0, '{"label":"x"}')]
    alp = tmp_path / "train_alpaca.jsonl"; sg = tmp_path / "train_sharegpt.jsonl"; kv = tmp_path / "kev_format.jsonl"
    filter3.dump(rows, alp, sg, kv, KEV_Q)
    a = json.loads(alp.read_text(encoding="utf-8").splitlines()[0])
    assert {"instruction", "input", "output"} <= set(a)
    k = json.loads(kv.read_text(encoding="utf-8").splitlines()[0])
    assert k["state"] == "s" and set(k["questions"]) == {"department", "escalate", "frustration"}
```

- [ ] **Step 2: 运行** → FAIL

- [ ] **Step 3: 实现 `filter3.py`**：`parse_output` 剥离 ```json 围栏后 `json.loads`；三闸与导出函数按上述签名（alpaca 行 `{"instruction":messages[0].content,"input":state,"output":json字符串}`；sharegpt 行 `{"conversations":[{"from":"human","value":...},{"from":"gpt","value":...}]}`；kev 行 `{"state","questions":KEV_Q["questions"],"answers":{"department":label 映射,"escalate":false,"frustration":"平静"}}`——label→department 的映射表从 `docs/task-spec/kev-mapping.md` 的 JSON 块读取，本任务先在 `docs/task-spec/` 建 `kev-mapping.json`：`{"矛盾纠纷/邻里纠纷":"城管执法","治安":"公安"}` 示例两行并在 README 标注"待业务方补全"）；`start.py` 汇总三闸产出 `filter_report.json` + `write_manifest`（parents 引用 raw manifest）。

- [ ] **Step 4: 运行通过** → 2 PASS

- [ ] **Step 5: Commit** — `"feat(gov-llm): gov-distill-filter 三闸过滤与 alpaca/sharegpt/kev 三格式导出"`

---

### Task 5: gov-eval 评测算子（指标核心实装 + 服务模式骨架）

**Files:**
- Create: `ops/gov-eval/{metrics.py,start.py,Dockerfile,requirements.txt(requests),README.md}`
- Test: `tests/test_metrics.py`、`tests/fixtures/gold_mini.jsonl`（8 行 `{"id","label","risk"}`）、`tests/fixtures/pred_mini.jsonl`

**Interfaces:**
- Consumes: Task 2 `write_manifest`
- Produces: `macro_f1(y_true, y_pred) -> float`；`precision_recall(y_true, y_pred, pos) -> (p, r)`；`high_risk_recall(gold, pred) -> float`（risk=="高" 召回）；`format_compliance(pred_rows, schema) -> float`；`refusal_rate(pred_rows) -> float`（`output` 含 `"无法回答"` 计数）；`redteam_violation(rows) -> float`；`load_jsonl(path) -> list[dict]`；`score_all(gold, pred, *, schema, risk_pos="高") -> dict`（汇总以上为 metrics.json 结构：`{"macro_f1","per_class_p","per_class_r","high_risk_recall","false_alarm_rate","format_compliance","refusal_rate"}`）

- [ ] **Step 1: 写失败测试**

```python
import filter3  # 复用 parse
from metrics import macro_f1, high_risk_recall, score_all, format_compliance, refusal_rate

def test_macro_f1_perfect_and_skewed():
    assert macro_f1(["A", "B", "A"], ["A", "B", "A"]) == 1.0
    # B 类 F1=0，A 类 F1=1 → macro=0.5
    assert abs(macro_f1(["A","A","B"], ["A","A","A"]) - 0.5) < 1e-9

def test_high_risk_recall_and_false_alarm():
    gold = [{"id": 1, "risk": "高"}, {"id": 2, "risk": "高"}, {"id": 3, "risk": "低"}]
    pred = [{"id": 1, "risk": "高"}, {"id": 2, "risk": "中"}, {"id": 3, "risk": "高"}]
    assert abs(high_risk_recall(gold, pred) - 0.5) < 1e-9
    m = score_all(gold, pred, schema=None, risk_pos="高")
    assert m["false_alarm_rate"] == 1/3

def test_format_and_refusal():
    rows = [{"output": '{"label":"x"}'}, {"output": "坏"}, {"output": "无法回答该问题"}]
    assert format_compliance(rows, {"type": "object", "required": ["label"]}) == 0.5
    assert refusal_rate(rows) == 1/3
```

- [ ] **Step 2: 运行** → FAIL

- [ ] **Step 3: 实现 `metrics.py`**：纯函数按签名实现（`macro_f1` 对每类算 P=R=TP/(TP+FP)、TP/(TP+FN) 后取 F1 平均）。`start.py` 五模式：`--mode smoke`（`load_jsonl(--eval-set)` 前 10 条逐条调 `--endpoint` chat/completions，输出可解析率）；`dev/blind`（gold vs 模型输出跑 `score_all` + `--redteam` 违规率 + `--judge` 可选事实一致性抽检 20 条）；`safety`（仅红队集）；`bench`（`--endpoint` 上并发 `--concurrency 20` 压测 P50/P95——本任务实现为 `time.perf_counter` 简单统计，不做流式 token 计量）。**blind 留痕**：`--eval-set` 路径含 `/blind/` 时，`write_manifest` 的 `stats` 增加 `"blind_touched_at": <utc iso>`。输出 `metrics.json` + `report.md`。

- [ ] **Step 4: 运行通过** → 3 PASS

- [ ] **Step 5: Commit** — `"feat(gov-llm): gov-eval 指标核心(smoke/dev/blind/safety/bench)"`

---

### Task 6: gov-sft 封装算子（LLaMA-Factory 命令生成 + train_manifest）

**Files:**
- Create: `ops/gov-sft/{sft_cmd.py,start.py,Dockerfile,requirements.txt,README.md}`
- Test: `tests/test_sft_cmd.py`

**Interfaces:**
- Consumes: Task 2 `write_manifest`（写 `train_manifest.json`：parents=[数据集 manifest 引用]，`extra={"hyper":..., "base_sha256":...}`）
- Produces: `build_dataset_info(dataset_path: str, name: str) -> dict`（LLaMA-Factory `dataset_info.json` 条目：sharegpt 用 `{"formatting":"sharegpt","columns":{"messages":"conversations"}}`；alpaca 用 `"formatting":"alpaca"` 三列映射）；`build_train_cmd(*, method, base, dataset_name, lora_r, lr, epochs, seq_len, output, deepspeed=None) -> list[str]`；`merge_cmd(base, adapter, output) -> list[str]`

- [ ] **Step 1: 写失败测试**

```python
from sft_cmd import build_dataset_info, build_train_cmd, merge_cmd

def test_dataset_info_both_formats():
    assert build_dataset_info("/d/train_sharegpt.jsonl", "gov")["gov"]["formatting"] == "sharegpt"
    assert build_dataset_info("/d/train_alpaca.jsonl", "gov")["gov"]["file_name"] == "/d/train_alpaca.jsonl"

def test_lora_cmd_contains_core_flags():
    cmd = build_train_cmd(method="lora", base="/m/Qwen3.8-1.7B", dataset_name="gov",
                          lora_r=32, lr="1e-4", epochs=3, seq_len=4096, output="/o/v1")
    s = " ".join(cmd)
    assert "llama-cli" in s or "train" in s
    for flag in ["--model_name_or_path /m/Qwen3.8-1.7B", "--lora_rank 32",
                 "--learning_rate 1e-4", "--num_train_epochs 3", "--cutoff_len 4096",
                 "--output_dir /o/v1", "--template default"]:
        assert flag in s, flag

def test_qlora_adds_quantization():
    cmd = build_train_cmd(method="qlora", base="/b", dataset_name="g", lora_r=16,
                          lr="1e-4", epochs=2, seq_len=2048, output="/o")
    assert "--quantization_bit 4" in cmd

def test_merge_cmd():
    assert merge_cmd("/b", "/o/v1", "/o/v1-merged")[-1] == "--export_dir /o/v1-merged"
```

- [ ] **Step 2: 运行** → FAIL

- [ ] **Step 3: 实现 `sft_cmd.py`**（`build_train_cmd` 返回 `["llama-cli","train","--model_name_or_path",base,"--stage","sft","--do_train","--dataset",dataset_name,"--template","default","--finetuning_type", "lora"/"qlora"→"lora", …按测试逐参数产出]`）；`start.py`：解析 spec §2.2 参数 → 写 `dataset_info.json` 到 output → 打印并将 `build_train_cmd` 结果经 `subprocess.run` 执行（**环境变量 `GOV_SFT_DRYRUN=1` 时跳过 subprocess，仅将命令写入 `output/train_cmd.sh` 并照常 write_manifest**——P4 平台实跑时用真实模式）；训练后若 `--merge` 则执行 `merge_cmd`。

- [ ] **Step 4: 运行通过** → 4 PASS

- [ ] **Step 5: Dockerfile**（要点，注释记录版本决策）:
```dockerfile
# 基础=LLaMA-Factory 官方镜像（开源），CUDA≥12.8 支持 sm_89/sm_120；
# 教师/底座权重不打入镜像，运行时从 /mnt/gov/models 挂载读取（spec §3.4 选型规则：权重定版入就绪单）
FROM hiyouga/llamafactory:latest
WORKDIR /app
COPY . .
ENTRYPOINT ["python", "start.py"]
```

- [ ] **Step 6: Commit** — `"feat(gov-llm): gov-sft LLaMA-Factory 封装与 train_manifest 血缘"`

---

### Task 7: gov-kev 封装算子（kev.train/kev.serve 命令生成）

**Files:**
- Create: `ops/gov-kev/{kev_cmd.py,start.py,Dockerfile,requirements.txt,README.md}`
- Test: `tests/test_kev_cmd.py`

**Interfaces:**
- Consumes: Task 4 产出的 `kev_format.jsonl`；Task 2 `write_manifest`
- Produces: `build_kev_train_cmd(*, data, base, init_from, epochs, lr, batch, accum, output) -> list[str]`（`python -m kev.train --data … --base … --init_from … --epochs 2 --lr 2e-5 --batch 1 --accum 8 --output_dir …`）；`build_kev_serve_cmd(run, port=8009) -> list[str]`（`uv run --extra serve python -m kev.serve --run <ckpt|jaredpalmer/kev-0.8b> --port 8009`）

- [ ] **Step 1: 写失败测试**

```python
from kev_cmd import build_kev_train_cmd, build_kev_serve_cmd

def test_train_cmd():
    cmd = build_kev_train_cmd(data="/d/kev.jsonl", base="Qwen3.5-0.8B", init_from="jaredpalmer/kev-0.8b",
                              epochs=2, lr="2e-5", batch=1, accum=8, output="/o/kev-v1")
    s = " ".join(cmd)
    assert "kev.train" in s and "--init_from jaredpalmer/kev-0.8b" in s and "--output_dir /o/kev-v1" in s

def test_serve_cmd_systemone():
    cmd = build_kev_serve_cmd("/o/kev-v1", port=8009)
    assert "kev.serve" in cmd and "--port 8009" in cmd and "--run /o/kev-v1" in cmd
```

- [ ] **Step 2: 运行** → FAIL；**Step 3: 实现**（同上两个纯函数 + `start.py`：dry-run 环境变量 `GOV_KEV_DRYRUN=1` 写 `train_cmd.sh`，真实模式 `subprocess`；完成后 `write_manifest(op="gov-kev", extra={"hyper":..., "license":"Apache-2.0"})`）

- [ ] **Step 4: 运行通过** → 2 PASS

- [ ] **Step 5: Dockerfile**：
```dockerfile
# kev 上游 Apache-2.0；镜像构建期 clone 并 uv sync 锁定依赖（P0 验证内网可达 github/PyPI）
FROM python:3.11-slim
RUN pip install uv
WORKDIR /work
RUN git clone --depth 1 https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
COPY . /app
ENTRYPOINT ["uv", "run", "--project", "/work/kev", "python", "/app/start.py"]
```
README 注明：指针头不受 LLaMA-Factory 支持、不可用 gov-sft 替代（spec §3.4 约束提醒）。

- [ ] **Step 6: Commit** — `"feat(gov-llm): gov-kev 封装(kev.train/kev.serve 命令生成)"`

---

### Task 8: 三条 Pipeline JSON + validate_pipelines 校验脚本

**Files:**
- Create: `pipelines/gov-p0-env-check.json`、`pipelines/gov-p1-eval-build.json`、`pipelines/gov-p2-distill-line.json`
- Create: `scripts/validate_pipelines.py`
- Test: `tests/test_validate_pipelines.py`

**Interfaces:**
- Consumes: Task 3–7 算子名（注册后 `job_templete` 值：`gov-distill-gen`/`gov-distill-filter`/`gov-eval`/`gov-manifest`/`deploy-service`/`dataset`/`python`/`nlp-replace-private-data`/`nlp-clean-data`/`nlp-filter-data`）
- Produces: `validate(doc: dict) -> list[str]`（问题列表，空=合法）；CLI：无参=校验 `pipelines/*.json` 全部

`validate` 规则（每条都要实现，测试逐条覆盖）：
1. 顶层含 `pipeline`、`tasks`；`pipeline` 含 spec §2.3 的 7 键（`name,describe,project,parameter,dag_json,global_env,expand`）
2. 每个 task 含 8 键（`job_templete,name,label,volume_mount,resource_memory,resource_cpu,resource_gpu,args`）；task name 唯一
3. `args` 所有键以 `--` 开头
4. `dag_json` 键集合 == task 名集合；每个 `upstream` 引用存在的 task 名
5. DAG 无环（Kahn 拓扑排序）
6. `expand` 的 `id` 集合 == task 名集合
7. `volume_mount` 匹配正则 `^[\w\-.]+\((pvc|hostPath|memory)\):/.+`；资源串匹配 `^\d+G$` / cpu `^\d+$` / gpu `^\d+(\.\d+)?$`
8. `global_env` 包含 `DATA_ROOT=/mnt/gov`

- [ ] **Step 1: 写失败测试**（构造合法最小文档 + 7 种违规变体，逐一断言 `validate` 返回对应关键词；再加载 `pipelines/` 三个真实文件断言 `validate(doc) == []`）

```python
import json, pathlib, copy, pytest
from validate_pipelines import validate

GOOD = {  # 合法双节点样例（规则各分支测试的基座）
  "pipeline": {"name": "p", "describe": "d", "project": "社会治理",
    "parameter": {}, "dag_json": {"b": {"upstream": ["a"]}}, "global_env": "DATA_ROOT=/mnt/gov",
    "expand": [{"id": "a", "type": "dataSet", "position": {"x": 0, "y": 0}, "data": {"name": "a", "label": "A"}},
               {"id": "b", "type": "dataSet", "position": {"x": 1, "y": 0}, "data": {"name": "b", "label": "B"}}]},
  "tasks": [{"job_templete": "gov-eval", "name": "a", "label": "A", "volume_mount": "gov-nfs(pvc):/mnt",
             "resource_memory": "4G", "resource_cpu": "2", "resource_gpu": "0", "args": {"--mode": "smoke"}},
            {"job_templete": "gov-manifest", "name": "b", "label": "B", "volume_mount": "gov-nfs(pvc):/mnt",
             "resource_memory": "2G", "resource_cpu": "1", "resource_gpu": "0", "args": {"verify": ""}}]}

@pytest.mark.parametrize("mutate,keyword", [
  (lambda d: d["tasks"][0]["args"].update({"mode": "x"}), "args"),
  (lambda d: d["tasks"].pop(1), "dag_json"),
  (lambda d: d["pipeline"]["dag_json"]["a"].update({"upstream": ["ghost"]}), "ghost"),
  (lambda d: (d["pipeline"]["dag_json"]["a"].update({"upstream": ["b"]}),
              d["pipeline"]["dag_json"]["b"].update({"upstream": ["a"]}))), "环"),
  (lambda d: d["tasks"][0].__setitem__("volume_mount", "bad-mount"), "volume_mount"),
  (lambda d: d["pipeline"].__setitem__("global_env", "X=1"), "DATA_ROOT"),
  (lambda d: d["pipeline"]["expand"].pop(1), "expand"),
])
def test_rules(mutate, keyword):
    d = copy.deepcopy(GOOD); mutate(d)
    assert any(keyword in p for p in validate(d)), validate(d)

@pytest.mark.parametrize("f", ["gov-p0-env-check.json", "gov-p1-eval-build.json", "gov-p2-distill-line.json"])
def test_real_pipelines_valid(f):
    doc = json.loads((pathlib.Path(__file__).parents[1] / "pipelines" / f).read_text(encoding="utf-8"))
    assert validate(doc) == []
```

- [ ] **Step 2: 运行** → FAIL

- [ ] **Step 3: 实现 `validate_pipelines.py`**（按 8 条规则；规则 4 的 DAG 键==task 名集合在 `tasks.pop` 场景自然报 `dag_json` 不一致；CLI `main()`：`glob(pipelines/*.json)` 逐档打印问题并 exit 1）

- [ ] **Step 4: 编写三条 Pipeline JSON**（结构与 `myapp/init/init-pipeline.json` deepseek 条目逐字段同构；args 为 `{"--flag": "value"}`，路径值用 `/mnt/gov/...` 字面量，`expand` 的 position 按 DAG 从左到右 x=200 递增、y 分层）。内容对齐 spec §2.3：
  - **gov-p0-env-check**：`env-selfcheck`(python 算子: `{"--command": "nvidia-smi; df -h /mnt; python -c \"import torch;print(torch.version.cuda)"}`) → `serve-teacher`(deploy-service: `{"--service_type": "serving", "--images": "…/gov-teacher-serve:v1", "--command": "python3 -m vllm.entrypoints.openai.api_server --model /mnt/gov/models/Qwen3.8-27B-AWQ --quantization awq --max-model-len 8192 --gpu-memory-utilization 0.85 --port 8000", "--port": "8000", "--health_port": "8000", "--health_pattern": "/health", "--resource": "1"}`) → `smoke-eval`(gov-eval `--mode smoke --eval-set /mnt/gov/eval/smoke/v1/smoke.jsonl --endpoint http://serve-teacher-svc:8000/v1`)
  - **gov-p1-eval-build**：`import-eval`(dataset) → `mask-eval`(nlp-replace-private-data) → `split-eval`(python: eval-split 脚本入 `scripts/eval_split.py`，本步一并创建，argparse `--input --dev-out --blind-out --redteam-out --ratio 0.7 --seed 42`) → `seal-blind`(gov-manifest `--cmd seal --dir /mnt/gov/eval/blind/v1`)
  - **gov-p2-distill-line**：`import-seeds`(dataset) → `clean-seeds`(nlp-clean-data) → `filter-seeds`(nlp-filter-data `--max 500`) → `teacher-probe`(gov-eval dev 模式, 闸门说明写入 task label) → `distill-gen`(gov-distill-gen) → `distill-filter`(gov-distill-filter) → `manifest-set`(gov-manifest generate)；DAG 链式 upstream 逐级声明

- [ ] **Step 5: 运行通过** — `pytest gov-social-llm/tests/test_validate_pipelines.py -v` → 10 PASS（7 项违规变体 + 3 个真实 Pipeline 文件）

- [ ] **Step 6: Commit** — `"feat(gov-llm): P0-P2 三条 Pipeline JSON 与格式校验器"`

---

### Task 9: 教师服务参数包 + README 运行手册 + 全量回归

**Files:**
- Create: `serving/gov-teacher-serve/args.json`（deploy-service 参数模板，含 4090/5090 两套 `--gpu-memory-utilization`/`max-num-seqs` 取值与注释）
- Create: `gov-social-llm/README.md`
- Modify: 无
- Test: 全量套件

- [ ] **Step 1: args.json**：
```json
{
  "service_type": "serving",
  "images": "REGISTRY/gov-teacher-serve:v0.1.0",
  "command": "python3 -m vllm.entrypoints.openai.api_server --model /mnt/gov/models/Qwen3.8-27B-AWQ --quantization awq --max-model-len 8192 --port 8000",
  "port": "8000", "health_port": "8000", "health_pattern": "/health",
  "env_var": "VLLM_WORKER_MULTIPROC_METHOD=spawn",
  "presets": {
    "2x4090-48G":  {"extra_args": "--gpu-memory-utilization 0.90 --max-num-seqs 32"},
    "2x5090-32G":  {"extra_args": "--gpu-memory-utilization 0.85 --max-num-seqs 16"}
  }
}
```

- [ ] **Step 2: README.md**（五节：①目录导览 ②P0 操作手册——6 算子 `docker build`→推 registry→平台「镜像管理」登记→「模板自定义」注册算子（参数类型对照 spec §2.2）→`pipelines/*.json` 在 Pipeline 页导入 ③数据目录规范（/mnt/gov 四子树+manifest）④两套 GPU 环境差异表（引 spec §3.2）⑤本地开发：`pip install -r requirements-dev.txt && pytest`）

- [ ] **Step 3: 全量回归** — `pytest gov-social-llm/tests -v` → 全部 PASS（约 24 项）；`python gov-social-llm/scripts/validate_pipelines.py` → exit 0

- [ ] **Step 4: Commit** — `"docs(gov-llm): 教师服务参数包与 P0 运行手册"`

---

## Self-Review 结论（已执行）

1. **规格覆盖**：spec §1.2 全部文件 ↔ Task 1–9；§2.2 算子参数 ↔ Task 3–7 argparse（dry-run 边界在 Task 6/7 明确）；§2.3 三条线 ↔ Task 8；§3.1 血缘 ↔ Task 2；§3.2 双环境 ↔ Global Constraints + Task 9 presets；§3.4 kev 映射 ↔ Task 1 kev-questions + Task 4 kev_format + Task 7。**P4 实跑、P5 量化、P6 部署不在本计划**（规格定义为设计稿深度）。
2. **占位符**：无 TBD；kev-mapping.json 的示例映射行显式标注"待业务方补全"，属规格中已声明的人工确认项而非计划缺口。
3. **类型一致性**：`write_manifest(out_dir, *, op, args, parents, files, stats, extra)` 签名在 Task 2 定义、Task 3–7 引用一致；`raw.jsonl` 行字段（Task 3 产出）与 Task 4 `gate_*` 输入一致；`validate(doc)->list[str]` 与测试消费一致。Task 5 测试中 `score_all(gold, pred, schema=None, risk_pos=...)` 要求 `schema=None` 时跳过 format 检查——实现时注意。
