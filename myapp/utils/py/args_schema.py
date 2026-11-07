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
