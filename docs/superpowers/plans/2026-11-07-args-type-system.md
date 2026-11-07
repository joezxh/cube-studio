# 任务模板参数类型系统实现计划 (args-type-system)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在开源版自定义算子（Job_Template）参数链路上补齐企业版功能点 #22：int/float/list/bool/json 五种参数类型完整可用、workdir/image/select-input/select2/project 五种子类型、参数 tip 提醒，后端统一校验且对旧数据向后兼容。

**Architecture:** 后端将 core.py 中内联的参数校验实现迁移到自包含模块 `myapp/utils/py/args_schema.py` 并扩展（类型注册表 + 新字段校验 + JSON Schema 子集校验），core.py 通过 re-export 保持全部既有调用方 API 兼容；前端新增自包含渲染组件 `ArgsField`（vision 与 visionPlus 各一份，因构建包隔离），以最小插入点接入两个 FlowEditor 的参数渲染链。

**Tech Stack:** Python 3.x / pytest（无新增 pip 依赖，JSON Schema 用自实现子集）；React + @fluentui/react（react-app-rewired 构建）。

**Spec:** docs/superpowers/specs/2026-11-07-ent-training-features-brainstorm.md §5-E2（自定义任务模板参数类型扩展，#22）

## Global Constraints

1. 不新增任何 pip 依赖；JSON Schema 校验为自实现子集，仅支持 `type/properties/required/items/enum` 五个关键字。
2. 存量序列化契约不可破坏：`list` 类型的值统一归一化为**逗号分隔字符串**（`view_pipeline.py` 的 ops_args 以字符串逐个传给容器，`view_pipeline.py:208` 对 dict/list 才走 json.dumps）；`validate_job_args(args: str) -> str` 与 `validate_task_args(task_args: dict, job_args: dict) -> dict` 的签名与返回结构不变。
3. 未知参数类型的行为按层区分：模板注册时（`validate_job_args`）仍**拒绝**；任务参数校验时（`validate_task_args`）按 **string 降级**（旧 DAG JSON 兼容）。
4. `choice_url` 必须以 `/` 开头（站内相对路径），拒绝外链；选项由**浏览器侧** fetch，后端不做代理。
5. 命名与文案：新字段名固定为 `tip/regex/schema/choice_url`；子类型名固定为 `select-input/select2/workdir/image/project`（与 vision 前端既有 `item_type` 判断一致）。
6. commit 规范：`feat:`/`test:`/`docs:` 前缀 + 中文标题 + `(英文标识)`，每个 Task 一个提交。
7. 平台为 Windows（PowerShell）；python/pytest/npm 已可用；仓库根目录 `d:\projects\github\cube-studio`。执行时如需隔离工作区，先用 superpowers:using-git-worktrees。

## 既有代码事实（执行者必读）

- 参数定义结构：`myapp/utils/core.py:576` `default_args`（type/item_type/label/require/choice/range/default/placeholder/describe/editable），type 白名单在 `core.py:592`（已含 int/bool/str/text/enum/float/multiple/dict/list/file/json）。
- 缺口：`to_value`（core.py:650）无 bool 分支（会 raise）、无 file 分支；`list` 值仅做逗号 join、无 item_type 强转；json 值不做 schema 校验；`validate_task_args` 遇未知 type 直接 raise（core.py:666）；无 tip/regex/schema/choice_url 字段。
- 前端现状：`myapp/vision/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx` **已支持** tip（tip_tooltip）、regex（RegexValidatedTextField）、select-input（ComboBox）、workdir（打开目录按钮）、image（调试镜像按钮），**缺** bool/select2/project；`myapp/visionPlus/.../Setting/index.tsx` 仅支持 str/text/json/int + choice 下拉，tip/regex/子类型全缺。
- 帮助文案：`core.py:498` `job_template_args_definition()`，在模板表单 tips 中展示。
- 调用方（不可破坏）：`view_job_template.py:191,206,241`、`view_task.py:222` 均通过 `core.validate_job_args/core.validate_task_args` 调用。

---

### Task 1: 自包含参数 schema 模块骨架

**Files:**
- Create: `myapp/utils/py/args_schema.py`
- Test: `tests/test_args_schema.py`

**Interfaces:**
- Consumes: 无（自包含，仅标准库 + try-import myapp.exceptions）
- Produces: 模块 `myapp/utils/py/args_schema.py`，导出 `ARGS_TYPES: list[str]`、`ARGS_ITEM_TYPES: list[str]`、`SUB_TYPES: list[str]`、`default_args: dict`（含新字段 tip/regex/schema/choice_url）、`MyappException`（运行时为 `myapp.exceptions.MyappException`，脱包测试时为等价兜底类）。Task 2/3 在本模块内继续扩展。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_args_schema.py`：

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: FAIL，报错 `FileNotFoundError` 或 `spec_from_file_location` 找不到模块（args_schema.py 尚不存在）

- [ ] **Step 3: Write minimal implementation**

创建 `myapp/utils/py/args_schema.py`：

```python
"""任务模板参数类型系统（企业版 #22）。

自包含实现：仅依赖标准库，可脱离 Flask 应用单独测试。
core.py 通过 re-export 保持原有 validate_job_args/validate_task_args/default_args 的 API 兼容。

序列化契约（向后兼容红线）：
- list 类型的值统一归一化为逗号分隔字符串（容器以命令行参数方式接收）。
- type 为 json 的值解析为 dict/list 存储（ops_args 对 dict/list 走 json.dumps）。
"""
import copy
import json
import re

try:
    from myapp.exceptions import MyappException
except Exception:  # 脱离 myapp 包环境（如单测）时使用等价兜底类
    class MyappException(Exception):
        status = 500

        def __init__(self, msg):
            super(MyappException, self).__init__(msg)


# 参数类型注册表：type 控制值语义；item_type 控制子项类型或前端控件子类型
ARGS_TYPES = ['int', 'bool', 'str', 'text', 'enum', 'float', 'multiple', 'dict', 'list', 'file', 'json']
ARGS_ITEM_TYPES = ['int', 'str', 'text', 'float', 'dict',
                   'select-input', 'select2', 'workdir', 'image', 'project',
                   'python', 'java', 'json', 'sql']
SUB_TYPES = ['select-input', 'select2', 'workdir', 'image', 'project']

# 参数定义的默认结构。新增字段：tip/regex/schema/choice_url
default_args = {
    "type": "str",        # int,bool,str,text,enum,float,multiple,dict,list,file,json
    "item_type": "str",   # 在type为enum,list时每个子属性的类型；子类型：select-input,select2,workdir,image,project
    "label": "",          # 中文名
    "require": 1,         # 是否必须
    "choice": [],         # type为enum/multiple/select-input时，可选值
    "range": "",          # 最小最大取值，在int,float时使用  [$min,$max)
    "default": "",        # 默认值
    "placeholder": "",    # 输入提示内容
    "describe": "",       # 描述
    "editable": 1,        # 是否可修改
    "tip": "",            # 参数提醒，web表单tooltip展示，支持html
    "regex": "",          # str/text参数值的正则校验
    "schema": {},         # type为json时的JSON Schema声明（type,properties,required,items,enum）
    "choice_url": "",     # select2/project子类型的站内选项接口，必须以/开头
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/py/args_schema.py tests/test_args_schema.py
git commit -m "feat: 任务模板参数类型系统-自包含校验模块 (args-schema)"
```

---

### Task 2: validate_job_args 迁移 + 新字段校验

**Files:**
- Modify: `myapp/utils/py/args_schema.py`（追加函数）
- Test: `tests/test_args_schema.py`（追加用例）

**Interfaces:**
- Consumes: Task 1 的 `default_args/ARGS_TYPES/ARGS_ITEM_TYPES/SUB_TYPES/MyappException`
- Produces:
  - `validate_job_args(args: str) -> str`：输入模板参数定义 JSON 字符串，返回归一化后的 JSON 字符串（缩进 4、ensure_ascii=False）。非法 regex/schema/choice_url/未知 type 时 raise `MyappException`。
  - `check_json_schema_decl(schema)`：校验 schema 声明自身合法性（json_schema_check 值校验函数在 Task 3 产出）。

- [ ] **Step 1: Write the failing test**

在 `tests/test_args_schema.py` 追加：

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 新增 10 条 FAIL（`AttributeError: module has no attribute 'validate_job_args'`），Task 1 的 4 条仍 PASS

- [ ] **Step 3: Write minimal implementation**

在 `myapp/utils/py/args_schema.py` 的 `default_args` 之后追加：

```python
# JSON Schema 子集支持的关键字类型
JSON_SCHEMA_TYPES = ['object', 'array', 'string', 'number', 'integer', 'boolean']


def check_json_schema_decl(schema, path='schema'):
    """校验 schema 声明自身合法性（仅支持 type/properties/required/items/enum）。"""
    if not isinstance(schema, dict):
        raise MyappException("job template args %s must be dict" % path)
    schema_type = schema.get('type')
    if schema_type and schema_type not in JSON_SCHEMA_TYPES:
        raise MyappException("job template args %s.type must in %s" % (path, str(JSON_SCHEMA_TYPES)))
    if schema.get('required') is not None and not isinstance(schema['required'], list):
        raise MyappException("job template args %s.required must be list" % path)
    for key, sub in (schema.get('properties') or {}).items():
        check_json_schema_decl(sub, '%s.properties.%s' % (path, key))
    if schema.get('items'):
        check_json_schema_decl(schema['items'], '%s.items' % path)


def validate_job_args(args):
    """校验并归一化模板参数定义。输入/输出均为 JSON 字符串，非法定义 raise MyappException。"""
    validate_json(args)
    job_args = json.loads(json.dumps(json.loads(args), indent=4, ensure_ascii=False))

    def check_attr(attr):
        default_args_temp = copy.deepcopy(default_args)
        default_args_temp.update(attr)
        attr = default_args_temp
        attr['type'] = str(attr['type'])
        attr['item_type'] = str(attr['item_type'])
        attr['label'] = str(attr['label'])
        attr['require'] = int(attr['require'])
        attr['range'] = str(attr['range'])
        attr['default'] = attr['default']
        attr['placeholder'] = str(attr['placeholder'])
        attr['describe'] = str(attr['describe']) if attr['describe'] else str(attr['label'])
        attr['editable'] = int(attr['editable'])
        attr['tip'] = str(attr.get('tip') or '')
        attr['regex'] = str(attr.get('regex') or '')
        attr['choice_url'] = str(attr.get('choice_url') or '')
        if not isinstance(attr['schema'], dict):
            attr['schema'] = {}

        if attr['type'] not in ARGS_TYPES:
            raise MyappException("job template args type must in %s " % str(ARGS_TYPES))
        if attr['type'] in ('enum', 'multiple', 'list'):
            if attr['item_type'] not in ARGS_ITEM_TYPES:
                raise MyappException("job template args item_type must in %s " % str(ARGS_ITEM_TYPES))
        if attr['type'] in ('enum', 'multiple'):
            if not attr['choice']:
                raise MyappException("job template args choice must exist when type is enum,multiple ")
        if attr['type'] == 'dict':
            if not attr.get('sub_args'):
                raise MyappException("job template args sub_args must exist when type is dict ")
            for sub_attr in attr['sub_args']:
                attr['sub_args'][sub_attr] = check_attr(attr['sub_args'][sub_attr])
        if attr['type'] == 'list' and attr['item_type'] == 'dict':
            if not attr.get('sub_args'):
                raise MyappException("job template args sub_args must exist when type is list ")
            for sub_attr in attr['sub_args']:
                attr['sub_args'][sub_attr] = check_attr(attr['sub_args'][sub_attr])

        # 企业版 #22 扩展：新字段校验
        if attr['regex']:
            try:
                re.compile(attr['regex'])
            except re.error as e:
                raise MyappException("job template args regex is not valid: %s" % str(e))
        if attr['type'] == 'json':
            check_json_schema_decl(attr['schema'])
        if attr['choice_url'] and not attr['choice_url'].startswith('/'):
            raise MyappException("job template args choice_url must be site-relative, start with / ")
        if attr['item_type'] == 'select2' and not attr['choice_url']:
            raise MyappException("job template args choice_url must exist when item_type is select2 ")
        if attr['item_type'] == 'select-input' and not attr['choice']:
            raise MyappException("job template args choice must exist when item_type is select-input ")

        return attr

    for group in job_args:
        for attr_name in job_args[group]:
            job_args[group][attr_name] = check_attr(job_args[group][attr_name])

    return json.dumps(job_args, indent=4, ensure_ascii=False)


def validate_json(args):
    if args:
        try:
            json.loads(args)
        except Exception as e:
            raise MyappException("JSON is not valid :%s" % str(e))
```

说明：`validate_json` 在本模块内自带一份（与 core.py 的同名函数行为一致），保证模块自包含；core.py 保留自己的版本。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/py/args_schema.py tests/test_args_schema.py
git commit -m "feat: 任务模板参数类型系统-模板定义校验扩展 (args-schema-validate)"
```

---

### Task 3: validate_task_args 迁移 + bool/list/json-schema/未知类型降级

**Files:**
- Modify: `myapp/utils/py/args_schema.py`（追加函数）
- Test: `tests/test_args_schema.py`（追加用例）

**Interfaces:**
- Consumes: Task 1 的 `MyappException/default_args/ARGS_TYPES`；Task 2 的 `check_json_schema_decl`
- Produces: `validate_task_args(task_args: dict, job_args: dict) -> dict`（与 core.py 原函数同契约；新增 bool 强转、list item_type 强转并保持逗号串输出、json 字符串解析 + schema 校验、未知 type 按 str 降级、str/text 的 regex 校验）
- Produces: `json_schema_check(value, schema, path='args')`：对已解析的 json 值按 schema 子集校验，违规 raise

- [ ] **Step 1: Write the failing test**

在 `tests/test_args_schema.py` 追加：

```python
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
        args_schema.validate_task_args({}, _job(type='str', require=1))
    result = args_schema.validate_task_args({}, _job(type='str', default='dv'))
    assert result['--attr1'] == 'dv'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 新增 15 条 FAIL（`module has no attribute 'validate_task_args'`），已有 14 条 PASS

- [ ] **Step 3: Write minimal implementation**

在 `myapp/utils/py/args_schema.py` 追加：

```python
def _json_schema_type_ok(value, schema_type):
    if schema_type == 'object':
        return isinstance(value, dict)
    if schema_type == 'array':
        return isinstance(value, list)
    if schema_type == 'string':
        return isinstance(value, str)
    if schema_type == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == 'boolean':
        return isinstance(value, bool)
    return True


def json_schema_check(value, schema, path='args'):
    """按 JSON Schema 子集（type/properties/required/items/enum）校验已解析的 json 值。"""
    if not schema:
        return
    schema_type = schema.get('type')
    if schema_type and not _json_schema_type_ok(value, schema_type):
        raise MyappException("%s json schema type(%s) not match" % (path, schema_type))
    if 'enum' in schema and value not in schema['enum']:
        raise MyappException("%s json schema enum not match: %s" % (path, str(schema['enum'])))
    if isinstance(value, dict):
        for req in schema.get('required') or []:
            if req not in value:
                raise MyappException("%s json schema missing required key: %s" % (path, req))
        props = schema.get('properties') or {}
        for key in value:
            if key in props:
                json_schema_check(value[key], props[key], '%s.%s' % (path, key))
    if isinstance(value, list) and schema.get('items'):
        for idx, item in enumerate(value):
            json_schema_check(item, schema['items'], '%s[%d]' % (path, idx))


def validate_task_args(task_args, job_args):
    """校验任务参数值是否符合模板定义。task_args/job_args 均为字典，返回校验后的字典。

    向后兼容策略：未知 type 按 str 降级；list 值保持逗号分隔字符串契约。
    """
    if not task_args:
        return {}

    def to_value(value, value_type):
        if value_type in ('str', 'text', 'file'):
            return str(value).strip(' ')  # 把用户容易填错的多个空格去掉
        if value_type == 'int':
            return int(value)
        if value_type == 'float':
            return float(value)
        if value_type == 'bool':
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ('true', '1', 'yes'):
                return True
            if text in ('false', '0', 'no'):
                return False
            raise MyappException("task args bool is not valid: %s" % str(value))
        if value_type == 'dict':
            return dict(value)
        if value_type == 'json':
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception as e:
                    raise MyappException("task args json is not valid: %s" % str(e))
            return value
        raise MyappException("task args type is not valid: %s" % str(value))

    def check_attr(task_arg_value, job_arg_attr):
        validate_attr = task_arg_value
        attr_type = job_arg_attr.get('type', 'str')
        if attr_type not in ARGS_TYPES:
            attr_type = 'str'  # 未知类型按 string 降级（旧 DAG JSON 兼容）

        if attr_type in ('str', 'text', 'file', 'int', 'float', 'bool'):
            validate_attr = to_value(task_arg_value, attr_type)

        if attr_type == 'json':
            validate_attr = to_value(task_arg_value, attr_type)
            json_schema_check(validate_attr, job_arg_attr.get('schema') or {})

        if attr_type == 'enum':
            validate_attr = to_value(task_arg_value, job_arg_attr.get('item_type', 'str'))
            if validate_attr not in job_arg_attr.get('choice', []):
                raise MyappException("task arg type(enum) is not in choice: %s" % str(job_arg_attr.get('choice', [])))

        if attr_type == 'multiple':
            if type(task_arg_value) == str:
                validate_attr = re.split(' |,|;|\n|\t', str(task_arg_value))  # 分割字符串
            if type(validate_attr) == list:
                for item in validate_attr:
                    if item not in job_arg_attr.get('choice', []):
                        raise MyappException("task arg type(enum) is not in choice: %s" % str(job_arg_attr.get('choice', [])))

        if attr_type == 'dict' and type(job_arg_attr.get('sub_args')) != dict:
            raise MyappException("task args type(dict) sub args must is dict")

        if attr_type == 'dict':
            for sub_attr_name in task_arg_value:
                validate_attr[sub_attr_name] = check_attr(task_arg_value[sub_attr_name], job_arg_attr['sub_args'][sub_attr_name])

        if attr_type == 'list':
            # 保持逗号分隔字符串契约；接受数组或逗号/换行分隔的字符串
            if isinstance(task_arg_value, list):
                items = [str(x).strip() for x in task_arg_value]
            else:
                items = re.split(',|\n|\t', str(task_arg_value))
                items = [x.strip() for x in items]
            items = [x for x in items if x]
            item_type = job_arg_attr.get('item_type', 'str')
            if item_type == 'int':
                items = [str(int(x)) for x in items]
            elif item_type == 'float':
                items = [str(float(x)) for x in items]
            validate_attr = ','.join(items)

        # 企业版 #22 扩展：str/text 的 regex 校验
        if attr_type in ('str', 'text') and job_arg_attr.get('regex'):
            if not re.match(job_arg_attr['regex'], str(validate_attr)):
                raise MyappException("task args regex not match: %s" % str(validate_attr))

        return validate_attr

    validate_args = {}
    try:
        for group in job_args:
            for arg_name in job_args[group]:
                job_arg_attr = job_args[group][arg_name]
                if arg_name in task_args:
                    task_arg_value = task_args[arg_name]
                    validate_args[arg_name] = check_attr(task_arg_value, job_arg_attr)
                elif job_arg_attr.get('require', 1) and not job_arg_attr.get('default', ''):
                    raise MyappException("task args %s must is require" % arg_name)
                elif job_arg_attr['default']:
                    validate_args[arg_name] = job_arg_attr['default']

        return validate_args

    except MyappException:
        raise
    except Exception as e:
        raise MyappException("task args is not valid: %s" % str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/py/args_schema.py tests/test_args_schema.py
git commit -m "feat: 任务模板参数类型系统-任务参数校验扩展 (args-schema-task)"
```

---

### Task 4: core.py 接入（re-export + 帮助文案更新）

**Files:**
- Modify: `myapp/utils/core.py:498-522`（帮助文案）、`myapp/utils/core.py:575-725`（替换为实现 re-export）

**Interfaces:**
- Consumes: Task 1–3 的 `args_schema` 全部导出
- Produces: `core.validate_job_args/core.validate_task_args/core.default_args/core.json_schema_check` 与新实现同契约（所有既有调用方 `view_job_template.py`、`view_task.py` 零改动）

- [ ] **Step 1: 确认 default_args 的既有引用面**

Run: `rg -n "core\.default_args|core\.validate_job_args|core\.validate_task_args|core\.json_schema_check" myapp --type py`
Expected: 引用仅来自 view_job_template.py / view_task.py（re-export 即可覆盖；若有其他调用方，同样由 re-export 覆盖，无需改动）

- [ ] **Step 2: 替换 core.py 的内联实现为 re-export**

在 `myapp/utils/core.py` 中删除第 575–725 行的整块旧实现（`# 校验task args是否合法` 注释、`default_args`、`validate_job_args`、`import pysnooper`（该行在 642，如删除后同文件其他位置仍用 pysnooper 则保留该 import）、`validate_task_args`），原位替换为：

```python
# ===== 任务模板参数类型系统（企业版 #22）=====
# 实现迁移至 myapp/utils/py/args_schema.py（自包含，可脱离 Flask 应用单独测试）。
# 此处 re-export 保持原有函数名与契约；新增能力：tip/regex/schema/choice_url 字段、
# select-input/select2/workdir/image/project 子类型、bool 强转、list item_type 强转、
# json 的 JSON Schema 校验、未知类型按 str 降级。
from myapp.utils.py.args_schema import (  # noqa: E402
    ARGS_ITEM_TYPES,
    ARGS_TYPES,
    default_args,
    json_schema_check,
    validate_job_args,
    validate_task_args,
)
```

注意：若删除区间后 `pysnooper` 在 core.py 其他位置仍有使用（用 `rg -n "pysnooper" myapp/utils/core.py` 确认），则保留原 `import pysnooper` 行不删。

- [ ] **Step 3: 更新帮助文案**

将 `core.py:498-522` 的 `job_template_args_definition()` 整体替换为：

```python
# job模板参数的定义
def job_template_args_definition():
    demo = f'''
{{
    "group1":{{               # {_('参数分组，仅做web显示使用')}
       "--attr1":{{           # {_('参数名')}
        "type":"str",         # str,text,json,int,float,bool,list,enum,multiple,dict,file
        "item_type": "str",   # {_('子类型：int,str,text,float,dict,select-input,select2,workdir,image,project；text型还可为python,java,json,sql')}
        "label":"{_('参数1')}",      # {_('中文名')}
        "require":1,         # {_('是否必须')}
        "choice":[],         # {_('设定输入的可选值，enum/multiple/select-input时使用')}
        "range":"",          # {_('int和float型时设置最小最大值,"min,max"')}
        "default":"",        # {_('默认值')}
        "placeholder":"",    # {_('输入提示内容')}
        "describe":"{_('这里是这个参数的描述和备注')}",
        "editable":1,        # {_('是否可修改')}
        "tip":"",            # {_('参数提醒，web表单tooltip展示，支持html')}
        "regex":"",          # {_('str/text型参数值的正则校验，例如^v\\\\d+')}
        "schema":{{}},        # {_('type为json时的JSON Schema声明，支持type,properties,required,items,enum')}
        "choice_url":""      # {_('select2/project子类型的站内选项接口，必须以/开头，返回FAB列表json或字符串数组')}
      }},
      "--attr2":{{
       ...
      }}
    }},
    "group2":{{
    }}
}}
'''.strip()
    return _(demo)
```

- [ ] **Step 4: 语法与导入链验证**

Run: `python -m py_compile myapp/utils/core.py`
Expected: 无输出（编译通过）
说明：core.py 顶部依赖 pandas/flask/celery 等重依赖，完整 import 冒烟在部署环境执行；本计划的运行时行为已由 Task 1–3 的 27 条单测覆盖（同函数同契约）。

- [ ] **Step 5: Run test to verify it passes（回归）**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 29 passed（core.py 改动不影响自包含模块）

- [ ] **Step 6: Commit**

```bash
git add myapp/utils/core.py
git commit -m "feat: 任务模板参数类型系统-core接入与帮助文案 (args-schema-core)"
```

---

### Task 5: ArgsField 组件（vision）+ Model 接入

**Files:**
- Create: `myapp/vision/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx`
- Modify: `myapp/vision/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx`（在 `if (options.length > 0){` 锚点前插入 ArgsField 分支 + import）

**Interfaces:**
- Consumes: 后端模板参数定义（args 对象含 type/item_type/choice/choice_url/tip/regex/describe/editable 字段）
- Produces: 组件 `<ArgsField args name keyValue onChange />`，props 契约：`args: any`（参数定义）、`name: string`（参数名，作 label）、`keyValue: any`（当前值）、`onChange: (value: any) => void`。bool 输出 boolean；其余输出 string。Task 6 复用同一 props 契约（独立文件副本）。

- [ ] **Step 1: 确认 vision 的 UI 组件库导入源**

Run: `rg -n "^import" myapp/vision/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx`
Expected: 输出文件头部 import；记下 Dropdown/ComboBox 所在源（`@fluentui/react` 或 `office-ui-fabric-react`，下文代码以 `@fluentui/react` 书写，若实际为 `office-ui-fabric-react` 则仅替换 import 来源，组件 API 相同）

- [ ] **Step 2: 确认 vision 构建脚本存在**

Run: `Get-Content myapp/vision/package.json | Select-String '"build"'`
Expected: 输出 build 脚本行；若 vision 无 build 脚本，则在 package.json scripts 中确认实际可用脚本并以之替代（后续 Step 5 用同一脚本）

- [ ] **Step 3: 创建 ArgsField 组件**

创建 `myapp/vision/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx`：

```tsx
import React, { useEffect, useState } from 'react';
import {
  ActionButton,
  ComboBox,
  Dropdown,
  IDropdownOption,
  IconButton,
  TextField,
  Toggle,
  TooltipHost,
} from '@fluentui/react';

// 单个参数渲染器：bool/select-input/select2/workdir/image/project 子类型 + tip 提醒 + regex 校验
export interface IArgsFieldProps {
  args: any;
  name: string;
  keyValue: any;
  onChange: (value: any) => void;
}

const fetchChoiceOptions = async (choiceUrl: string): Promise<IDropdownOption[]> => {
  const resp = await fetch(choiceUrl, { credentials: 'include', headers: { Accept: 'application/json' } });
  const data = await resp.json();
  const rows: any[] = Array.isArray(data) ? data : data.result || [];
  return rows.map((item: any) =>
    typeof item === 'string'
      ? { key: item, text: item }
      : { key: String(item.name ?? item.id), text: String(item.name ?? item.id) }
  );
};

const ArgsField: React.FC<IArgsFieldProps> = (props) => {
  const { args, name, keyValue, onChange } = props;
  const item_type: string = args.item_type || 'str';
  const localOptions: IDropdownOption[] = (args.choice || []).map((option: any) => ({ key: option, text: option }));
  const [remoteOptions, setRemoteOptions] = useState<IDropdownOption[]>([]);
  const [regexError, setRegexError] = useState('');

  const needRemote = item_type === 'select2' || (item_type === 'project' && localOptions.length === 0);
  useEffect(() => {
    const url: string = args.choice_url || (item_type === 'project' ? '/project_modelview/api/' : '');
    if (needRemote && url) {
      fetchChoiceOptions(url)
        .then((opts) => setRemoteOptions(opts))
        .catch(() => setRemoteOptions([]));
    }
  }, [args.choice_url, needRemote]);

  const onTextChange = (value: string) => {
    if (args.regex) {
      try {
        setRegexError(new RegExp(args.regex).test(value) ? '' : '不符合格式要求');
      } catch (e) {
        setRegexError('');
      }
    }
    onChange(value);
  };

  const tipNode = args.tip ? (
    <TooltipHost content={args.tip}>
      <IconButton iconProps={{ iconName: 'Info' }} />
    </TooltipHost>
  ) : null;

  // bool：Toggle 开关，输出 boolean
  if (args.type === 'bool') {
    const checked = keyValue === true || keyValue === 'true' || keyValue === '1';
    return (
      <div>
        <Toggle
          label={name}
          checked={checked}
          onChange={(event: React.MouseEvent<HTMLElement>, checked?: boolean) => onChange(!!checked)}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // select2 / project：站内接口拉取选项的下拉
  if (item_type === 'select2' || item_type === 'project') {
    return (
      <div>
        <Dropdown
          label={name}
          options={remoteOptions}
          selectedKey={keyValue !== undefined && keyValue !== '' ? String(keyValue) : undefined}
          onChange={(event: React.FormEvent<HTMLDivElement>, option?: IDropdownOption) => onChange(option ? String(option.key) : '')}
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // select-input：可选可填（choice 选项 + 自由输入）
  if (item_type === 'select-input') {
    return (
      <div>
        <ComboBox
          label={name}
          options={localOptions}
          selectedKey={keyValue !== undefined && keyValue !== '' ? String(keyValue) : undefined}
          text={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
          allowFreeform
          autoComplete="on"
          onChange={(event: React.FormEvent<IComboBox>, option?: IComboBoxOption, index?: number, value?: string) =>
            onChange(value !== undefined ? value : option ? option.text : '')
          }
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // workdir / image：文本框 + 平台跳转按钮
  if (item_type === 'workdir' || item_type === 'image') {
    const actionUrl =
      item_type === 'workdir'
        ? '/notebook_modelview/api/entry/jupyter?file_path=' + keyValue
        : '/docker_modelview/api/entry/docker?image=' + keyValue;
    return (
      <div>
        <TextField
          label={name}
          value={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
          onChange={(event: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, value?: string) => onTextChange(value || '')}
          errorMessage={regexError}
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <ActionButton iconProps={{ iconName: item_type === 'workdir' ? 'FabricFolder' : 'Bug' }} onClick={() => window.open(actionUrl, '_blank')}>
          {item_type === 'workdir' ? '打开目录' : '调试镜像'}
        </ActionButton>
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // 兜底：str/text（含 regex 校验）
  return (
    <div>
      <TextField
        label={name}
        value={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
        onChange={(event: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, value?: string) => onTextChange(value || '')}
        errorMessage={regexError}
        required={args.require === 1}
        disabled={args.editable !== 1}
      />
      <div>
        <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
        {tipNode}
      </div>
    </div>
  );
};

export default ArgsField;
```

- [ ] **Step 4: 在 vision Model/index.tsx 接入**

在 `myapp/vision/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx` 中：

1. 文件头部 import 区追加：

```tsx
import ArgsField from '../ArgsField';
```

2. 在 `if (options.length > 0){`（该行在文件中唯一，位于 select-input ComboBox 分支之后）**之前**插入：

```tsx
              // 企业版 #22：bool/select2/project 等子类型走统一渲染器
              if (args.type === 'bool' || ['select-input', 'select2', 'workdir', 'image', 'project'].indexOf(args.item_type || '') >= 0) {
                return (
                  <React.Fragment key={key}>
                    <ArgsField
                      args={args}
                      name={`${key}`}
                      keyValue={keyValue}
                      onChange={(value: any) => handleOnChange(key, value, args.type)}
                    />
                  </React.Fragment>
                );
              }

```

说明：插入点位于 `const keyValue = ...`（L430 附近）之后，keyValue 已定义；select-input 由原内联 ComboBox 分支改走 ArgsField（行为一致，tip 渲染统一）。

- [ ] **Step 5: 构建验证**

Run: `cd myapp/vision; npm run build`
Expected: 构建成功（exit 0）

- [ ] **Step 6: Commit**

```bash
git add myapp/vision/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx myapp/vision/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx
git commit -m "feat: 任务模板参数类型系统-vision前端子类型 (args-field-vision)"
```

---

### Task 6: ArgsField 组件（visionPlus）+ Setting/Model 接入

**Files:**
- Create: `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx`
- Modify: `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx`
- Modify: `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx`

**Interfaces:**
- Consumes: Task 5 定义的 `<ArgsField args name keyValue onChange />` props 契约（此处为独立文件副本，代码相同，因 vision/visionPlus 是独立构建包）
- Produces: visionPlus 两个编辑面板（Setting 配置面板、Model 任务弹窗）均支持 bool/select-input/select2/workdir/image/project 子类型与 tip/regex

- [ ] **Step 1: 创建 visionPlus 的 ArgsField 组件**

将 Task 5 Step 3 的组件代码原样复制到 `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx`（visionPlus 已确认使用 `@fluentui/react`，见 Setting/index.tsx:2，import 无需改动）。

- [ ] **Step 2: 在 visionPlus Setting/index.tsx 接入**

在 `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx` 中：

1. 头部 import 区（第 2 行 `@fluentui/react` 之后）追加：

```tsx
import ArgsField from '../ArgsField';
```

2. 在 `if (options.length > 0) {`（L217，该行在文件中唯一）**之前**插入：

```tsx
              // 企业版 #22：bool/select2/project 等子类型走统一渲染器
              if (args.type === 'bool' || ['select-input', 'select2', 'workdir', 'image', 'project'].indexOf(args.item_type || '') >= 0) {
                return (
                  <ArgsField
                    key={key}
                    args={args}
                    name={`${key}`}
                    keyValue={keyValue}
                    onChange={(value: any) => handleOnChange(key, value, args.type)}
                  />
                );
              }

```

3. 为其余类型补 tip 提醒：将默认 TextField 分支的 `onRenderDescription`（原 L259–266）替换为：

```tsx
                    onRenderDescription={() => {
                      return (
                        <div
                          className={style.argsDescription}
                          dangerouslySetInnerHTML={{ __html: args.describe }}
                        ></div>
                      );
                    }}
```

改为（追加 tip 图标）：

```tsx
                    onRenderDescription={() => {
                      return (
                        <div className={style.argsDescription}>
                          <span dangerouslySetInnerHTML={{ __html: args.describe }}></span>
                          {args.tip ? <TooltipHost content={args.tip}><IconButton iconProps={{ iconName: 'Info' }} /></TooltipHost> : null}
                        </div>
                      );
                    }}
```

同时在第 2 行的 `@fluentui/react` import 中补入 `TooltipHost`、`IconButton`（该行已含 IconButton 则只补 TooltipHost）。

- [ ] **Step 3: 在 visionPlus Model/index.tsx 接入**

1. 先读取 `myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx` 的 L340–430，定位 `const keyValue = args.type === 'json' ? ...` 与其参数渲染分支的起始锚点。
2. 在渲染链最前（keyValue 定义之后、既有分支之前）按 Task 5 Step 4 相同方式插入 ArgsField 分支（`return (<ArgsField key={key} args={args} name={`${key}`} keyValue={keyValue} onChange={(value: any) => handleOnChange(key, value, args.type)} />)` 包裹于该文件既有的 Fragment 风格中），并追加 `import ArgsField from '../ArgsField';`。

- [ ] **Step 4: 构建验证**

Run: `cd myapp/visionPlus; npm run build`
Expected: 构建成功（exit 0，脚本自带 TSC_COMPILE_ON_ERROR=true）

- [ ] **Step 5: Commit**

```bash
git add myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/ArgsField/index.tsx myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx myapp/visionPlus/src/components/FlowEditor/components/EditorBody/components/Model/index.tsx
git commit -m "feat: 任务模板参数类型系统-visionPlus前端对齐 (args-field-visionplus)"
```

---

### Task 7: 全量回归与文档收尾

**Files:**
- Test: `tests/test_args_schema.py`（全量）
- Verify: 两个前端构建、后端 py_compile

**Interfaces:**
- Consumes: Task 1–6 全部产出
- Produces: 企业版 #22 交付完成的后端 + 前端验证证据

- [ ] **Step 1: 后端全量回归**

Run: `python -m pytest tests/test_args_schema.py -v`
Expected: 29 passed

- [ ] **Step 2: 后端语法回归**

Run: `python -m py_compile myapp/utils/core.py myapp/utils/py/args_schema.py`
Expected: 无输出

- [ ] **Step 3: 前端构建回归**

Run: `cd myapp/vision; npm run build; cd ../../visionPlus; npm run build`
Expected: 两个构建均 exit 0

- [ ] **Step 4: 交付核对（对照 spec §5-E2）**

逐项核对并在提交说明中记录：
1. int/float：值强转（既有）+ 单测覆盖 ✓
2. bool：后端强转 + 前端 Toggle ✓
3. list：数组/字符串输入统一逗号串（契约不破坏）+ item_type 强转 ✓
4. json：JSON Schema 声明与校验 ✓
5. workdir/image/select-input/select2/project：后端注册校验 + 前端 ArgsField ✓
6. tip：后端字段归一化 + 前端 tooltip（vision 既有 + visionPlus 新增）✓
7. 后端统一校验：所有值经 validate_task_args；未知类型按 str 降级 ✓

- [ ] **Step 5: Commit（如有遗留修正）**

```bash
git add -A
git commit -m "test: 任务模板参数类型系统-全量回归 (args-schema-regression)"
```

若无遗留修正（前 6 个 Task 已全部提交），跳过本步骤。

## 范围外说明（YAGNI）

- `range`（min,max）在 int/float 上历史未强制，本计划不启用强制（wiki #22 未要求）。
- visionPlus `Model/index.tsx` 若结构与描述偏差过大，允许仅在 Setting/index.tsx 完成 Task 6 的接入并在提交说明中记录 Model 的遗留项，交由人工确认后续跟进。
- list 的前端动态增删行控件留待后续增强，v1 以 textarea 逗号/换行分隔输入（后端两种输入均支持）。
