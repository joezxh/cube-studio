"""向 init-job-template.json 追加 lerobot 三模板（幂等：已存在则跳过）。"""
import json

PATH = "myapp/init/init-job-template.json"


def arg(label, typ="str", default="", choice=None, require=0, describe="", item="str"):
    return {"choice": choice or [], "default": default, "describe": describe,
            "editable": 1, "item_type": item, "label": label,
            "placeholder": "", "range": "", "require": require, "type": typ}


def main():
    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)
    img_cpu = "ccr.ccs.tencentyun.com/cube-studio/lerobot:import-cpu"
    img_gpu = "ccr.ccs.tencentyun.com/cube-studio/lerobot:gpu-0.6.2"
    new = {
        "lerobot-import": {
            "gitpath": "/job-template/job/lerobot_import",
            "image_describe": "LeRobotDataset 接入轻镜像", "image_name": img_cpu,
            "job_template_account": "",
            "job_template_args": {"数据集接入": {
                "--source_type": arg("数据集来源", default="local_path",
                                     choice=["local_path", "hub_repo_id"], require=1,
                                     describe="local_path=共享存储目录；hub_repo_id=HuggingFace 数据集 id"),
                "--source": arg("来源路径或repo_id", default="", require=1,
                                describe="如 /data/k8s/kubeflow/global/raw/pusht_v3 或 lerobot/pusht"),
                "--target_name": arg("数据集名称", require=1, default="pusht_demo"),
                "--target_version": arg("数据集版本", default="v1"),
                "--hub_endpoint": arg("HF镜像源", describe="内网可填 https://hf-mirror.com，仅 hub 来源生效"),
                "--link_mode": arg("软链免拷贝", "bool", default="false",
                                   describe="仅 local_path 同盘生效，默认拷贝")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobotDataset 接入与画像(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-import",
            "job_template_volume": "",
            "project_name": "数据导入导出"},
        "lerobot-train": {
            "gitpath": "/job-template/job/lerobot_train",
            "image_describe": "lerobot训练镜像 0.6.2", "image_name": img_gpu,
            "job_template_account": "",
            "job_template_args": {"策略与数据": {
                "--policy_type": arg("策略类型", default="act",
                                     choice=["act", "diffusion", "vqbet", "smolvla"],
                                     require=0, describe="与加载权重二选一；smolvla 需单卡≥24G"),
                "--policy_path": arg("加载权重路径", describe="预训练/续训 checkpoint 目录或 Hub 模型 id，与策略类型互斥"),
                "--dataset_ref": arg("数据集引用", default="pusht_demo:v1", require=1,
                                     describe="已登记的 lerobot 数据集 name:version"),
                "--output": arg("输出目录", default="/mnt/{{creator}}/lerobot/train",
                                require=1)},
                "训练参数": {
                    "--batch_size": arg("batch_size", "int", default="8"),
                    "--steps": arg("训练步数", "int", default="10000"),
                    "--save_freq": arg("保存频率", "int", default="5000"),
                    "--log_freq": arg("日志频率", "int", default="200"),
                    "--lr": arg("学习率", describe="留空用策略默认，如 1e-4"),
                    "--resume": arg("断点续训", "bool", default="false"),
                    "--wandb_enable": arg("wandb记录", "bool", default="false",
                                          describe="内网建议关闭，指标落 metrics.json"),
                    "--extra_args": arg("透传参数",
                                        describe="逃生舱，仅 --flag value 偶数对，如 --policy.chunk_size 50")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobot 策略训练(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-train",
            "job_template_volume": "",
            "project_name": "深度学习"},
        "lerobot-eval": {
            "gitpath": "/job-template/job/lerobot_eval",
            "image_describe": "lerobot评测镜像 0.6.2", "image_name": img_gpu,
            "job_template_account": "",
            "job_template_args": {"仿真评测": {
                "--checkpoint": arg("checkpoint路径", require=1,
                                   describe="上游训练产物 checkpoints/{step}/pretrained_model 或 Hub 模型 id"),
                "--env_type": arg("仿真环境", default="pusht",
                                  choice=["pusht", "aloha"], require=1,
                                  describe="自定义环境名透传，预设环境启动前校验动作维度"),
                "--output": arg("输出目录", default="/mnt/{{creator}}/lerobot/eval",
                                require=1),
                "--n_episodes": arg("评测回合数", "int", default="50"),
                "--batch_size": arg("并行环境数", "int", default="10"),
                "--seed": arg("随机种子", "int", default="100000",
                              describe="同 seed 同 checkpoint 结果可复现"),
                "--video_n_episodes": arg("录视频数", "int", default="3",
                                          describe="置 0 关闭录制")}},
            "job_template_command": "python3 start.py",
            "job_template_describe": "LeRobot 仿真评测(企业版)",
            "job_template_env": "", "job_template_expand": {},
            "job_template_name": "lerobot-eval",
            "job_template_volume": "",
            "project_name": "深度学习"},
    }
    changed = False
    for k, v in new.items():
        if k not in d:
            d[k] = v
            changed = True
    if changed:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=4)
    print("templates ready:", list(new))


if __name__ == "__main__":
    main()
