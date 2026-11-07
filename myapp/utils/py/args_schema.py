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


def validate_json(args):
    if args:
        try:
            json.loads(args)
        except Exception as e:
            raise MyappException("JSON is not valid :%s" % str(e))


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
