"""gov-kev：kev（Jared Palmer 的 system-one 决策微调）命令生成（计划 Task 7）。

纯函数，返回 list[str]，每个「--flag value」为单元素、模块 token 独立成元素。
与 gov-sft 的关键区别（spec §3.4 约束提醒）：kev 用「指针头」而非 LoRA，
LLaMA-Factory 不支持该范式，故工单分派/风险打分的对照实验臂必须由本算子独立封装，
不可用 gov-sft 替代。
"""


def build_kev_train_cmd(*, data, base, init_from, epochs, lr, batch, accum, output):
    """kev 训练命令：在 base 上从 init_from 检查点继续，产出 system-one 决策 run。"""
    return [
        "python", "-m", "kev.train",
        f"--data {data}",
        f"--base {base}",
        f"--init_from {init_from}",
        f"--epochs {epochs}",
        f"--lr {lr}",
        f"--batch {batch}",
        f"--accum {accum}",
        f"--output_dir {output}",
    ]


def build_kev_serve_cmd(run, port=8009):
    """kev 推理服务命令：uv 拉起 serve extra，对已训练 run 提供 system-one 端点。"""
    return [
        "uv", "run", "--extra serve",
        "python", "-m", "kev.serve",
        f"--run {run}",
        f"--port {port}",
    ]
