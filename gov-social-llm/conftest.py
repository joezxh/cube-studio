"""本地测试脚手架：把各算子包与 gov-manifest 共享库注入 sys.path（不依赖镜像环境）。"""
import pathlib
import stat
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent
for p in [ROOT / "ops" / "gov-manifest" / "lib",
          ROOT / "ops" / "gov-distill-gen", ROOT / "ops" / "gov-distill-filter",
          ROOT / "ops" / "gov-eval", ROOT / "ops" / "gov-sft", ROOT / "ops" / "gov-kev",
          ROOT / "scripts"]:
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


@pytest.fixture(autouse=True)
def _clear_readonly(tmp_path):
    """Windows 兼容：测试结束后解除 seal() 设置的只读位，保证 tmp 目录可被清理。"""
    yield
    for f in pathlib.Path(tmp_path).rglob("*"):
        if f.is_file():
            try:
                f.chmod(stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
