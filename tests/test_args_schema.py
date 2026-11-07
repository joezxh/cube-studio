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


def _job_def(attr):
    return json.dumps({'group1': {'--attr1': attr}}, ensure_ascii=False)


def test_validate_job_args_new_fields_normalized():
    result = json.loads(args_schema.validate_job_args(_job_def({
        'type': 'str', 'label': '参数1', 'tip': '<b>提示</b>', 'regex': r'^v\d+$', 'describe': 'desc',
    })))
    attr = result['group1']['--attr1']
    assert attr['tip'] == '<b>提示</b>'
    assert attr['regex'] == r'^v\d+$'
    assert attr['schema'] == {}
    assert attr['choice_url'] == ''


def test_validate_job_args_invalid_regex_rejected():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'str', 'regex': '(['}))


def test_validate_job_args_choice_url_must_be_site_relative():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'str', 'item_type': 'select2', 'choice_url': 'http://evil.com/api'}))


def test_validate_job_args_select2_requires_choice_url():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'str', 'item_type': 'select2'}))


def test_validate_job_args_select_input_requires_choice():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'str', 'item_type': 'select-input'}))


def test_validate_job_args_enum_without_choice_still_rejected():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'enum'}))


def test_validate_job_args_json_schema_decl_validated():
    result = json.loads(args_schema.validate_job_args(_job_def({
        'type': 'json', 'schema': {'type': 'object', 'properties': {'lr': {'type': 'number'}}},
    })))
    assert result['group1']['--attr1']['schema']['type'] == 'object'


def test_validate_job_args_json_schema_decl_invalid_rejected():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'json', 'schema': {'type': 'not-a-type'}}))


def test_validate_job_args_unknown_type_rejected():
    with pytest.raises(Exception):
        args_schema.validate_job_args(_job_def({'type': 'not-exist-type'}))


def test_validate_job_args_backward_compatible_output():
    result = json.loads(args_schema.validate_job_args(_job_def({
        'type': 'str', 'label': '参数1', 'default': 'value1', 'describe': '这里是这个参数的描述和备注',
    })))
    attr = result['group1']['--attr1']
    assert attr['type'] == 'str'
    assert attr['default'] == 'value1'
    assert attr['editable'] == 1
