"""本地测试脚手架：把各算子包与 gov-manifest 共享库注入 sys.path（不依赖镜像环境）。"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
for p in [ROOT / "ops" / "gov-manifest" / "lib",
          ROOT / "ops" / "gov-distill-gen", ROOT / "ops" / "gov-distill-filter",
          ROOT / "ops" / "gov-eval", ROOT / "ops" / "gov-sft", ROOT / "ops" / "gov-kev",
          ROOT / "scripts"]:
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
