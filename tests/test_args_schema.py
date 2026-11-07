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


def _job(**attr):
    return {'group1': {'--attr1': attr}}


def test_int_and_float_coercion():
    job_group = {'group1': {'--a': {'type': 'int'}, '--b': {'type': 'float'}}}
    result = args_schema.validate_task_args({'--a': '3', '--b': '0.5'}, job_group)
    assert result['--a'] == 3
    assert result['--b'] == 0.5


def test_int_coercion_rejected_on_bad_value():
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--a': 'abc'}, {'group1': {'--a': {'type': 'int'}}})


def test_bool_native_accepted():
    assert args_schema.validate_task_args({'--attr1': True}, _job(type='bool'))['--attr1'] is True


def test_bool_string_coerced():
    assert args_schema.validate_task_args({'--attr1': 'false'}, _job(type='bool'))['--attr1'] is False


def test_bool_invalid_rejected():
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--attr1': 'maybe'}, _job(type='bool'))


def test_list_from_string_normalized_to_comma_joined():
    result = args_schema.validate_task_args({'--attr1': 'a, b,,c'}, _job(type='list'))
    assert result['--attr1'] == 'a,b,c'


def test_list_from_array_normalized_to_comma_joined():
    result = args_schema.validate_task_args({'--attr1': ['1', '2']}, _job(type='list', item_type='int'))
    assert result['--attr1'] == '1,2'


def test_list_int_item_type_coercion_rejected_on_bad_value():
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--attr1': ['x']}, _job(type='list', item_type='int'))


def test_json_string_parsed_and_schema_checked():
    job = _job(type='json', schema={'type': 'object', 'properties': {'lr': {'type': 'number'}}, 'required': ['lr']})
    result = args_schema.validate_task_args({'--attr1': '{"lr": 0.1}'}, job)
    assert result['--attr1'] == {'lr': 0.1}


def test_json_schema_violation_rejected():
    job = _job(type='json', schema={'type': 'object', 'properties': {'lr': {'type': 'number'}}})
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--attr1': {'lr': 'abc'}}, job)


def test_json_schema_missing_required_rejected():
    job = _job(type='json', schema={'type': 'object', 'required': ['lr']})
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--attr1': {}}, job)


def test_unknown_type_degrades_to_str():
    result = args_schema.validate_task_args({'--attr1': ' 42 '}, _job(type='not-exist-type'))
    assert result['--attr1'] == '42'


def test_str_regex_enforced():
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--attr1': 'abc'}, _job(type='str', regex=r'^v\d+$'))


def test_str_regex_pass():
    result = args_schema.validate_task_args({'--attr1': 'v1.0'}, _job(type='str', regex=r'^v\d+'))
    assert result['--attr1'] == 'v1.0'


def test_require_and_default_semantics_unchanged():
    with pytest.raises(Exception):
        args_schema.validate_task_args({'--other': 'x'}, _job(type='str', require=1))
    result = args_schema.validate_task_args({'--other': 'x'}, _job(type='str', default='dv'))
    assert result['--attr1'] == 'dv'
    # 空任务参数：与原 core.py 语义一致，早返回空字典（不触发 require/default）
    assert args_schema.validate_task_args({}, _job(type='str', require=1)) == {}
