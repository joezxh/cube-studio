"""Pipeline JSON 格式校验器（计划 Task 8 / spec §2.3）。

`validate(doc) -> list[str]`：返回问题列表，空=合法。8 条规则逐条实现、互不短路，
一次性收集全部问题便于修复。CLI：无参=校验 pipelines/*.json 全部；有问题 exit 1。
"""
import glob
import json
import os
import pathlib
import re
import sys
from collections import deque

PIPE_KEYS = {"name", "describe", "project", "parameter", "dag_json", "global_env", "expand"}
TASK_KEYS = {"job_templete", "name", "label", "volume_mount", "resource_memory",
             "resource_cpu", "resource_gpu", "args"}
_VM_RE = re.compile(r"^[\w\-.]+\((pvc|hostPath|memory)\):/.+")
_MEM_RE = re.compile(r"^\d+G$")
_CPU_RE = re.compile(r"^\d+$")
_GPU_RE = re.compile(r"^\d+(\.\d+)?$")


def validate(doc):
    problems = []
    for k in ("pipeline", "tasks"):
        if k not in doc:
            problems.append(f"缺少顶层键 {k}")
    pipe = doc.get("pipeline", {})
    tasks = doc.get("tasks", [])

    # 规则 1：pipeline 7 键
    miss = PIPE_KEYS - set(pipe)
    if miss:
        problems.append(f"pipeline 缺键: {sorted(miss)}")

    # 规则 2：task 8 键 + name 唯一
    names = []
    for i, t in enumerate(tasks):
        miss = TASK_KEYS - set(t)
        if miss:
            problems.append(f"task[{i}] 缺键: {sorted(miss)}")
        names.append(t.get("name"))
    if len(names) != len(set(names)):
        problems.append("task name 必须唯一")

    # 规则 3：args 键以 -- 开头
    for t in tasks:
        bad = [k for k in t.get("args", {}) if not str(k).startswith("--")]
        if bad:
            problems.append(f"task {t.get('name')}: args 键必须以 -- 开头: {bad}")

    dag = pipe.get("dag_json", {})
    # 规则 4：dag_json 键集合==task 名集合；upstream 引用存在
    if set(dag) != set(names):
        problems.append(f"dag_json 键集合与 task 名不一致: dag={sorted(dag)} tasks={sorted(names)}")
    for tn, node in dag.items():
        for up in (node or {}).get("upstream", []):
            if up not in names:
                problems.append(f"upstream 引用不存在的 task: {tn} -> {up}")

    # 规则 5：DAG 无环（Kahn）
    adj = {n: [] for n in names}
    indeg = {n: 0 for n in names}
    for tn, node in dag.items():
        if tn not in indeg:
            continue
        for up in (node or {}).get("upstream", []):
            if up in adj:
                adj[up].append(tn)
                indeg[tn] += 1
    q = deque(n for n in names if indeg[n] == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if seen != len(names):
        problems.append("DAG 存在环")

    # 规则 6：expand 的 id 集合==task 名集合
    ids = {e.get("id") for e in pipe.get("expand", [])}
    if ids != set(names):
        problems.append(f"expand id 集合与 task 名不一致: {sorted(ids)} vs {sorted(names)}")

    # 规则 7：volume_mount 与资源串格式
    for t in tasks:
        nm = t.get("name")
        if not _VM_RE.match(str(t.get("volume_mount", ""))):
            problems.append(f"task {nm}: volume_mount 非法(应 name(pvc|hostPath|memory):/path): {t.get('volume_mount')}")
        if not _MEM_RE.match(str(t.get("resource_memory", ""))):
            problems.append(f"task {nm}: resource_memory 非法(\\d+G)")
        if not _CPU_RE.match(str(t.get("resource_cpu", ""))):
            problems.append(f"task {nm}: resource_cpu 非法(\\d+)")
        if not _GPU_RE.match(str(t.get("resource_gpu", ""))):
            problems.append(f"task {nm}: resource_gpu 非法(\\d+(\\.\\d+)?)")

    # 规则 8：global_env 含 DATA_ROOT=/mnt/gov
    if "DATA_ROOT=/mnt/gov" not in str(pipe.get("global_env", "")):
        problems.append("global_env 必须包含 DATA_ROOT=/mnt/gov")

    return problems


def main(argv=None):
    paths = argv or sorted(glob.glob(str(pathlib.Path(__file__).resolve().parents[1] / "pipelines" / "*.json")))
    bad = 0
    for p in paths:
        doc = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        probs = validate(doc)
        name = os.path.basename(p)
        if probs:
            bad += 1
            print(f"[FAIL] {name}")
            for x in probs:
                print("   - " + x)
        else:
            print(f"[ OK ] {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
