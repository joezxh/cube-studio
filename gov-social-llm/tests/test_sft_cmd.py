"""gov-sft LLaMA-Factory 命令生成测试（计划 Task 6）。

约定：build_train_cmd/merge_cmd 返回 list[str]，每个「--flag value」为单个元素，
拼接后即可作为 shell 命令；布尔参数为单独元素（如 "--do_train"）。
"""
from sft_cmd import build_dataset_info, build_train_cmd, merge_cmd


def test_dataset_info_both_formats():
    assert build_dataset_info("/d/train_sharegpt.jsonl", "gov")["gov"]["formatting"] == "sharegpt"
    assert build_dataset_info("/d/train_alpaca.jsonl", "gov")["gov"]["file_name"] == "/d/train_alpaca.jsonl"


def test_lora_cmd_contains_core_flags():
    cmd = build_train_cmd(method="lora", base="/m/Qwen3.8-1.7B", dataset_name="gov",
                          lora_r=32, lr="1e-4", epochs=3, seq_len=4096, output="/o/v1")
    s = " ".join(cmd)
    assert "llama-cli" in s or "train" in s
    for flag in ["--model_name_or_path /m/Qwen3.8-1.7B", "--lora_rank 32",
                 "--learning_rate 1e-4", "--num_train_epochs 3", "--cutoff_len 4096",
                 "--output_dir /o/v1", "--template default"]:
        assert flag in s, flag


def test_qlora_adds_quantization():
    cmd = build_train_cmd(method="qlora", base="/b", dataset_name="g", lora_r=16,
                          lr="1e-4", epochs=2, seq_len=2048, output="/o")
    assert "--quantization_bit 4" in cmd


def test_merge_cmd():
    assert merge_cmd("/b", "/o/v1", "/o/v1-merged")[-1] == "--export_dir /o/v1-merged"
