# 测试加载机制：myapp/__init__.py 在 import 时即完整 boot Flask app
# （创建 app、连接 db.engine、初始化 AppBuilder），本地无 MYSQL_SERVICE 等环境必然失败。
# 因此这里以 stub 空包占位 myapp/myapp.utils，再按文件路径加载被测模块，
# 使测试文件中的 `from myapp.utils.xxx import ...` 不触发真实包链。
# 被测 util 模块自身禁止 import myapp.*（计划 Global Constraints），保证此机制成立。
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _stub_package(name):
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = []  # 标记为包
        sys.modules[name] = module
    return sys.modules[name]


def _load_module(name, relpath):
    path = ROOT / relpath
    if not path.exists():
        return  # 尚未实现：交给测试文件 import 时的 ModuleNotFoundError 作为 TDD 红灯
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_stub_package('myapp')
_stub_package('myapp.utils')

_load_module('myapp.utils.dataset_reader', 'myapp/utils/dataset_reader.py')
_load_module('myapp.utils.dataset_profile', 'myapp/utils/dataset_profile.py')
_load_module('myapp.utils.labelstudio_bridge', 'myapp/utils/labelstudio_bridge.py')
