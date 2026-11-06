"""gov-kev 命令生成测试（计划 Task 7）。

约定同 gov-sft：命令 list[str]，每个「--flag value」为单元素、模块 token 独立成元素，
故 serve 断言以成员相等（in cmd）校验，train 断言以拼接子串校验。
"""
from kev_cmd import build_kev_serve_cmd, build_kev_train_cmd


def test_train_cmd():
    cmd = build_kev_train_cmd(data="/d/kev.jsonl", base="Qwen3.5-0.8B", init_from="jaredpalmer/kev-0.8b",
                              epochs=2, lr="2e-5", batch=1, accum=8, output="/o/kev-v1")
    s = " ".join(cmd)
    assert "kev.train" in s and "--init_from jaredpalmer/kev-0.8b" in s and "--output_dir /o/kev-v1" in s


def test_serve_cmd_systemone():
    cmd = build_kev_serve_cmd("/o/kev-v1", port=8009)
    assert "kev.serve" in cmd and "--port 8009" in cmd and "--run /o/kev-v1" in cmd
