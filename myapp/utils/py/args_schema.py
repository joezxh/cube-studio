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
