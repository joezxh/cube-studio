"""任务模板参数类型系统单测。

用 importlib 按文件路径加载 args_schema，避免触发 myapp/__init__.py 的 Flask 应用构建。
"""
import importlib.util
import json
import pathlib

import pytest

_MOD_PATH = pathlib.Path(__file__).resolve().parents[1] / 'myapp' / 'utils' / 'py' / 'args_schema.py'
_spec = importlib.util.spec_from_file_location('args_schema_under_test', _MOD_PATH)
args_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(args_schema)


def test_default_args_contains_new_fields():
    for field in ('tip', 'regex', 'schema', 'choice_url'):
        assert field in args_schema.default_args


def test_args_types_cover_enterprise_types():
    for t in ('int', 'float', 'list', 'bool', 'json'):
        assert t in args_schema.ARGS_TYPES


def test_args_item_types_cover_sub_types():
    for t in ('select-input', 'select2', 'workdir', 'image', 'project'):
        assert t in args_schema.ARGS_ITEM_TYPES


def test_module_exception_is_exception_subclass():
    assert issubclass(args_schema.MyappException, Exception)
