"""gov-sft：LLaMA-Factory 训练/合并命令生成（纯函数，spec §2.2 / 计划 Task 6）。

约定：命令以 list[str] 返回，每个「--flag value」为单个元素，布尔参数为单独元素，
`subprocess.run(cmd)` 与 `" ".join(cmd)` 均可直接使用，无需二次 shell 解析。
权重不打入镜像，运行时由 /mnt/gov/models 挂载提供。
"""


def build_dataset_info(dataset_path, name):
    """LLaMA-Factory dataset_info.json 单条目 dict。按文件名含 sharegpt/alpaca 判别格式。"""
    p = str(dataset_path)
    if "sharegpt" in p.lower():
        entry = {
            "file_name": p,
            "formatting": "sharegpt",
            "columns": {"messages": "conversations"},
        }
    else:
        entry = {
            "file_name": p,
            "formatting": "alpaca",
            "columns": {"prompt": "instruction", "query": "input", "response": "output"},
        }
    return {name: entry}


def build_train_cmd(*, method, base, dataset_name, lora_r, lr, epochs,
                    seq_len, output, deepspeed=None):
    """组装 llamafactory-cli 训练命令。method: lora|qlora。"""
    cmd = [
        "llamafactory-cli", "train",
        f"--model_name_or_path {base}",
        "--stage sft",
        "--do_train",
        f"--dataset {dataset_name}",
        "--template default",
        "--finetuning_type lora",
        f"--lora_rank {lora_r}",
        f"--learning_rate {lr}",
        f"--num_train_epochs {epochs}",
        f"--cutoff_len {seq_len}",
        f"--output_dir {output}",
        "--overwrite_output_dir",
        "--per_device_train_batch_size 1",
        "--gradient_accumulation_steps 8",
        "--logging_steps 10",
        "--save_strategy steps",
        "--save_steps 100",
        "--plot_loss",
        "--report_to none",
        "--bf16",
    ]
    if method == "qlora":
        cmd.append("--quantization_bit 4")
    if deepspeed:
        cmd.append(f"--deepspeed {deepspeed}")
    return cmd


def merge_cmd(base, adapter, output):
    """LoRA adapter 合并导出命令（llamafactory-cli export）。"""
    return [
        "llamafactory-cli", "export",
        f"--model_name_or_path {base}",
        f"--adapter_name_or_path {adapter}",
        "--template default",
        "--finetuning_type lora",
        f"--export_dir {output}",
    ]
