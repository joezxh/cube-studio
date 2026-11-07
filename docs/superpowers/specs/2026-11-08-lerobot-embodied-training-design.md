# 具身智能 / VLA 训练（LeRobot 整合）设计文档

> **来源**：头脑风暴母文档 `docs/superpowers/specs/2026-11-07-ent-training-features-brainstorm.md` 主题 F（§6），本 spec 覆盖 F1+F2+F3；F4（checkpoint 边缘分发与指标回流）不在本期范围。
> **目标**：在 cube-studio 平台交付具身智能训练最小闭环——LeRobotDataset 数据进平台（F2）→ lerobot-train 训练（F1）→ lerobot-eval 仿真评测（F3），产物与指标全部走平台既有契约。
> **上游锚定**：HuggingFace LeRobot `0.6.2`（CLI 形态 `lerobot-train` / `lerobot-eval`，数据格式 LeRobotDataset v3，兼容读取 v2.1）。

## §1 范围与已对齐决策

### 1.1 范围内

- F2 `lerobot-import` 数据接入算子（共享存储路径为主 + Hub repo id 可选来源）与 Dataset 登记联动
- F1 `lerobot-train` 训练算子（v1 锚点：单卡 ≤24G）
- F3 `lerobot-eval` 仿真评测算子与平台自有指标契约
- 两个镜像（CPU 轻镜像 + GPU 镜像）、三个 job-template 模板注册、一条示例 pipeline

### 1.2 明确不做（排除清单）

| 项 | 处置 |
|---|---|
| F4 边缘分发与指标回流 | 独立后续 spec |
| 真机控制链路（遥操作采集、USB 串口、lerobot-record） | 永不进平台，边缘机本地 |
| π0/π0.5/GR00T 等大 VLA 全量训练 | v2，注明 A100 80G 级卡型要求 |
| Isaac Lab 仿真器 | v2 |
| 多卡 accelerate 分布式训练 | v2 |
| episode 抽帧回传 LabelStudio 标注 | 本期仅画像输出 `videos/` 结构信息，标注联动后置 |
| 真 GPU 集成测试进 CI | CI 无 GPU，列为交付后手工验收清单（§8） |

### 1.3 头脑风暴阶段已定的三项范围决策

1. v1 GPU 锚点为单卡 ≤24G（ACT/Diffusion/VQ-BeT/SmolVLA-LoRA 级）；
2. 仿真器 v1 用 lerobot 原生 gym 环境（gym-pusht / gym-aloha，headless 可跑）；
3. 数据源形态 = 平台共享存储路径为主 + Hub 在线拉取可选（复用 B2/B3 HF mirror 配置模式）。

## §2 架构与交付物

### 2.1 交付物清单

| 层 | 交付物 | 位置 |
|---|---|---|
| 镜像 | `lerobot-import`（CPU：pyarrow/opencv/lerobot dataset 读写，不装 torch） | `images/lerobot/Dockerfile-import` |
| 镜像 | `lerobot-gpu`（CUDA 12.x + lerobot 0.6.2 + gym-pusht/gym-aloha + MuJoCo EGL） | `images/lerobot/Dockerfile-gpu` |
| 算子 | `lerobot-import` 模板（数据接入 + 画像） | `job-template/job/lerobot_import/` |
| 算子 | `lerobot-train` 模板（训练） | `job-template/job/lerobot_train/` |
| 算子 | `lerobot-eval` 模板（仿真评测） | `job-template/job/lerobot_eval/` |
| 平台 | Dataset 类型登记 `file_type='lerobot'`；模板/镜像注册 | `myapp/views/view_dataset.py`、`myapp/init/init-job-template.json`、`myapp/init/init-image.json` |
| 示例 | 端到端 pipeline `lerobot-import → lerobot-train → lerobot-eval` | `myapp/example/pipeline/lerobot-embodied/`（过 `scripts/validate_pipelines.py`） |
| 测试 | 三算子纯函数单测 + 画像/指标契约测试 + view_dataset 识别测试 | `tests/test_lerobot_*.py` |

### 2.2 算子内部结构（复刻 gov-sft 已验证模式）

每个算子目录固定三件套：

```
job-template/job/lerobot_<name>/
  start.py            # argparse 入口；DRYRUN 环境变量短路；subprocess 执行；写 manifest
  <name>_cmd.py       # 纯函数命令组装（单测对象；禁止 import myapp.*，禁止跨算子 import）
  Dockerfile          # 薄层：FROM 两个基础镜像之一，COPY 入口脚本
```

产物约定：输出落统一工作目录 + `manifest.json`（args 全量 + parents 血缘 digest + files 清单），对齐母文档 §7.3 全局设计约定（CLI flag-value 单元素、密钥不进 DAG JSON、算子隔离）。

### 2.3 调度底座

三算子 v1 均为 k8s **batch Job** 单机形态（F1/F3 申请 GPU，F2 纯 CPU）。不引入 PyTorchJob——v1 无分布式语义需求，batch Job 链路最短。资源参数（`gpu_num`/`gpu_type`/`cpu`/`mem`）走平台既有任务表单透传，`gpu_type` 复用 A3 卡型字典 select2。

## §3 F2：`lerobot-import` 数据接入契约

### 3.1 表单参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `source_type` | select2 预设 | `local_path` | `local_path` / `hub_repo_id` |
| `source` | string | — | NFS 路径（`/data/k8s/kubeflow/` 下）或 Hub repo id（如 `lerobot/pusht`） |
| `target_name` | string | — | 登记数据集名称 |
| `target_version` | string | `v1` | 登记数据集版本 |
| `hub_endpoint` | string | 空 | HF 镜像源，仅 `hub_repo_id` 时注入 `HF_ENDPOINT`；空则用 lerobot 默认 |
| `link_mode` | bool | false | 仅 `local_path` 且同盘时生效：软链免拷贝；默认拷贝 |

### 3.2 执行流程

1. 读源目录 `meta/info.json` → 校验格式版本（接受 v2.1 / v3；未知版本显式报错终止）；
2. 规范化拷贝到 `/data/k8s/kubeflow/global/dataset/{target_name}/{target_version}/`（默认拷贝；local_path 同盘可选软链模式参数 `link_mode`，默认 false）；
3. 生成画像 `lerobot_profile.json`：episode 数、总帧数、fps、视频路数与分辨率、动作/状态维度、任务标签分布、视频总时长；
4. 写 `manifest.json`（parent=源路径 digest）+ 在目标目录留 `.cube_dataset_meta`（供平台登记读取，内容 = profile + 版本 + 来源）。

### 3.3 Dataset 登记联动（解耦决策）

**算子不直接写 DB**。任务完成后由用户在数据集管理 UI 走既有「数据集导入登记」链路；`view_dataset.py` 登记识别新增：目录中存在 `.cube_dataset_meta` 且 `format=lerobot` 时，`file_type` 自动置 `lerobot` 并带出画像字段；无该文件时行为不变（降级不报错）。

### 3.4 与 S4 数据探索的兼容（契约锁定项）

LeRobotDataset `data/*.parquet`（状态/动作列）可被既有 dataset_reader 表格读取器直接消费。本兼容性作为**契约测试**锁定（fixture 构造迷你 parquet 目录断言可打开），Data Explorer 对 `file_type='lerobot'` 的入口指向 `data/` 子目录，零改动。

### 3.5 失败语义

- 缺 `meta/info.json` → 报错终止；
- Hub 拉取失败 → 重试 3 次后失败退出（断点续传交 `huggingface_hub` 自身）；
- 目标目录已存在且非空 → 拒绝覆盖（显式 `overwrite=false` 语义，对齐数据集同名同版本拒绝的既有惯例）。

## §4 F1：`lerobot-train` 训练算子契约

### 4.1 表单参数（`lerobot_train_cmd.py` 的输入面）

| 参数 | 类型 | 默认 | 映射到 CLI |
|---|---|---|---|
| `policy_type` | select2 预设 | `act` | `--policy.type=`；预设 act/diffusion/vqbet/smolvla，支持自定义输入透传 |
| `policy_path` | string | 空 | `--policy.path=`（续训/加载预训练权重；与 `policy_type` 互斥，后端校验） |
| `dataset_ref` | select-input | — | `{name}:{version}` 引用 F2 产出；算子翻译为本地路径形态传 `--dataset.repo_id=`（见 §4.3 实测锁定项）|
| `batch_size` | int | 8 | `--batch_size=` |
| `steps` | int | 10000 | `--steps=` |
| `save_freq` | int | 5000 | `--save_freq=` |
| `log_freq` | int | 200 | `--log_freq=` |
| `learning_rate` | string | 空（按策略默认） | `--optimizer.lr=` |
| `resume` | bool | false | `--resume=` |
| `wandb_enable` | bool | **false** | `--wandb.enable=`（内网默认关，指标靠产物解析） |
| `extra_args` | string | 空 | 尾部透传逃生舱；白名单校验：仅允许 `--` 开头 flag，禁含 shell 元字符 |

### 4.2 执行流程与产物

```
start.py:
  1. build(...) → list[str]（flag-value 单元素）
  2. 落 train_cmd.sh；ROBOT_DRYRUN=1 时到此为止
  3. subprocess 执行 lerobot-train ... --output_dir=/mnt/train/{job_name}
  4. 解析 stdout 日志 → 补写 metrics.json
  5. 写 manifest.json
```

产物目录为 lerobot 原生输出（算子不搬迁）：

```
{output_dir}/
  checkpoints/{step}/pretrained_model/   ← F3 评测引用对象
  config.yaml                             ← 超参事实源
  images/、logs/
```

`metrics.json`（算子补写）：`{steps_run, final_train_loss, wall_time_sec, policy_type, dataset_ref}`，loss 曲线自 stdout 解析。

`manifest.json`：`parents=[{dataset 目录 manifest digest}]`（数据集→训练血缘），`files=[config.yaml, metrics.json]`。

### 4.3 关键决策

- **本地数据集传参形态为实测锁定项**：lerobot 0.6.2 对离线目录的支持存在 `--dataset.root=` 与 `repo_id + local-files-only` 两种可能形态，实施计划首个 Task 以镜像内 `lerobot-train --help` + dry-run 实测定死其一，结论回写本 spec 并由 `lerobot_train_cmd.py` 单测锁定 flag 契约。
- **checkpoint 不自动注册模型仓库**：训练与 model_register 解耦，对齐平台「训练→注册」两步走；注册路径进示例 pipeline 演示但不强制。
- **权重加载失败显式报错**：`policy_path` 指向不存在/不可读的权重时在启动前报错，绝不静默回退随机初始化。

## §5 F3：`lerobot-eval` 评测算子与指标契约

### 5.1 表单参数

| 参数 | 类型 | 默认 | 映射到 CLI |
|---|---|---|---|
| `checkpoint` | select-input | — | `--policy.path=`（引用上游 `{output_dir}/checkpoints/{step}/pretrained_model`，或手填 Hub 模型 id） |
| `env_type` | select2 预设 | `pusht` | `--env.type=`；预设 pusht/aloha，自定义透传 |
| `n_episodes` | int | 50 | `--eval.n_episodes=` |
| `batch_size` | int | 10 | `--eval.batch_size=` |
| `seed` | int | 100000 | `--seed=`（评测可复现关键） |
| `video_n_episodes` | int | 3 | 录制视频条数，落 `{eval_dir}/videos/` 供 UI 预览 |

### 5.2 指标契约 schema（平台自有，上游格式隔离层）

`eval_metrics.json`：

```json
{
  "contract_version": "1",
  "source": { "type": "lerobot-eval", "env": "pusht", "n_episodes": 50, "seed": 100000 },
  "policy_ref": { "checkpoint_path": "...", "train_manifest_digest": "..." },
  "metrics": { "success_rate": 0.82, "mean_return": 14.6, "mean_episode_len": 96.3,
               "n_evaluated": 50, "n_success": 41 },
  "artifacts": { "videos": ["eval/videos/ep_0.mp4"], "raw_log": "eval/eval.log" }
}
```

- 消费端对齐 E1「模型指标 JSON」读取口径（指标名+值对 + 维度信息），评测指标可被模型指标可视化直接展示；
- 生产端：算子解析 lerobot-eval stdout 汇总行 + `eval/` 目录产物组装成上述 schema；**解析器与契约分层——上游字段名变化只影响解析器，不影响契约**（各以单测覆盖）。

### 5.3 血缘与启动前校验

- `eval_manifest.json`：`parents=[{训练 manifest digest}]`，串联数据集→训练→评测。
- **策略×环境匹配 = 动作维度启动前校验**（代替静态兼容矩阵）：读 checkpoint config 的 `shape_metadata`/action 维度与环境 action 空间维度比对，不一致在 `subprocess` 拉起前非零退出（错配跑满 episodes 是最贵的失败）。

### 5.4 失败语义

- 渲染缺失：启动自检 MuJoCo EGL 探针，报错文案指向镜像/卡型配置；
- 单 episode 崩溃：lerobot-eval 原生继续，`n_evaluated < n_episodes` 时指标仍产出并记录缺口。

## §6 镜像规格

| 项 | `lerobot-import`（CPU） | `lerobot-gpu` |
|---|---|---|
| 基础 | python:3.11-slim | 本仓库 `images/ubuntu-gpu` 系列 CUDA 12.x 基座 |
| 核心依赖 | `lerobot==0.6.2` dataset 读写最小子集（pyarrow/pandas/opencv）、ffmpeg 只读探测 | `lerobot==0.6.2` 全量 + `gym-pusht` + `gym-aloha` + mujoco |
| 环境变量 | — | `MUJOCO_GL=egl`、`HF_HUB_OFFLINE` 可配 |
| 体积预估 | <2G | 10G+ 级（锁版本，升级走镜像新版本而非 in-place） |
| 登记 | `init-image.json` 两条目，分类归既有类目 | 同左 |

不新增平台类目；三模板注册进 `init-job-template.json` 的「数据工具」（import）与「模型训练」（train/eval）既有类目。

## §7 测试策略（TDD，进 `tests/`，沿用 conftest.py 惰性加载基建）

| 层 | 对象 | 关键用例 |
|---|---|---|
| 纯函数单测 | 三个 `<name>_cmd.py` | flag-value 单元素约定；参数缺省；`policy_type`×`policy_path` 互斥；`extra_args` 白名单（拒 shell 元字符）；`{name}:{version}`→路径翻译 |
| 画像契约 | import profile 生成器 | fixture 迷你 LeRobotDataset v3 目录（parquet+meta json 手工构造，视频 0 字节占位并跳过 header 校验）→ `lerobot_profile.json` 字段完备；未知 meta version 显式报错 |
| 指标契约 | eval 解析器 | fixture stdout 文本变体 → 契约 schema 稳定输出；`n_evaluated < n_episodes` 缺口记录 |
| 校验逻辑 | 动作维度校验、渲染探针 | 维度不一致 → 非零退出且发生在 subprocess 拉起前 |
| 平台侧 | `view_dataset` lerobot 识别 | 有 `.cube_dataset_meta` → `file_type='lerobot'` 带出画像；无 → 降级不报错 |

不测：真 GPU 集成（进 §8 手工清单）；lerobot 上游行为本身。

## §8 手工验收清单（GPU 环境，交付后执行一次）

- [ ] `lerobot/pusht` Hub 数据集导入 → 画像正确；Data Explorer 可打开 `data/*.parquet`
- [ ] ACT×pusht 短训（`steps=200`）→ `metrics.json` 有 loss、checkpoints 产出
- [ ] ACT checkpoint × pusht 评测（`n_episodes=5`）→ `eval_metrics.json` 契约字段齐、视频落盘
- [ ] 错配测试（ALOHA checkpoint × pusht）→ 启动前报错、不拉起训练/评测进程
- [ ] `ROBOT_DRYRUN=1` 三算子均只产 `*_cmd.sh` 不执行
- [ ] 示例 pipeline 端到端跑通并通过 `scripts/validate_pipelines.py`

## 附录 A：各策略起始参数建议表（表单 tip 数据源）

| 策略 | 显存量级（单卡） | 起始 `batch_size` | 备注 |
|---|---|---|---|
| ACT | 2–6G | 8–64 | pusht/aloha 均适用 |
| Diffusion | 4–8G | 32 | pusht 经典组合 |
| VQ-BeT | 2–6G | 64 | |
| SmolVLA（LoRA） | ~24G | 64 | 需拉基础权重，`HF_ENDPOINT` mirror 建议预配 |

起始值以 lerobot 官方示例配置为参考，表格仅作默认值与 tip 提示，不构成硬约束。

## 附录 B：版本锚定与升级策略

- `lerobot==0.6.2` 锁进 `lerobot-gpu` 镜像；CLI flag 面（`--policy.type`、`--eval.n_episodes` 等）以 0.6.2 实测为准，`<name>_cmd.py` 单测即 flag 契约的回归防线。
- 升级路径：新镜像 tag（如 `lerobot-gpu:0.7`）+ 模板镜像参数可选，旧模板默认值不突变；上游格式漂移由 §5.2 解析器/契约分层吸收。
- LeRobotDataset 兼容范围声明：import 算子接受 v2.1/v3，其余显式报错并提示转换。
