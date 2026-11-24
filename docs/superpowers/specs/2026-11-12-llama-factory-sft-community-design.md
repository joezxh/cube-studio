# cube-studio 社区版 LLaMA-Factory 微调镜像与模板设计

> 状态：builder 审阅已完成并回写，待用户批准。本文只描述设计，未改动任何产品代码。
> 适用版本：本仓库 `d:/projects/github/cube-studio` 社区版（2026-11-12 快照）。
> 目标读者：准备按本文实施并提交上游 PR 的工程师，以及希望沿用／扩展该能力的社区用户。

---

## 1 意图与为什么

社区版 `myapp/init/init-job-template.json` 里已有 `llama-factory-sft / -reward / -ppo / -eval` 四个模板条目，但它们只是「商业版占位」：`expand.enterprise=true`、`job_template_args={}`、镜像指向 `python:3.9`、`gitpath=/job-template/job/llama-factory` 对应的代码目录在仓库里并不存在。因此社区用户点开「大模型」分类里的 SFT 模板，得到的是一个跑不起来的空壳。

本次要用 LLaMA-Factory 真正跑通一次微调，并且刻意不做一次性脚本：交付一套**能提交给上游、别人能长期维护**的通用镜像与模板。允许复用仓库里已有的 `gov-social-llm/ops/gov-sft`（它已经把 LLaMA-Factory 封装成「薄算子」），但要剥掉其项目专属部分，使它成为 cube-studio 的一等公民算子。

一句话边界：**镜像只负责把平台参数翻译成 LLaMA-Factory 的配置与命令，不实现训练逻辑、不内置权重；平台负责调度、GPU、挂载、日志、状态与产物登记。**

---

## 2 目标／非目标／反目标

### 目标

1. 社区用户 `myapp init` 后，在「训练 → 任务模板 → 大模型」里能看到一个可直接使用的 `llama-factory-sft`，填表单即可跑 LoRA/QLoRA SFT。
2. 提供一份可直接 `docker build` + `docker push` 的镜像定义，含锁定版本的基础镜像、国内可达策略、调用入口与构建脚本。
3. 定义清晰的数据输入／产物输出契约，使微调结果能被平台现有 `model-register` 与示例 pipeline 承接，并给出指标产物约定（社区版没有自动渲染消费端，见 §3）。
4. 交付一套契约测试，保证「模板参数 ↔ 入口 `argparse`」不会因后续改动悄悄错位。
5. 文档覆盖：全新安装、已部署环境升级、版本升级、多机多卡扩展、三个同族空壳模板的后续路线。

### 非目标（本期明确不做）

- 不重写 `pytorchjob` / `tfjob` / `volcano` launcher；多机多卡复用现成模板。
- 不实现 DPO / PPO / Reward Model / 量化 / 评测算子；`-reward/-ppo/-eval` 三个占位条目保持原样。
- 不在平台后端新增调度逻辑、不改 `view_pipeline.py` / `py_k8s.py` / 数据库模型，**也不补 `/metric.json` 的渲染消费端**。
- 不引入 `gov-manifest` 之类的跨算子私有依赖，不引入服务端 Dockerfile 自动构建。
- 不把模型权重、数据集打进镜像。

### 反目标（技术上跑通也算失败）

- 只有一份 README 和一个示例脚本，没有注册进 `init-job-template.json` 的模板记录。
- 参数表单与 `start.py` 的 `argparse` 不对齐，用户填了某个字段运行时 `exit 2`。
- 用 `hiyouga/llamafactory:latest` 或任何不锁定的 tag；半年后重建镜像得到不同依赖。
- 产物写进容器临时目录而不是共享卷，任务结束后 adapter 丢失。
- 为了「通用」把 gov-sft 的 `/mnt/gov`、政务 manifest、教师模型链路一起搬进社区算子。

---

## 3 约束（均为仓库内已核实的事实）

| 约束 | 依据 | 对设计的影响 |
|---|---|---|
| 模板是 `init-job-template.json` 的一条 JSON，`myapp init` → `create_template()` 写入 `Images` / `job_template` 表 | `myapp/cli.py:122-180` | 新增模板＝改这一个 JSON，不改后端 |
| `create_template()` 对**已存在**的 `job_template.name` 直接 `pass`（更新逻辑被注释） | `myapp/cli.py:148-158,184-189` | 改 JSON 只对全新安装生效；已部署环境必须走页面编辑或 SQL，文档必须写 |
| `enterprise` 只是 `expand` 里的元数据，后端与前端源码均不读取 | 全仓 `enterprise` 搜索仅命中 init JSON 与示例文件 | 去掉它技术上无副作用，属于产品口径决策 |
| 平台把 `task.args` 拍平成 `--flag value`；Python `bool` 真值只发裸 flag；空值跳过；`dict/list` 序列化为 JSON 字符串；`images`/`workdir` 是特例键 | `myapp/views/view_pipeline.py:202-229` | `start.py` 每个模板 flag 都要有 `argparse` 同名项；bool 必须同时接受裸 flag 与带值两种形态（见下行） |
| `validate_task_args()` 对**未出现在** `task.args` 的 flag 原样写入模板 `default`，不做类型转换 | `myapp/utils/py/args_schema.py:271-284` | 字符串 `"false"` 会被渲染成 `--merge false` 两个 token；`action="store_true"` 必然 `exit 2`，必须用 `nargs="?"` + `const` + 字符串布尔解析 |
| `int` 值会执行 `int(value)`，空串抛错并统一变成 "task args is not valid" | `args_schema.py:189-195,286-289`、`myapp/views/view_task.py:214-222` | 允许留空的数值参数必须声明 `type=str` + 空默认，由入口自行解析 |
| 参数类型白名单 `int,bool,str,text,enum,float,multiple,dict,list,file,json`；`bool/int` 的 `default` 在仓库惯例中是字符串 | `args_schema.py:25-47`、`tests/test_lerobot_template_reg.py:84-116` | 参数 schema 不能发明类型；bool 默认值写 `"true"/"false"` |
| 模板 `env` 每行按 `KEY=VALUE` 解析，实现是 `env.split('=')[1]` | `myapp/views/view_pipeline.py:233-238` | **env 值里不能出现等号**，否则被截断 |
| 任务最终是 Argo Workflow 中的一个 container；`command` 来自 `Job_Template.entrypoint`（覆盖镜像 ENTRYPOINT），`args` 来自拍平后的参数 | `view_pipeline.py:279-291,396-421` | Dockerfile 的 `ENTRYPOINT` 仅本地兜底 |
| GPU 走 `Task.resource_gpu` → `nvidia.com/gpu`；默认挂载 `kubeflow-user-workspace(pvc):/mnt`；`{{creator}}` 由 Jinja2 渲染 | `view_pipeline.py:158-169,361-373,538`、`models/model_job.py:541` | 产物路径统一 `/mnt/{{creator}}/...` |
| `install/kubernetes/all_image.py:123-124` 直接从 init JSON 的 `image_name` 生成离线镜像清单 | `install/kubernetes/all_image.py` | 新镜像写进模板记录即自动纳入，无需改该文件 |
| 既有算子会写 `/metric.json`（list of `{metric_type, describe, ...}`），但**社区版没有消费端**：`myapp/` 与 `myapp/vision/` 全目录 0 命中 | 写入方 `job-template/job/demo/launcher.py:55-77`、`xgb/launcher.py:168-171`；`view_pipeline.py:396-400` 的 `outputs.artifacts` 恒为空；`view_workflow.py:398-399` 只透传 Argo 名为 `metric` 的 artifact key | `/metric.json` 仅作兼容既有算子惯例尽力写；真正可查的产物是共享卷 `<output>/metrics.json` + loss 图/表。本期不改后端 |
| `model-register` 算子通过 `KFJ_MODEL_REPO_API_URL` 调 `/training_model_modelview/api/` 登记模型 | `job-template/job/model_register/launcher.py:13-58` | 示例 pipeline 末端可接它 |
| `gov-sft` 的 `build_train_cmd()` 把 `--flag value` 作为**单个** argv 元素，`subprocess.run(list)` 下无法被解析 | `gov-social-llm/ops/gov-sft/sft_cmd.py:27-57` | 复用时改为配置文件驱动，从根本上消除该缺陷 |
| LLaMA-Factory 官方 CLI 除 `webui` 外均接受 YAML 配置文件（`llamafactory-cli train <yaml>`、`llamafactory-cli export <yaml>`） | 官方文档与 `examples/train_lora/*.yaml`、`examples/merge_lora/*.yaml` | 采用配置驱动，表单与 CLI 解耦 |
| `hiyouga/llamafactory:0.9.3` 是已发布的具体 tag（约 16.9 GB）；`0.9.4` 为更新版本 | Docker Hub 镜像索引 | 默认锁 `0.9.3`，升级走换 tag + 回归 |
| 首次登录会把整个 `myapp/example/pipeline/` 拷到用户工作区 `pipeline/example` | `myapp/project.py:159-166`；`myapp/example/pipeline/deepseek/identity.json` 已存在 | 示例数据放进 `myapp/example/pipeline/llamafactory/` 即可被 `{{creator}}` 路径引用 |

---

## 4 方案选择（Approaches）

| 路线 | 做法 | 取舍 | 结论 |
|---|---|---|---|
| **A 锁定版本的官方镜像 + 配置驱动** | `FROM hiyouga/llamafactory:0.9.3`（ARG 可切私有同步镜像）；`start.py` 生成 `dataset_info.json` + `train.yaml`，调 `llamafactory-cli train train.yaml`；表单暴露高频参数，另给 `--train_config` / `--extra_args` 逃生舱 | LLaMA-Factory 升级通常只需换 tag + 回归，不必改模板和入口；上百个超参不被表单锁死。代价：镜像大、国内需同步、版本矩阵要文档化 | **采纳** |
| B 平台自建底座 + 全 flag 命令行 | `FROM .../ubuntu-gpu:cuda12.6-cudnn9-python3.9` + `pip install llamafactory==x`；沿用 gov-sft 逐 flag 拼装 | 国内可直接 build、与平台底座一致；但需自钉 torch/CUDA/transformers/flash-attn/bitsandbytes 矩阵，且 py3.9 可能与新版要求冲突；每加一个超参要改模板 + 入口 + 测试三处 | 未采纳 |
| C 不新建镜像 | 只补 `myapp/example/pipeline/llamafactory/` 脚本，占位条目指向 `pytorchjob` 镜像 | 改动最小，但「换真实镜像、补 args、gitpath」全部落空，没有独立入口与可回归测试 | 未采纳 |

**与占位条目的关系（用户已拍板选 B 方案「填实」）**：直接改造 `llama-factory-sft` 条目——去掉 `enterprise`、换真实镜像、补 `args` 与 `gitpath`、保留 `job_template_old_names: ["llama-factory"]` 做改名迁移。理由是名字最符合社区预期、模板列表最干净。已明确接受的代价：动了商业版标记（上游可能视为越界）、对已部署环境无效（需额外升级说明）、`-reward/-ppo/-eval` 仍是空壳（只在 README 路线图中说明扩展方式，不假装已实现）。

**改动面**：一个自包含的新算子目录 + 一条模板记录 + 一条示例 pipeline + 一个静态示例数据文件 + README/升级说明 + 一组契约测试。不动调度后端。

---

## 5 交付物清单

| 路径 | 内容 |
|---|---|
| `job-template/job/llama_factory/Dockerfile` | 镜像定义（锁定基础镜像 + 薄适配层） |
| `job-template/job/llama_factory/build.sh` | 构建／推送脚本，对齐 `job-template/README.md` 约定 |
| `job-template/job/llama_factory/start.py` | 平台入口：`argparse` → 配置生成 → 训练／合并 → 指标与 manifest |
| `job-template/job/llama_factory/train_config.py` | 纯函数：`dataset_info.json`、`train.yaml`、`export.yaml` 的构造与安全校验 |
| `job-template/job/llama_factory/README.md` | 面向社区用户的使用、参数、数据格式、扩展与排障 |
| `myapp/init/init-job-template.json` | 改写 `llama-factory-sft` 条目（唯一模板注册点） |
| `myapp/init/init-pipeline.json` | 新增一条 `llama-factory-sft-demo` 示例 pipeline |
| `myapp/example/pipeline/llamafactory/identity.json` | 示例训练数据（与已有 DDP 脚本同目录，首次登录自动拷入用户工作区） |
| `docs/superpowers/specs/2026-11-12-llama-factory-sft-community-design.md` | 本文 |
| `job-template/job/llama_factory/UPGRADE.md`（或 README 专节） | 已部署环境的升级／重建说明 |
| `tests/test_llama_factory_template_reg.py` | 模板 ↔ 入口契约测试 |
| `tests/test_llama_factory_train_config.py` | `train_config.py` 纯函数单测 |

算子目录**自包含**：不复制 `job/pkgs`、不 import `gov-social-llm` 任何模块（`gov-manifest`、路径约定、教师链路全部剥离）。

---

## 6 镜像定义

### 6.1 Dockerfile（要点，非最终逐字文本）

```dockerfile
ARG BASE_IMAGE=hiyouga/llamafactory:0.9.3
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    HF_ENDPOINT=https://hf-mirror.com \
    HF_HOME=/mnt/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple

RUN python -m pip install --no-cache-dir "pyyaml==6.0.2"

COPY job/llama_factory /opt/llama_factory
WORKDIR /opt/llama_factory
ENTRYPOINT ["python3", "start.py"]
```

- 基础镜像负责 torch / transformers / peft / trl / accelerate / deepspeed / bitsandbytes / flash-attn 等全部训练依赖，本层只补 `PyYAML`（若基础镜像已含则可省，由 `build.sh` 的 smoke 检查确认；设计上不重装 torch 系依赖）。
- `ENTRYPOINT` 仅用于本地 `docker run` 兜底；平台上 `Job_Template.entrypoint = python3 start.py` 会成为 K8s `command` 覆盖它，`args` 来自表单。
- `WORKDIR` 与模板 `job_template_workdir` 必须一致（`/opt/llama_factory`），否则相对路径启动即失败。
- `HF_HOME` 落在共享卷内以便复用权重缓存；如需按用户隔离，可在模板 env 覆盖为 `/mnt/{{creator}}/.cache/huggingface`。
- 不设 `TORCH_CUDA_ARCH_LIST`：官方镜像已含预编译内核，只有自行编译扩展时才需要（gov-sft 里的设置是为 4090/5090 自编译场景，不属于本通用镜像）。

### 6.2 版本锁定与国内可达

- 默认 `BASE_IMAGE=hiyouga/llamafactory:0.9.3`，**禁止 `latest`**。README 记录该 tag 内实际 `pip freeze` 出的 torch / CUDA / transformers / LLaMA-Factory 版本矩阵，以及验证过的宿主驱动下限。
- 升级路径：换 `ARG` 默认值 → 重新 build 出新 tag → 跑 §12 的 smoke → 更新 README 版本矩阵 → 更新模板 `image_name`。不 in-place 覆盖旧 tag（与 `images/lerobot/Dockerfile-gpu` 的锁定做法一致）。
- 内网／国内拉取：`docker pull` 后 retag 推到 `ccr.ccs.tencentyun.com/cube-studio/llamafactory-base:0.9.3`，构建时 `--build-arg BASE_IMAGE=<私有地址>`；`Repository.hubsecret` 必须覆盖该仓库。
- `install/kubernetes/all_image.py` 会自动从模板 `image_name` 收进离线镜像清单，无需手改 `user_image` 列表。

### 6.3 build.sh

在 `job-template/` 目录执行（与 `job-template/README.md:22-26` 一致，**build context 是 `job-template/`**，因此 `COPY job/llama_factory ...` 不带 `job-template/` 前缀）：

```bash
sh job/llama_factory/build.sh
# 内部：docker build --network=host -f job/llama_factory/Dockerfile \
#   -t ccr.ccs.tencentyun.com/cube-studio/llamafactory:0.9.3-cube1 . && docker push ...
```

镜像名 `ccr.ccs.tencentyun.com/cube-studio/llamafactory:0.9.3-cube1`，tag 表达「上游版本 + 本仓库适配层版本」；后续适配层变更递增 `-cubeN`，上游版本变更改前半段。

---

## 7 模板定义

改写 `myapp/init/init-job-template.json` 的 `llama-factory-sft` 条目，字段：

| 字段 | 值 | 说明 |
|---|---|---|
| `project_name` | `大模型` | 沿用占位条目分类（`myapp/cli.py:115` 预建） |
| `image_name` | `ccr.ccs.tencentyun.com/cube-studio/llamafactory:0.9.3-cube1` | 换掉 `python:3.9`；同时被 `all_image.py` 收录 |
| `image_describe` | `LLaMA-Factory 通用微调镜像（社区版）` | |
| `gitpath` | `/job-template/job/llama_factory` | 指向真实存在的算子目录 |
| `image_expand.icon` | 保留原 `/static/assets/images/job_templates/llama-factory.png` | |
| `job_template_name` | `llama-factory-sft` | 不变 |
| `job_template_old_names` | `["llama-factory"]` | 保留改名迁移 |
| `job_template_describe` | `LLaMA-Factory SFT/LoRA/QLoRA 微调（社区版）` | 去掉「(商业版)」字样 |
| `job_template_version` | `Release` | 非 admin 可见 |
| `job_template_workdir` | `/opt/llama_factory` | 与镜像 WORKDIR 一致 |
| `job_template_command` | `python3 start.py` | 覆盖镜像 ENTRYPOINT |
| `job_template_volume` | `kubeflow-user-workspace(pvc):/mnt/` | 显式声明，`/mnt` 与 `{{creator}}` 路径才成立 |
| `job_template_account` | `""` | 单 Pod 不需要 launcher 类 SA |
| `job_template_env` | `HF_ENDPOINT=https://hf-mirror.com\nHF_HOME=/mnt/.cache/huggingface\nTOKENIZERS_PARALLELISM=false` | 值内不得含 `=`（见 §3） |
| `job_template_expand` | `{"index":5,"rec_job_template":"自定义镜像","help_url":"/job-template/job/llama_factory"}` | **删除 `enterprise`**；`source` 由 `create_template` 注入 |
| `job_template_args` | 见下表 | 参数分组 + schema |

参数分组（键名即容器 argv 的 flag，必须与 `start.py` 的 `add_argument` 逐字一致）：

| 分组 | flag | type | default | 说明 |
|---|---|---|---|---|
| 模型与数据 | `--model_path` | str | `/mnt/{{creator}}/pipeline/example/llamafactory/base` | 底座权重目录（必填） |
| | `--dataset` | str | `/mnt/{{creator}}/pipeline/example/llamafactory/identity.json` | 训练数据文件绝对路径（必填），示例文件见 §5 |
| | `--data_format` | str | `alpaca` | `choice: alpaca / sharegpt`，显式指定，不按文件名猜 |
| | `--dataset_info` | str | `""` | 自备完整 `dataset_info.json` 路径；给定时直接复制，不自动生成 |
| | `--dataset_name` | str | `cube_train` | `dataset_info.json` 中注册名，写进 `train.yaml` 的 `dataset` |
| | `--template` | str | `qwen` | 对话模板，须与底座匹配（describe 给出常见取值） |
| 训练参数 | `--stage` | str | `sft` | `choice: ["sft"]`，v1 明确只支持 SFT；扩展时加 choice + 回归 |
| | `--method` | str | `lora` | `choice: lora / qlora / full`；映射到 `finetuning_type` (+ `quantization_bit 4`) |
| | `--lora_rank` | int | `"8"` | |
| | `--learning_rate` | str | `"1e-4"` | |
| | `--num_train_epochs` | float | `"3.0"` | |
| | `--cutoff_len` | int | `"1024"` | |
| | `--per_device_train_batch_size` | int | `"1"` | |
| | `--gradient_accumulation_steps` | int | `"8"` | |
| | `--bf16` | bool | `"false"` | 两种 argv 形态都可能出现，入口用 `nargs="?"` + `const` + `_bool()`（见下） |
| | `--deepspeed` | str | `""` | 挂载卷内 ZeRO 配置文件路径（单机多卡） |
| | `--max_samples` | str | `""` | 空＝不限制；**用 str 而非 int**，避免空默认触发 `int("")` 校验失败；示例 pipeline 显式给值 |
| 输出与运行 | `--output` | str | `/mnt/{{creator}}/llama_factory/sft` | 产物根目录（必填） |
| | `--merge` | bool | `"false"` | 训练后 `llamafactory-cli export` 合并 LoRA |
| | `--train_config` | str | `""` | 自备完整训练 YAML（逃生舱，优先级见 §8.2） |
| | `--extra_args` | str | `""` | `--flag value` 偶数对，转成 YAML 键 |
| | `--dry_run` | bool | `"false"` | 只生成配置与命令，不启动训练（等价 env `LLF_DRYRUN=1`） |

schema 字段集固定 10 项（`choice/default/describe/editable/item_type/label/placeholder/range/require/type`），与 `tests/test_lerobot_template_reg.py` 的断言一致；`bool/int/float` 的 `default` 一律字符串；`choice` 非空时 `type` 用 `str`。

**bool 的 argv 形态（builder 审阅后修正）**：平台在用户显式勾选时渲染裸 flag `--merge`，在用户未改动、沿用模板字符串默认值 `"false"` 时渲染 `--merge false`。因此 bool 项一律声明为 `nargs="?", const="true", default="false"`，并用 `_bool(value)` 把 `true/1/yes/false/0/no` 统一解析；**禁止 `action="store_true"`**。示例 pipeline 中的 bool 参数写成 JSON 字符串（与 `init-pipeline.json:560-561` 的 `--fp16: "true"` 惯例一致）。

---

## 8 调用与数据契约

### 8.1 `start.py` 行为

1. `argparse` 声明上表全部 flag；bool 项用 `nargs="?"` + `const="true"` + `default="false"` 与 `_bool()` 解析，同时兼容裸 flag 与 `--flag false`（见 §7 末）。
2. 校验：必填项、路径安全性（拒绝 shell 元字符与 `..`）、`--extra_args` 必须为偶数个 token 且 flag 以 `--` 开头、`--train_config` 指向的文件存在且为合法 YAML；`--max_samples` 非空时必须能转成正整数。
3. 在 `--output` 下生成 `dataset_info.json`（按 `--data_format` 显式构造列映射；`--dataset_info` 给定时直接复制）与 `train.yaml`，并写 `train_cmd.sh` 记录最终命令。
4. **dry-run**：跳过训练，仍写 `dataset_info.json` / `train.yaml` / `train_cmd.sh` / `train_manifest.json`，退出 0。
5. 真实模式：`subprocess.run(["llamafactory-cli", "train", str(train_yaml)])`，使用 list 形式、绝不 `shell=True`；stdout/stderr 直接继承，交给 Argo 日志归档。退出码透传。
6. `--merge`：`subprocess.run(["llamafactory-cli", "export", str(export_yaml)])`，导出到 `<output>/merged`。
7. 训练后写 `<output>/metrics.json`（loss 摘要 + loss 序列）、`<output>/train_manifest.json`（血缘）、`<output>/train_cmd.sh`，并**尽力**写 `/metric.json`（兼容既有算子惯例，社区版无消费端，见 §3）。

### 8.2 配置生成与覆盖语义（必须实现成纯函数，便于测试）

`train_config.py` 输出 LLaMA-Factory 官方字段：`model_name_or_path`、`stage`、`do_train`、`finetuning_type`、`lora_rank`、`lora_target=all`、`quantization_bit`（仅 qlora）、`dataset`、`dataset_dir`、`template`、`cutoff_len`、`output_dir`、`per_device_train_batch_size`、`gradient_accumulation_steps`、`learning_rate`、`num_train_epochs`、`bf16`、`deepspeed`、`max_samples`、`save_steps`、`logging_steps`、`plot_loss=true`、`report_to=none`、`overwrite_output_dir=true`。

- `dataset_dir` = `<output>`（与 `dataset_info.json` 同目录），`output_dir` = `<output>/adapter`，避免 checkpoint 与数据注册文件混放。
- `--train_config` 语义：读取用户 YAML 作为基础字典 → **用户文件的键覆盖表单生成的键** → 覆盖完成后强制把 `output_dir`、`dataset_dir` 写回平台计算的值（产物必须落在 `--output` 下，不能被配置改写到容器临时目录）→ 写最终 `train.yaml`。表单中的 `--output`/`--dataset`/`--model_path` 仍用于产物登记与 manifest。
- `--extra_args`：`shlex.split` 后按 `--key value` 成对转成 YAML 键（去掉前导 `--`），在用户文件覆盖之后应用，并在 manifest 中记录，便于复现。
- 不做 shell 拼接；所有值经 `yaml.safe_dump` 写入，避免注入。

### 8.3 数据输入约定

| 输入 | 约定 |
|---|---|
| 底座权重 | `--model_path` 指向共享卷目录（`/mnt/{{creator}}/...`），由 `model-download` 模板或用户自备；镜像内不含权重 |
| 训练数据 | 单个 JSONL/JSON 文件，`--data_format=alpaca` 时列 `instruction/input/output`，`sharegpt` 时列 `conversations`；复杂多数据集交给 `--dataset_info` 自备完整注册 |
| 自备配置 | `--train_config` 指向共享卷 YAML；`--deepspeed` 指向共享卷 ZeRO JSON |
| 示例数据 | `myapp/example/pipeline/llamafactory/identity.json`，首次登录由 `myapp/project.py:159-166` 拷到用户工作区，模板默认值直接指向它 |

### 8.4 产物输出约定

```
<output>/
├── dataset_info.json        # LLaMA-Factory 数据注册
├── train.yaml               # 最终生效的训练配置（含用户覆盖）
├── train_cmd.sh             # 可复现命令
├── adapter/                 # LLaMA-Factory output_dir：adapter / checkpoint / trainer_state.json / training_loss.png
├── merged/                  # --merge 时导出的完整权重
├── metrics.json             # loss 摘要（step/loss 序列 + 最终 loss）
├── loss.csv                 # loss 曲线表（可由 trainer_state.json 生成）
└── train_manifest.json      # 自包含血缘：args、镜像 tag、LLaMA-Factory 版本、产物清单、退出码、时间
```

`/metric.json` 写成一个 list：loss 文本（`metric_type=text`）、`training_loss.png`（`metric_type=image`）、`loss.csv`（`metric_type=table`）。任一可视化文件缺失时降级为纯文本，不得因此让训练任务失败；**它是兼容性输出，社区版后端不读取，文档不得承诺「平台原生可视化渲染」**，可查的指标产物是 `<output>/metrics.json` + loss 图/表。若将来要在 UI 上展示，需要另立一项改动（给 `view_pipeline.py` 增加 artifact 声明并让 `view_workflow.py` 落地），不在本期范围。

`train_manifest.json` 是**自包含最小契约**（不引入 `gov-manifest`）：字段固定为 `op / args / image_tag / lf_version / files / stats / created_at`。大权重文件不做 sha256，避免训练结束后长时间阻塞。

### 8.5 退出码

`0` 成功（含 dry-run）；`2` 参数／配置校验失败；其余透传 `llamafactory-cli` 的返回码，让 Argo 节点正确标红并可重试。

---

## 9 与平台现有组件的衔接

| 组件 | 衔接方式 |
|---|---|
| 模板注册 | 改 `init-job-template.json` → `myapp init` → `create_template()` 建 `Images(image_type=job-template)` 与 `Job_Template`；`job_template_old_names` 兼容旧名 `llama-factory` |
| 镜像管理 | 镜像由 `build.sh` 线下 build/push；已部署环境需在「训练 → 仓库／镜像」登记，或重跑 init；`Repository.hubsecret` 覆盖目标仓库，`view_pipeline.py` 汇总成 `imagePullSecrets` |
| 离线镜像清单 | `all_image.py` 自动读 `image_name`，无需改动 |
| 任务调度 | 无需新代码：Argo Workflow 单 Pod，`command=python3 start.py`、`args=<拍平参数>`、`image=<模板镜像>`、`workingDir=/opt/llama_factory`；定时调度复用 `Pipeline.schedule_type=crontab` |
| GPU | 用户在任务上填 `resource_gpu`（如 `1`），平台注入 `nvidia.com/gpu` 与 `gpu-type` nodeSelector；单机多卡在容器内由 `--deepspeed` 或 `FORCE_TORCHRUN` 承担 |
| 存储 | 模板 `job_template_volume=kubeflow-user-workspace(pvc):/mnt/`；`{{creator}}` 由 Jinja2 渲染；产物落 `/mnt/{{creator}}/...` |
| 环境变量 | 模板 env + `KFJ_*` / `K8S_*` 平台注入；`HF_ENDPOINT` 走 hf-mirror；env 值禁含 `=` |
| 日志与状态 | stdout 直接进 Argo `archiveLogs` → MinIO；退出码决定节点状态；`watch_workflow.py` 回写 `RunHistory` |
| 结果可视化 | 兼容性写 `/metric.json`（社区版无消费端）；可查产物是共享卷 `<output>/metrics.json` + `training_loss.png` + `loss.csv`；README 明确这一现状 |
| 模型管理 | 示例 pipeline 末端接 `model-register`，`--model_path` 指向 `<output>/merged`（或 adapter 目录），`--model_metric` 取 `metrics.json` 摘要 |
| 分布式扩展 | README 指向 `pytorchjob` 模板 + **同一镜像** + `myapp/example/pipeline/llamafactory/pytorch-ddp.sh` / `deepspeed.sh` 的 `WORLD_SIZE/RANK/GPU_NUM → torchrun` 逻辑；本期不重写 launcher |

---

## 10 已部署环境的升级／重建（B 方案的必付成本）

`create_template()` 对同名记录 `pass`，所以**只改 JSON 对已跑过 `myapp init` 的环境无效**。文档必须给出三条路径并明确推荐：

1. **推荐：页面编辑**。「训练 → 任务模板」找到 `llama-factory-sft`，按 §7 逐项改：`images`（先在「镜像」页登记新镜像）、`describe`（去掉「(商业版)」）、`workdir`、`entrypoint`、`volume_mount`、`args`（整段参数 JSON）、`env`、`expand`（去掉 `enterprise` 键，`help_url` 指向新目录）。改完在模板详情页确认参数分组出现、镜像名正确。
2. **批量：SQL**。`UPDATE job_template SET ... WHERE name='llama-factory-sft'`，同步在 `images` 表插入新镜像记录并修正 `images_id`；`args`/`env`/`expand` 是文本列，需写入合法 JSON 字符串。附完整语句与回滚备份提示。
3. **全新安装**：无需操作，`myapp init` 自动生效。

明确不推荐「删掉模板记录再 init」：`task.job_template_id` 外键会让已有 pipeline 悬空。

---

## 11 示例 pipeline

在 `myapp/init/init-pipeline.json` 新增 `llama-factory-sft-demo`，三节点 DAG（`create_pipeline()` 要求所有 `job_templete` 都已存在，否则整条 pipeline 被跳过；下列三个模板在开源版均存在）：

```
model-download  →  llama-factory-sft  →  model-register
(拉小底座)          (LoRA SFT)          (登记 merged 权重)
```

- `model-download`：`--from=huggingface`、`--model_name=Qwen/Qwen2.5-0.5B-Instruct`、`--save_path=/mnt/{{creator}}/pipeline/example/llamafactory/base`；小模型保证单卡 smoke 可跑，社区用户可自行替换为更大底座并调整 `resource_gpu`。
- `llama-factory-sft`：`resource_gpu=1`、`resource_memory=40G`、`volume_mount=kubeflow-user-workspace(pvc):/mnt`，`--model_path`/`--dataset`/`--output` 全部使用 `/mnt/{{creator}}/...`，`--template=qwen`、`--max_samples="100"` 便于快速验证；bool 参数写成字符串（如 `"--merge": "true"`）。
- `model-register`：`--model_path=<output>/merged`、`--model_name`、`--model_version`、`--framework`、`--model_metric`、`--describe`、`--project_name`。
- 训练数据来自 §5 新增的静态 `myapp/example/pipeline/llamafactory/identity.json`（目录已存在，内含 DDP 示例脚本）；**不设数据准备节点、不依赖 `deepseek` 示例目录**，三节点 DAG 与 §7 的 `--dataset` 默认值一致。

pipeline 条目结构（`pipeline` + `tasks` + `dag_json` + `expand`）照抄 `init-pipeline.json` 现有 `deepseek` 条目形态，字段名不要发明。

---

## 12 契约测试与验收

### 测试

`tests/test_llama_factory_template_reg.py`（对齐 `tests/test_lerobot_template_reg.py`）：

- `llama-factory-sft` 条目存在、`job_template_name`/`gitpath`/`job_template_command`/`image_name`/`workdir` 符合 §7；
- `expand` 中**不含** `enterprise`，`job_template_old_names` 保留；
- 模板所有 flag 与 `start.py` 的 `add_argument` 双向对齐（AST 静态提取，不执行模块）；
- 每个参数 schema 字段集为固定 10 项，`bool/int/float` 的 default 为字符串；
- **bool flag 的 `add_argument` 必须同时含 `nargs` 与 `const`**（不能是 `store_true`），并有回归用例覆盖 `--merge`（裸 flag）与 `--merge false`（字符串）两种 argv 形态都能解析；
- **可留空的数值参数（如 `--max_samples`）必须 `type=str` + 空默认**，防止 `int("")` 校验失败；
- `job_template_volume` 含 `kubeflow-user-workspace(pvc):/mnt`；`env` 每行值不含 `=`。

`tests/test_llama_factory_train_config.py`：

- alpaca / sharegpt 两种 `dataset_info.json` 结构；
- `lora/qlora/full` 到 `finetuning_type` + `quantization_bit` 的映射；
- `--train_config` 覆盖后 `output_dir`/`dataset_dir` 仍被强制写回；
- `--extra_args` 奇数 token、非 `--` 开头、含 shell 元字符全部拒绝；
- `--max_samples` 空值不写入 YAML，非空时写成整数；
- dry-run 不调用 `subprocess`（monkeypatch），产物文件齐全；
- 生成的 YAML 可被 `yaml.safe_load` 读回，且包含必需键。

运行：`pytest tests/test_llama_factory_template_reg.py tests/test_llama_factory_train_config.py -v`（`pytest.ini` 已配置本地 `--basetemp`）。

### 验收标准

1. `pytest` 两组全绿。
2. `sh job/llama_factory/build.sh` 能产出镜像；`docker run --gpus all <image> --dry_run --output /tmp/x ...` 生成完整配置且退出 0（验证裸 bool flag 形态）；另跑一次带 `--dry_run false` 的命令，验证带值形态也能保存任务参数并退出 0。
3. 全新安装 `myapp init` 后，模板详情页能看到参数分组、真实镜像、无「(商业版)」描述；打开任务表单直接保存（不修改任何默认值）不报 "task args is not valid"。
4. 在单卡节点跑通示例 pipeline：adapter 与 merged 权重落到 `/mnt/{{creator}}/...`，`<output>/metrics.json` 有内容，`model-register` 登记成功；`/metric.json` 存在但不作为 UI 渲染验收项。
5. 按 §10 在一份模拟「已部署」环境上完成页面升级，模板可用。

---

## 13 社区沿用与扩展

README 至少覆盖：

- 快速开始（三步：推镜像 → 注册／init → 填表单跑示例 pipeline）；
- 参数表与 `data_format` 数据样例（alpaca / sharegpt 各一段最小 JSON）；
- 产物目录与 `metrics.json` / `train_manifest.json` 字段说明，以及「社区版没有 `/metric.json` 渲染消费端」的现状；
- 换底座、换数据、加超参（优先 `--train_config` / `--extra_args`，不必改模板）；
- 升级 LLaMA-Factory 版本的流程（换 tag → smoke → 更新版本矩阵 → 换模板 `image_name`）；
- 单机多卡（`--deepspeed`）与多机多卡（`pytorchjob` + 同镜像 + 示例脚本）的分工；
- 三个同族占位模板 `-reward/-ppo/-eval` 的现状说明：本期仍是空壳，后续可在同一镜像上通过 `--stage` 与 `export/eval` 配置扩展，不在本期实现；
- 排障：env 值不能含 `=`、bool 参数两种 argv 形态、可留空数值参数为何用 str、`{{creator}}` 与 `/mnt` 挂载、镜像国内同步、驱动／CUDA 版本核对、已部署环境模板不会自动更新。

---

## 14 本次会话已定的决定

**用户决定**：填实 `llama-factory-sft`（去 enterprise、换真实镜像、补 args/gitpath、保留 old_names）；选实现路线 A；复用 `gov-sft` 思路；目标是上游可合并、长期可维护；接受「已部署需升级说明」「三个空壳暂不齐」两项代价。

**我提出并经用户默认认可的决定**：v1 只做单 Pod 内多卡，多机多卡指向 `pytorchjob`；示例任务用小底座 + `identity.json` 并接 `model-register`；三个空壳保持不动只在 README 写路线图；升级说明写成文档章节而非连库脚本；算子目录名 `llama_factory`、workdir `/opt/llama_factory`、镜像 tag `0.9.3-cube1`；算子自包含、不依赖 `gov-manifest`；产物落共享卷并写 `/metric.json`。

**builder 审阅后我补定的决定（请批准时一并核对）**：

1. bool 参数一律 `nargs="?"` + `const` + `_bool()`，禁用 `store_true`；示例 pipeline 中 bool 写 JSON 字符串。原因是模板字符串默认值会被渲染成 `--flag false`，前者两种形态都能解析。
2. `--max_samples` 从 `int + 空默认` 改为 `str + 空默认`，入口自行解析；避免 `int("")` 让任务表单无法保存。
3. 示例数据改为新增一个静态 `myapp/example/pipeline/llamafactory/identity.json`，模板默认路径同步改到已存在的 `llamafactory/` 目录；三节点 DAG 不变，不依赖 `deepseek` 示例目录，也不设数据准备节点。
4. **指标可视化降级为兼容性输出**：社区版 `myapp/` / `myapp/vision/` 无 `/metric.json` 消费端，`view_pipeline.py` 的 `outputs.artifacts` 恒空；因此保留尽力写 `/metric.json` 的惯例，但把 `<output>/metrics.json` + loss 图/表定为可查产物，README 不承诺 UI 渲染。补渲染消费端需要改 `view_pipeline.py`，与「不动调度后端、上游易合并」的目标冲突，故不纳入本期。

---

## 15 留给实施者的部分

以下几项由实施者在编码阶段自行敲定并写进 README，不影响方案选择，无需再回头确认：

- 基础镜像 `0.9.3` 内实际的 torch/CUDA/transformers 版本矩阵，以及是否已自带 PyYAML（决定 `RUN pip install` 去留）；
- `train.yaml` 中 `save_steps` / `logging_steps` / `warmup_ratio` 等次要默认值；
- 参数表单 `label` / `describe` / `tip` 的具体中文文案与分组顺序；
- 契约测试中「允许只出现在 `start.py`、不出现在模板」的 flag 白名单；
- README 的排版、`identity.json` 的具体条目数、`model-register` 节点各参数的最终取值；
- 升级章节里 SQL 语句的逐字文本（须与部署时实际表结构核对后给出）。
