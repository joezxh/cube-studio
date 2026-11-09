
# 一、CubeStudio 平台功能全景

## 1.1 总体判断

CubeStudio 是云原生一站式 AI 平台（MLOps + MaaS + 算力调度 + 训推），入口在 [README.md](file:///d:/projects/github/cube-studio/README.md)。后端为 Flask AppBuilder 架构（[myapp/views/](file:///d:/projects/github/cube-studio/myapp/views)），训练算子模板集中在 [init-job-template.json](file:///d:/projects/github/cube-studio/myapp/init/init-job-template.json)（共 118 个模板），示例 Pipeline 链路在 [myapp/example/pipeline/](file:///d:/projects/github/cube-studio/myapp/example/pipeline)（49 条，含 llamafactory/deepseek/qwen/megatron/safety-eval 等）。

**一个关键事实（对社会治理项目影响最大）**：通过解析 `init-job-template.json` 中每个模板的 `enterprise` 标记，确认以下大模型模板**均标注为商业版（enterprise=True），且其模板代码目录（如 `/job-template/job/llama-factory`、`/job-template/job/llm-distillation`）在开源仓库中不存在**：

> `llama-factory-sft / reward / ppo / eval`、`llm-distillation`（数据蒸馏和知识蒸馏）、`llm-quantization`、`llm-prune`、`opencompass`、`llm-evaluation`、`llm-safety-eval`、`llm-benchmark`、`mindformers`、`label-studio`（模板）、`aihub-register/inference`、`markdown-to-qa`

同时 [view_inferenceserving.py#L175](file:///d:/projects/github/cube-studio/myapp/views/view_inferenceserving.py) 中服务类型明确列出：开源可用 `serving（自定义）/ tfserving / torch-server / triton-server`，而 `ml-server(商业版) / vllm(商业版) / vllm-distributed(商业版) / ollama(商业版)`。**即：开源版的大模型微调、蒸馏、量化、剪枝、vLLM 推理都需要自行补齐实现或采购商业版**，这是后续所有方案设计的核心约束。

## 1.2 功能矩阵

| 功能模块 | 能力说明 | 支持形式 | 对应目录/配置 | 社会治理场景用途 | 缺口/需确认 |
|---|---|---|---|---|---|
| 用户与权限 | SSO（OID/LDAP/REMOTE_USER）、RBAC、多租户、项目组隔离、菜单/接口权限 | Web 管理 + 配置 | [security.py](file:///d:/projects/github/cube-studio/myapp/security.py)、[view_user_role.py](file:///d:/projects/github/cube-studio/myapp/views/view_user_role.py)、[view_team.py](file:///d::/projects/github/cube-studio/myapp/views/view_team.py) | 政法/信访/公安等多部门分权分域，数据按项目组隔离 | 直接可用；对接政务统一身份认证需确认协议类型 |
| 算力调度 | 多集群/多资源组、vGPU/整卡/共享、RDMA(IB/RoCE)、binpack 策略、昇腾/海光/寒武纪/沐曦/摩尔线程/昆仑芯 | K8s + Volcano + 设备插件 | [install/kubernetes/](file:///d:/projects/github/cube-studio/install/kubernetes)（volcano、gpu、sa-rbac、scheduler-policy-config.json）、[view_k8s.py](file:///d:/projects/github/cube-studio/myapp/views/view_k8s.py)、[view_total_resource.py](file:///d:/projects/github/cube-studio/myapp/views/view_total_resource.py) | 30B 教师推理与 2B 学生训练错峰复用同一算力池 | 直接可用；信创芯片具体型号驱动需按节点验证 |
| 计量计费/资源限额 | 项目组/用户/任务多级资源限额、账单 | Web + 配额参数 | [view_task.py](file:///d:/projects/github/cube-studio/myapp/views/view_task.py)、README 算力调度节 | 控制多委办局 GPU 用量 | 直接可用 |
| 存储管理 | NFS/CephFS/MinIO/OSS 等存储盘 Web 注册并挂载到 notebook/pipeline/服务 | PV/PVC | [pv-pvc-*.yaml](file:///d:/projects/github/cube-studio/install/kubernetes)、minio 部署、[view_k8s.py](file:///d:/projects/github/cube-studio/myapp/views/view_k8s.py) | 案卷/笔录/音视频证据的统一下发路径 `/mnt/$username` | 需规划政务数据的存储分级与备份策略 |
| 在线开发 | JupyterLab/VSCode/RStudio Notebook、多 Python 环境、SSH remote、TensorBoard、环境保存 | Notebook 实例 | [view_notebook.py](file:///d:/projects/github/cube-studio/myapp/views/view_notebook.py)、[images/jupyter-notebook/](file:///d:/projects/github/cube-studio/images/jupyter-notebook) | 算法人员在线做数据处理、蒸馏 prompt 调试 | 直接可用 |
| 镜像能力 | 镜像仓库、在线构建、自定义镜像注册 | Docker 管理 | [view_docker.py](file:///d:/projects/github/cube-studio/myapp/views/view_docker.py)、[view_images.py](file:///d:/projects/github/cube-studio/myapp/views/view_images.py)、[install/docker/](file:///d:/projects/github/cube-studio/install/docker) | 构建 kev/llama-factory 等自定义训练镜像的关键入口 | 直接可用 |
| 数据管理 | 数据集上传/管理（图片/音频/文本）、一键探索 | 数据集模块 | [view_dataset.py](file:///d:/projects/github/cube-studio/myapp/views/view_dataset.py)、[model_dataset.py](file:///d:/projects/github/cube-studio/myapp/models/model_dataset.py)、`dataset` 算子 | 承载评测集/蒸馏产出/训练集的版本化样本库 | 数据集"版本管理"粒度需确认（见第三节） |
| 数据地图/SQLLab | 元数据表、指标、维表、多引擎交互查询（MySQL/PG/CK/Hive/达梦） | SQL 查询模块 | [view_sqllab.py](file:///d:/projects/github/cube-studio/myapp/views/view_sqllab.py)、[view_metadata.py](file:///d:/projects/github/cube-studio/myapp/views/view_metadata.py)、[view_dimension.py](file:///d:/projects/github/cube-studio/myapp/views/view_dimension.py) | 对接政务工单库/事件库，抽取事件文本构造语料 | 直接可用 |
| 数据标注 | 图/文/音/多模态标注、草稿-审核-打分角色流、大模型自动化标注 | LabelStudio 集成（模板标注为商业版） | `label-studio` 模板（enterprise=True）、README 数据标注节 | 矛盾纠纷文本标签体系、事件类别标注 | **开源仓库中标注模板代码缺失，需部署社区版 LabelStudio 或采购** |
| 文本处理算子 | `nlp-clean-data`、`nlp-filter-data`、`nlp-replace-private-data`（隐私脱敏）、`nlp-analyze-data`、`question-generation`、`question-answer-generation`、`question-answer-extension` | 开源 Pipeline 算子 | [job-template/job/pkgs/](file:///d:/projects/github/cube-studio/job-template/job/pkgs)、init-job-template.json（enterprise=None） | **低数据量场景核心**：清洗、脱敏、问答对扩充生成训练语料 | 开源可直接用；`markdown-to-qa` 为商业版 |
| 图像/音视频算子 | 质量评估、增强、视频抽帧、音频抽取（yolov8、paddleocr、kaldi、voice、media、video-audio） | 开源 Pipeline 算子 | [job-template/job/video-audio/](file:///d:/projects/github/cube-studio/job-template/job/video-audio)、example/pipeline 各目录 | 监控截图、接处警录音的预处理 | 直接可用 |
| Pipeline 编排 | 拖拉拽 DAG、定时调度、补录、并发/超时、全局常量、结果可视化、暂停恢复 | Argo/KFP 类工作流 | [view_pipeline.py](file:///d:/projects/github/cube-studio/myapp/views/view_pipeline.py)、[view_workflow.py](file:///d:/projects/github/cube-studio/myapp/views/view_workflow.py)、[install/kubernetes/argo/](file:///d:/projects/github/cube-studio/install/kubernetes/argo)、[job-template/job/](file:///d:/projects/github/cube-studio/job-template/job) | 把"蒸馏→过滤→训练→评估→注册→部署"固化为可复跑生产线 | 直接可用，是本方案的主编排引擎 |
| 传统 ML/DL 训练 | sklearn/ray-sklearn/xgb/lightgbm 等 20+ 算法、tfjob/pytorchjob 分布式、volcano/ray | 开源算子 | [job-template/job/pytorch/](file:///d:/projects/github/cube-studio/job-template/job/pytorch)、xgb、ray 等 | 风险预警的表格类基线模型（与 LLM 互补） | 直接可用 |
| 分布式加速 | megatron/deepspeed/colossalai/horovod/mpi | 开源模板（enterprise=None） | init-job-template.json、[example/pipeline/](file:///d:/projects/github/cube-studio/myapp/example/pipeline) 对应目录 | 30B 教师多卡推理/2B 学生全参微调 | 直接可用 |
| 超参搜索 | NNI / Ray 自动调参 | 开源 | [view_nni.py](file:///d:/projects/github/cube-studio/myapp/views/view_nni.py)、`hyperparameter-search-*` | 学生模型 lr/lora_r 搜索 | 直接可用 |
| 模型管理 | 模型多版本、指标、注册、离线推理、格式转换 | 开源 | [view_train_model.py](file:///d:/projects/github/cube-studio/myapp/views/view_train_model.py)、`model-register`/`model-evaluation`/`model-convert`/`model-offline-predict` | 蒸馏 checkpoint、学生模型版本归档 | `model-evaluation` 面向传统模型，LLM 评测需扩展 |
| 推理服务 | 零代码发布、灰度/分流/限流/滚动升级/回滚、弹性伸缩、JWT | 开源 serving 体系 | [view_inferenceserving.py](file:///d:/projects/github/cube-studio/myapp/views/view_inferenceserving.py)、[images/serving/](file:///d:/projects/github/cube-studio/images/serving) | 小模型 API 化供调解辅助/事件识别系统调用 | **vLLM/Ollama 为商业版；开源需以自定义镜像 serving 方式自装 vLLM**（模板支持任意启动命令/端口/健康检查） |
| 大模型网关 | 统一入口、秘钥、QPS/TPS 限速、token 限额、流量监控 | README 载明 | 配置于 [myapp/config.py](file:///d:/projects/github/cube-studio/myapp/config.py) 体系 | 多部门调用 LLM 的配额与审计 | 开源/商业归属需确认 |
| 智能对话/知识库 | 多场景对话、提示词模板、私有知识库 RAG、安全问答检测 | chat 模块 | [view_chat.py](file:///d:/projects/github/cube-studio/myapp/views/view_chat.py)、[model_chat.py](file:///d:/projects/github/cube-studio/myapp/models/model_chat.py)、init-chat.json | 调解政策问答、知识库辅助判断 | 需确认开源版完整度 |
| AIHub 模型市场 | 400+ 预训练模型一键部署/开发/微调 | aihub | [view_aihub.py](file:///d:/projects/github/cube-studio/myapp/views/view_aihub.py)、init-aihub.json | 快速取用中文底座模型 | README 注明"需购买 aihub" |
| 监控告警 | Prometheus/Grafana 资源与服务监控、workflow 状态推送（企微/钉钉/飞书）、webhook | 开源 | [install/kubernetes/prometheus/](file:///d:/projects/github/cube-studio/install/kubernetes/prometheus)、[tasks/](file:///d:/projects/github/cube-studio/myapp/tasks)、tools/watch_workflow.py | 模型上线后的延迟/错误率告警 | 直接可用；LLM 业务质量监控需自建 |
| 国产化适配 | 昇腾 910B/310P、海光 DCU、寒武纪、沐曦、摩尔线程；ARM64 全栈；达梦/人大金仓/OceanBase；信创离线部署 | 开源 | README 国产化节、[install/kubernetes/](file:///d:/projects/github/cube-studio/install/kubernetes) | 政务内网信创环境落地 | MindIE/NPU 版 llama-factory 等开箱件多属商业版，需按采购清单核对 |

---

# 二、社会治理模型微调手册（低数据量 + 30B→0.8B/2B 蒸馏）

## 2.1 场景任务定义

| 任务 | 输入 | 输出形式 | 验收归属 |
|---|---|---|---|
| T1 社会治理事件分类 | 工单/舆情/笔录文本 | 事件类别标签（如纠纷类型、风险等级） | 分类指标 |
| T2 风险预警识别 | 描述文本 + 结构化要素 | 风险等级 + 依据要点（生成式或判别式） | 分类 + 生成双指标 |
| T3 矛盾纠纷调解辅助 | 案情描述 | 争点抽取、适用政策要点、调解建议（受约束 JSON） | 生成质量 + 安全合规 |
| T4 事件要素识别 | 案情文本 | 时间/地点/主体/行为 实体与关系（结构化抽取） | 抽取 F1 |

**建议**：T1/T2/T4 做成判别式短输出任务（同时是 Jev-like 决策模型的天然形态，见第六节），T3 做受格式约束的生成任务。四类任务共用同一蒸馏生产线，仅 Prompt 模板与输出 schema 不同。

## 2.2 数据准备（1000–2000 条评测数据的正确用法）

在训练数据少的约束下，**评测集是锚，蒸馏数据是量**：

1. **评测集切分**：将 1000–2000 条按 7:3 切成"开发评测集（≈600–1400 条，迭代中反复使用，教师也会见过其题材分布但不含原文）"与"盲测验收集（≈400–600 条，全程封存，仅最终验收用）"。盲测集必须人工复核标注质量。
2. **训练种子**：从业务库（SQLLab 对接工单/事件库）抽取 200–500 条**不带答案**的原始案情文本作为蒸馏 prompt 种子——训练标签完全由教师模型生成，评测标签保持人工标注，避免同源污染。
3. **数据增强（按优先级）**：
   - 教师改写增广：同一案情让 30B 教师做同义改写/视角变换（申诉人视角↔调解员视角），生成多样输入；
   - 平台开源算子：`question-generation`、`question-answer-generation`、`question-answer-extension` 把案情扩充为 QA 对；`nlp-clean-data`/`nlp-filter-data` 清洗过滤；`nlp-replace-private-data` 脱敏姓名/证件号/地址；
   - 回译与口语化扰动（Notebook 内脚本即可）。
   - 目标：种子 200–500 条 → 蒸馏指令集 5k–20k 条。
4. **禁止事项**：不要用被评测的同一批样本直接生成训练数据（泄漏）；不要假设教师输出天然正确（必须过滤）。

## 2.3 教师模型使用（约 30B）

- **部署**：30B FP16 约需 60–70GB 显存 → 单节点 2×A100-80G/H800，或用 vGPU 池化的多卡；显存受限时用 AWQ/GPTQ 4bit（约 16–20GB，单卡可跑）。开源版通过自定义镜像 serving（内置 vLLM）发布为 OpenAI 兼容接口；若采购商业版则直接用 `vllm(商业版)` 服务类型。
- **Prompt 构建**：每类任务写一个模板（系统提示 + 输出 JSON schema + 2–3 个 few-shot），模板文件放 NFS 数据集目录统一管理，平台"智能对话/提示词模板"功能可做版本化调试。
- **蒸馏数据生成**：Pipeline 编排"自定义镜像算子"批量调教师接口，采样温度 0.7、每条种子生成 3–5 个候选。
- **质量过滤（自蒸馏三道闸）**：
   1. 格式闸：JSON schema 校验，不合规直接丢弃；
   2. 一致性闸：同一种子多候选间标签投票（self-consistency），多数一致才保留高置信样本；
   3. 抽检闸：人工对每任务≥100 条生成结果打分，教师在该任务上的可用率 <85% 时先修 prompt 再放量。

## 2.4 学生模型训练（0.8B–2B）

| 方式 | 适用 | 平台落地路径 |
|---|---|---|
| LoRA/QLoRA SFT（**首选起步**） | 数据少、迭代快、单卡可训 Qwen3-1.7B/0.8B | 开源路径：自定义镜像装 LLaMA-Factory，`pytorchjob` 模板或"自定义镜像"算子跑训练；商业路径：`llama-factory-sft` 模板 |
| 全参数 SFT | 蒸馏数据 >10k 且 LoRA 饱和后 | `pytorchjob` + DeepSpeed Ze2（开源模板可用） |
| 知识蒸馏（logit/在线 KD） | 需要教师软标签进一步提精 | 平台 `llm-distillation` 为**商业版**且代码不在开源仓库；开源需自写 KD 脚本（如 MiniLLM/Distiller 思路）打成自定义镜像 |

**推荐路线**：先用 LoRA SFT 在蒸馏数据上跑通全链路拿到基线，再视指标决定是否上全参/KD。0.8B 与 1.7B（或 2B 档 Qwen 系）各训一版对比——0.8B 边缘部署占优，1.7B 复杂调解生成占优。超参用 `hyperparameter-search-ray` 搜 lr(1e-4~2e-4)、lora_r(16/32/64)、epoch(2~4)。

## 2.5 评测指标体系

| 维度 | 指标 | 测法 |
|---|---|---|
| 分类质量 | Accuracy / P / R / **macro-F1**（类别不平衡必须看 macro） | 盲测集脚本评测 |
| 风险预警 | 高危样本召回率（漏报比误报代价高，单独设阈值指标） | 混淆矩阵 |
| 抽取任务 | 实体/要素 F1 | 脚本 |
| 生成质量 | 要点覆盖率、格式合规率、事实一致性（抽样人工双评 + 教师当 judge） | 抽检 |
| 拒答/安全 | 拒答率（越权诉求应拒）、有害输出率、隐私泄漏率 | 建 50–100 条红队样本，复用 `safety-eval` 示例链路思路 |
| 性能 | P50/P95 延迟、吞吐、显存占用、单卡并发 | 压测脚本 + 平台服务监控 |
| 对照 | 同题下 教师 30B 得分 = 能力上限参考 | 评测集先跑教师 |

评测执行：开源版用"自定义镜像"算子在 Pipeline 中跑（装载 eval 脚本 + 盲测集），结果以 JSON/表格输出到 Pipeline 可视化节点；商业版直接 `llm-evaluation`/`opencompass`/`llm-benchmark`。

## 2.6 部署与上线

1. 学生模型经 `model-register` 注册版本（附评测指标）；
2. 推理服务：0.8B/1.7B 单卡即可（含 vGPU 共享切片），以自定义镜像 serving（vLLM 或 transformers + FastAPI）发布，配置健康检查、端口、JWT 认证；
3. 灰度：平台原生支持随机分流/header 分流 + 流量复制——先 10% 流量灰度，对照旧规则引擎基线；
4. 监控：QPS/延迟/错误率走 Prometheus 告警到企微/钉钉；建议再加业务层抽样回流（见 4.3）；
5. 回滚：多版本滚动升级机制，模型地址切换即回滚，保留最近 2 个版本。

## 2.7 验收标准（建议初值，与业务方确认后固化）

- T1 事件分类：盲测 macro-F1 ≥ 0.85，且不低于教师得分 90%；
- T2 风险预警：高危召回 ≥ 0.92，误报率 ≤ 15%；
- T3 调解辅助：格式合规 ≥ 99%，人工评审"可用+良好"≥ 80%，事实性错误 ≤ 3%；
- T4 要素抽取：F1 ≥ 0.85；
- 安全：红队样本违规输出 ≤ 1%，隐私泄漏 0；
- 性能：单卡 A800/910B 上 P95 ≤ 800ms（判别类 ≤ 200ms），满足并发目标；
- 相对 30B 教师：整体质量保留率 ≥ 90% 且推理成本 ≤ 1/10，方视为蒸馏成功。

---

# 三、模型压缩与蒸馏方案（平台能力复用与新建）

**已有可复用（开源仓库内直接可用）**：
- Pipeline 编排（Argo）作为蒸馏生产线骨架：种子导入 → 教师生成 → 三级过滤 → 格式转换 → 学生训练 → 评测 → 注册 → 部署，全部节点化、可复跑、可定时增量；
- `pytorchjob`/`deepspeed`/`megatron` 训练算力；`hyperparameter-search-ray/nni` 调参；
- `nlp-clean-data / nlp-filter-data / nlp-replace-private-data / question-*` 文本算子做语料加工；
- `model-download` 拉 Qwen 底座（支持 HF/魔搭镜像，注意其 `HF_ENDPOINT=hf-mirror` 环境变量，政务内网需换私有 registry）；
- `model-register` + 自定义镜像推理服务 + 灰度分流 + 监控告警完成交付；
- Notebook 做 prompt 调试与过滤脚本开发。

**开源版缺失、需自建或采购**：

| 缺口 | 自建方案（推荐） | 采购商业版 |
|---|---|---|
| `llm-distillation` 蒸馏算子（代码目录不在仓库） | 自定义镜像封装：调教师 API 生成 + self-consistency 投票过滤 + Alpaca/ShareGPT 格式导出，注册为 pipeline 算子 | 商业版含数据/知识蒸馏 |
| LoRA SFT 一键模板 | 自定义镜像内置 LLaMA-Factory（开源），配 `pytorchjob` 启动；README 亦载明 npu/dcu/沐曦版 llama-factory（归属商业版需确认） | `llama-factory-sft` 等 |
| 量化（GPTQ/AWQ） | 自定义镜像跑 `llmcompressor`/`auto_gptq`，产出作为学生部署档；平台 `model-convert` 仅传统模型格式转换 | `llm-quantization` |
| 剪枝/蒸馏到 0.8B 的结构压缩 | 低数据量场景**建议以"教师造数据 + 小底座直接 SFT"替代权重级剪枝**（剪枝对 <2B 模型收益有限且工具链不成熟），把剪枝列为二期 | `llm-prune` |
| vLLM 服务类型 | 自定义镜像 serving（任意启动命令/端口），完全可在开源版承载 vLLM | 原生 vllm 服务类型 |
| OpenCompass/安全评测 | 自定义镜像 + 评测脚本 + Pipeline 可视化输出 | `opencompass`/`llm-safety-eval`/`llm-benchmark` |

压缩链路总结：**30B 教师（API）→ 蒸馏指令数据 5k–20k → Qwen 0.8B/1.7B LoRA SFT → 盲测验收 →（可选）AWQ 4bit 量化部署**。1000–2000 条评测数据在四个节点使用：①教师能力摸底（决定哪些任务可蒸）；②蒸馏过滤的校准抽检集；③训练中的开发评测；④盲测验收。

---

# 四、高质量数据集全生命周期管理方案

覆盖文本/音频/图片/视频，全部依托平台现有件组合实现：

| 生命周期环节 | 平台模块 | 落地方式 |
|---|---|---|
| 数据接入 | SQLLab/数据地图、`datax`/`datax-import` 算子、数据集上传、`model_download` 式外部拉取 | 工单库→平台表；图片音视频经 NFS/MinIO 挂载路径拷入；huggingface/魔搭数据集导入 |
| 存储 | 存储盘管理（NFS/CephFS/MinIO/OSS）+ 项目组绑定挂载 | 统一 `/mnt/...` 路径规范：`/data/gov/{raw,annotated,distill,eval,archive}/{task}/{version}` |
| 清洗/脱敏 | `nlp-clean-data`、`nlp-filter-data`、`nlp-replace-private-data`、图像质量/音频清理算子 | 做成 Pipeline 标准前置段，输出带质量报告（`nlp-analyze-data`） |
| 标注 | LabelStudio 集成（开源需自行部署社区版对接；商业版含模板）+ 大模型自动化标注预标 | 模型预标 → 人工校对，效率提升 3–5 倍，正适合小种子数据扩标 |
| 审核 | 标注平台角色流（草稿/审核员核定/质量打分）；蒸馏数据三道过滤闸（格式/一致性/人工抽检） | 审核记录留存 |
| 版本管理 | 数据集模块 + 路径级 version 目录约定 + Pipeline 实例绑定数据集版本 | **平台数据集版本粒度需确认**（见第七节），存储层以目录+manifest.json 兜底 |
| 质量评估 | `nlp-analyze-data`、`vision-quality-assessment`、`audio-quality-assessment`；评测集分数曲线 | 每版数据集出质量报告卡 |
| 权限控制 | 项目组隔离 + RBAC + 存储盘组绑定 + Notebook/任务挂载控制 | 敏感案卷仅限"政法组"命名空间可见 |
| 隐私合规 | 脱敏算子强制前置 + 盲测集准入审查 + JWT/接口审计 | 内网闭环，禁公网出口 |
| 备份 | NFS 快照 / MinIO 纠删码 + `datax` 反向导出 + Pipeline 定时备份任务 | 每日增量、每周全量 |
| 训练/评测/推理路径管理 | Pipeline 全局常量定义 `DATA_ROOT`，任务输入输出传递；服务配置文件挂载 | 三类任务统一引用数据集注册项，禁止散路径硬编码 |

---

# 五、阶段化工作计划

| 阶段 | 目标 | 任务拆解 | 所需数据 | 算力/环境 | 平台能力 | 交付物 | 验收指标 | 风险/待确认 |
|---|---|---|---|---|---|---|---|---|
| P0 平台能力调研（1–2 周） | 摸清可用能力边界 | 部署/登录平台；核对开源 vs 商业版模板清单；验证 GPU/vGPU、NFS/MinIO 挂载；跑通 1 条示例 pipeline | — | 1 测试节点 | 全模块 | 《能力核对表》《环境就绪单》 | pytorchjob 示例任务成功运行 | **enterprise 模板的代码目录不在开源仓库**——确认商业授权范围 |
| P1 场景与任务定义（2 周） | 冻结 T1–T4 任务规格 | 与业务方定义标签体系、输出 schema、验收标准初值；写 prompt 模板 v1 | 现有案件样本 50–100 条传阅 | CPU | Notebook、智能对话（prompt 调试） | 任务规格书、标注规范、prompt v1 | 业务方签字 | 标签体系是否需上级标准 |
| P2 评测数据准备（3–4 周） | 建立金标评测集 | 1000–2000 条整理→预标→人工审核→切分开发/盲测集；红队样本 50–100 条 | 全部评测数据 | CPU + 标注环境 | 数据集、LabelStudio、脱敏/质量算子 | 评测集 v1（含盲测封存件） | 标注一致率(Kappa)≥0.8 | 标注平台开源可用性 |
| P3 教师模型蒸馏（3 周） | 教师能力摸底 + 蒸馏数据生产线 | 部署 30B 教师；跑教师盲测摸底；建 Pipeline：种子→生成→三级过滤→5k–20k 指令集 | 200–500 条种子文本 | 2×80G 或 4×40G（教师） | 自定义镜像 serving、pipeline、自定义算子 | 教师评估报告、蒸馏指令集 v1 | 教师 macro-F1 基线确立；过滤后数据抽检可用率≥90% | 教师显存/内网模型来源 |
| P4 小模型训练（2–3 周） | 得到 0.8B/1.7B 学生 | Qwen 底座导入→LoRA SFT→超参搜索→0.8B vs 1.7B 对比 | 蒸馏指令集 | 1–2×40G/卡（学生） | model-download、pytorchjob、deepspeed、NNI/Ray 调参、自定义镜像 LLaMA-Factory | 学生模型 2 版 + 训练报告 | 开发集分数接近教师 | llama-factory 开源版自行打包 |
| P5 模型压缩与评估（2 周） | 达标验收 + 部署档 | AWQ/GPTQ 量化；盲测集终验；延迟压测；安全红队测试 | 盲测集（解封一次） | 1 卡 | 自定义压缩镜像、pipeline 评测节点、safety-eval 示例 | 盲测报告、量化模型 | 第 2.7 节全部指标 | 盲测不可反复解封（防过拟合） |
| P6 推理服务部署（1–2 周） | 上线对外 API | model-register→serving 发布→JWT→灰度 10%→分流监控→回滚预案 | — | 1 卡（0.8B 可 vGPU） | 模型管理、推理服务、灰度/分流、网关（如启用） | 生产 API + 上线报告 | 灰度期 P95/错误率达标 | vLLM 服务类型商业版限制→自定义镜像绕过 |
| P7 运维监控与迭代（持续） | 效果不退化 | 线上样本回流→季度增量蒸馏→重训新版本→滚动升级；badcase 周报 | 回流新样本 | 复用训练池 | Prometheus/Grafana、告警推送、workflow 定时调度 | 月度运维报告、模型 v1.1+ | 复评不低于首版指标 | 回流数据的隐私审查责任 |

---

# 六、"Jev like 模型训练"支持结论

**1. 平台本身：不支持，仓库中无任何依据。** 全库检索 `jev / kev / jaredpalmer` 均无命中（仅前端 lock 文件哈希噪音）。CubeStudio 未内置 Jev-like 决策模型的定义、模板或训练代码。

**2. "Jev like"含义已核实（非不明表述）**：Jev 是闭源商业"系统 1 决策模型"API（不做文本生成，对一组类型化问题输出概率分布）；[jaredpalmer/kev](https://github.com/jaredpalmer/kev) 是其 Apache-2.0 开源复刻——Qwen 底座 + LoRA 适配器 + **指针头（pointer head）**，提供 `kev.train` / `kev.serve`（`/v1/systemone` 接口），模型家族覆盖 0.5B/0.6B/0.8B/4B/9B/27B。其技术本质是"PyTorch/PEFT 训练脚本 + 自定义头 + OpenAI 兼容服务"，**这恰好落在 CubeStudio 的通用训练与自定义服务框架内**，因此可整合。

**3. 基于现有功能的整合方案（推荐，全开源路径）**：
1. **镜像**：用平台在线镜像构建（[view_docker.py](file:///d:/projects/github/cube-studio/myapp/views/view_docker.py)）打一个 kev 镜像（`uv sync` + 依赖 + 内网 base 模型预置到私有 registry/NFS）；
2. **训练**：`pytorchjob` 模板或"自定义镜像"算子执行 `python -m kev.train --data train.jsonl --base Qwen/... --init_from kev-0.8b`，多卡时走已有 torchrun/DeepSpeed 通道；训练数据即第二节的蒸馏产物（choice/score/noul 类型化问题格式，与社会治理 T1/T2 判别任务天然吻合——工单分派、是否升级、情绪打分正是 system-one 决策形态）;
3. **评测**：kev 仓库自带 `evals` 协议，打包进自定义评测算子，与盲测集并联;
4. **交付**：`model-register` 注册 → 自定义镜像 serving 启动 `python -m kev.serve --port ...`，暴露 `/v1/systemone` + OpenAI 兼容端点 → 灰度/分流/回滚沿用平台机制;
5. **与 LLM 生成链路互补**：0.8B kev 档做实时决策分派，第二节蒸馏出的 1.7B 生成档做调解建议，两路服务由大模型网关/推理服务统一治理。

**风险提示**：kev 的指针头不在 LLaMA-Factory 等通用微调框架支持范围内，**不能**用 `llama-factory-sft` 直接替代；必须走"自定义镜像 + 自有训练脚本"路线，且需在内网验证 kev 依赖（uv、peft 版本）可达性。

---

# 七、风险与待确认事项

**风险**
1. **开源/商业边界**：蒸馏、量化、剪枝、LLM 评测、label-studio 模板、vLLM 服务、AIHub 均标 `enterprise=True` 且模板代码不在本仓库——若只持开源版，第三节所列自建工作量（约 3–4 人周镜像与算子开发）不可回避。
2. **教师天花板**：30B 教师在专业社会治理语料上的上限若不足（P3 摸底 macro-F1 <0.85），学生永远追不上，需考虑更大教师或换底座。
3. **小数据过拟合**：蒸馏数据由教师生成，分布单一，学生可能只学会教师口癖；靠种子多样化 + 盲测把关。
4. **信创硬件**：昇腾/DCU 上 vLLM/LLaMA-Factory/kev 适配版本多属商业支持范围，需逐卡型验证。
5. **合规**：案卷/录音涉敏，盲测集与回流数据的脱敏审查责任主体需明确。

**待确认问题（需要业务方/平台方回答后方案才能定稿）**
1. 贵方持有的是**开源版还是商业授权版**？是否包含 `llm-distillation / llama-factory / vllm serving / label-studio / opencompass`？
2. 30B 教师具体是哪个模型（Qwen2.5-32B？DeepSeek？），是否允许量化后单卡部署？
3. 可用 GPU 清单：卡型、卡数、是否信创卡、是否支持 RDMA？
4. 1000–2000 条评测数据的任务分布与标签质量现状（是否已人工复核）？
5. 平台数据集模块是否需要跨版本追溯/血缘（若是，需评估自研 manifest 机制的工作量）？
6. 推理延迟与并发 SLA（决定 0.8B 还是 1.7B、是否量化）？
7. Jev-like 需求是否即"工单分派/风险打分型 system-one 决策"？若是，kev 的 `questions{department/escalate/frustration}` 范式可直接映射，建议 P4 阶段并行做一版 kev-0.8B 对照实验。
8. 是否需要我下一步把 P0–P2 的任务拆解成平台内可直接导入的 Pipeline 示例 JSON / 自定义算子代码骨架，可以继续。