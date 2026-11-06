"""Pipeline 格式校验器测试（计划 Task 8）。

注：计划原文 GOOD 样例的 dag_json 仅含 {"b":...}，但违规变体 lambda 会访问 dag_json["a"]，
将触发 KeyError。此处补全 a 节点使 GOOD 自洽（dag_json 键集合==task 名集合）。
"""
import copy
import json
import pathlib

import pytest

from validate_pipelines import validate

GOOD = {  # 合法双节点样例（规则各分支测试的基座）
    "pipeline": {
        "name": "p", "describe": "d", "project": "社会治理", "parameter": {},
        "dag_json": {"a": {"upstream": []}, "b": {"upstream": ["a"]}},
        "global_env": "DATA_ROOT=/mnt/gov",
        "expand": [{"id": "a", "type": "dataSet", "position": {"x": 0, "y": 0}, "data": {"name": "a", "label": "A"}},
                   {"id": "b", "type": "dataSet", "position": {"x": 1, "y": 0}, "data": {"name": "b", "label": "B"}}],
    },
    "tasks": [
        {"job_templete": "gov-eval", "name": "a", "label": "A", "volume_mount": "gov-nfs(pvc):/mnt",
         "resource_memory": "4G", "resource_cpu": "2", "resource_gpu": "0", "args": {"--mode": "smoke"}},
        {"job_templete": "gov-manifest", "name": "b", "label": "B", "volume_mount": "gov-nfs(pvc):/mnt",
         "resource_memory": "2G", "resource_cpu": "1", "resource_gpu": "0", "args": {"--cmd": "verify", "--dir": "x"}},
    ],
}


def _mutate_cycle(d):
    d["pipeline"]["dag_json"]["a"].update({"upstream": ["b"]})
    d["pipeline"]["dag_json"]["b"].update({"upstream": ["a"]})


@pytest.mark.parametrize("mutate,keyword", [
    (lambda d: d["tasks"][0]["args"].update({"mode": "x"}), "args"),
    (lambda d: d["tasks"].pop(1), "dag_json"),
    (lambda d: d["pipeline"]["dag_json"]["a"].update({"upstream": ["ghost"]}), "ghost"),
    (_mutate_cycle, "环"),
    (lambda d: d["tasks"][0].__setitem__("volume_mount", "bad-mount"), "volume_mount"),
    (lambda d: d["pipeline"].__setitem__("global_env", "X=1"), "DATA_ROOT"),
    (lambda d: d["pipeline"]["expand"].pop(1), "expand"),
])
def test_rules(mutate, keyword):
    d = copy.deepcopy(GOOD)
    mutate(d)
    assert any(keyword in p for p in validate(d)), validate(d)


def test_good_is_valid():
    assert validate(copy.deepcopy(GOOD)) == []


@pytest.mark.parametrize("f", ["gov-p0-env-check.json", "gov-p1-eval-build.json", "gov-p2-distill-line.json"])
def test_real_pipelines_valid(f):
    doc = json.loads((pathlib.Path(__file__).parents[1] / "pipelines" / f).read_text(encoding="utf-8"))
    assert validate(doc) == []
