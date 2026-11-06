# gov-sft — LLaMA-Factory LoRA/QLoRA 微调封装算子

方案 A「薄算子」之一（spec §2.2 / 计划 Task 6）。**平台只调度、AI 能力封装进镜像**：本算子
不实现训练逻辑，只生成 `dataset_info.json` 与 `llamafactory-cli` 训练/合并命令，真实模式经
`subprocess` 执行，并写 `train_manifest.json` 登记超参与数据集血缘。GPU 算子。

## 关键参数

| 参数 | 缺省 | 说明 |
|---|---|---|
| `--base` | 必填 | 学生底座权重路径（`/mnt/gov/models` 挂载下） |
| `--dataset` | 必填 | 过滤后训练数据 JSONL 绝对路径（sharegpt/alpaca） |
| `--dataset-name` | gov | `dataset_info.json` 注册名 |
| `--method` | lora | `lora` / `qlora`（qlora 追加 `--quantization_bit 4`） |
| `--lora-rank` | 32 | LoRA 秩 |
| `--lr` / `--epochs` / `--seq-len` | 1e-4 / 3 / 4096 | 学习率 / 轮数 / cutoff_len |
| `--deepspeed` | — | ZeRO 配置路径（多卡时传入） |
| `--output` | 必填 | adapter 输出目录 `/mnt/gov/sft/{ver}` |
| `--merge` | 关 | 训练后 `llamafactory-cli export` 合并全量权重 |
| `--dataset-manifest` | — | 上游数据集 manifest（登记血缘 parent） |

## 命令生成（`sft_cmd.py`，纯函数）

- `build_dataset_info(path, name)`：文件名含 `sharegpt` → `formatting:sharegpt` + `columns.messages=conversations`；否则 alpaca 三列映射。
- `build_train_cmd(...)`：返回 `list[str]`，每个 `--flag value` 为单元素；核心 flags：`--model_name_or_path/--lora_rank/--learning_rate/--num_train_epochs/--cutoff_len/--output_dir/--template default`。
- `merge_cmd(base, adapter, output)`：末元素 `--export_dir <output>`。

## dry-run 保护

`GOV_SFT_DRYRUN=1` 时跳过 `subprocess`，仅落 `train_cmd.sh`（+ dataset_info + manifest）；
平台 P4 实跑用真实模式。

## 产出

```
{output}/
├── dataset_info.json   # LLaMA-Factory 数据注册
├── train_cmd.sh        # 训练（及可选合并）命令
└── manifest.json       # write_manifest(op="gov-sft", extra={"hyper":…})
```

## 本地

```bash
pytest tests/test_sft_cmd.py -v
```
