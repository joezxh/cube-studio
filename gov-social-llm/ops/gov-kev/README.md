# gov-kev — kev（system-one 决策）微调对照臂封装算子

方案 A「薄算子」之一（计划 Task 7）。kev 是 Jared Palmer 提出的 **system-one 快速决策**微调范式
（指针头 / pointer head），用于工单分派、风险打分这类「先快后想」的任务，与 gov-sft 的
LoRA 微调构成**双臂对照实验**。GPU 算子。

## 与 gov-sft 的边界（spec §3.4 约束提醒）

> **kev 的「指针头」不受 LLaMA-Factory 支持，本对照臂不可用 gov-sft 替代。** 两臂各自独立封装，
> 共用工单/风险任务定义与数据（Task 4 的 `kev_format.jsonl`），但训练/服务栈不同。

## 关键参数

| 参数 | 缺省 | 说明 |
|---|---|---|
| `--mode` | train | `train` / `serve` |
| `--data` | — | `kev_format.jsonl`（Task 4 产出，train 必填） |
| `--base` | Qwen3.5-0.8B | kev 底座 |
| `--init-from` | jaredpalmer/kev-0.8b | 初始化检查点 |
| `--epochs` / `--lr` / `--batch` / `--accum` | 2 / 2e-5 / 1 / 8 | 训练超参 |
| `--output` | — | train run 目录 `/mnt/gov/kev/{ver}` |
| `--run` / `--port` | output / 8009 | serve 加载的 run 与端口 |
| `--data-manifest` | — | 上游 kev 数据 manifest（登记血缘 parent） |

## 命令生成（`kev_cmd.py`，纯函数）

- `build_kev_train_cmd(...)` → `python -m kev.train --data … --base … --init_from … --epochs 2 --lr 2e-5 --batch 1 --accum 8 --output_dir …`
- `build_kev_serve_cmd(run, port=8009)` → `uv run --extra serve python -m kev.serve --run <run> --port 8009`

命令以 `list[str]` 返回，「--flag value」单元素，风格与 gov-sft 一致。

## dry-run 保护

`GOV_KEV_DRYRUN=1` 时跳过 `subprocess`，仅落 `train_cmd.sh`（+ manifest）。

## 产出

```
{output}/
├── train_cmd.sh    # python -m kev.train …
└── manifest.json   # write_manifest(op="gov-kev", extra={"hyper":…,"license":"Apache-2.0"})
```

## 本地

```bash
pytest tests/test_kev_cmd.py -v
```
