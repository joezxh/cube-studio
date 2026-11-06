"""Task1: T1–T4 任务 schema 与 kev-questions 结构测试（spec §2.2 / §3.4）。"""
import json
import pathlib

import pytest
from jsonschema import Draft202012Validator

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "task-spec" / "schemas"


@pytest.mark.parametrize("name", ["T1", "T2", "T3", "T4"])
def test_schema_valid_and_example_passes(name):
    schema = json.loads((SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    example = json.loads(schema["$meta"]["example"])  # 每个 schema 内嵌一条合法示例
    Draft202012Validator(schema).validate(example)


def test_kev_questions_shape():
    q = json.loads((SCHEMA_DIR / "kev-questions.json").read_text(encoding="utf-8"))
    assert {"department", "escalate", "frustration"} <= set(q["questions"])
