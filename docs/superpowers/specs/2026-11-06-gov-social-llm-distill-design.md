# 社会治理大模型蒸馏与微调 — 技术方案设计（gov-social-llm）

- 日期：2026-11-06
- 状态：已与需求方逐节确认（§1 架构、§2 算子与编排、§3 血缘/兼容/验收/kev/计划）
- 平台基线：cube-studio 开源版（本仓库），交付物置于独立顶层目录 `gov-social-llm/`，与上游零交叉

---

## 0. 背景与设计输入（已确认事项）

| # | 输入 | 结论 |
|---|---|---|
| 1 | 平台版本 | **仅开源版**，不含商业版模板 `llm-distillation / llama-factory / vllm serving / label-studio / opencompass`（已核实：`myapp/init/init-job-template.json` 中上述模板 `enterprise=True` 且模板代码目录不在开源仓库；`myapp/views/view_inferenceserving.py` 服务类型标注 vllm/ollama 为商业版） |
| 2 | 教师模型 | **Qwen3.8-27B**，允许量化后单卡部署（AWQ-INT4） |
| 3 | GPU | 两套备选环境，方案必须**同时**能在「单节点 2×4090-48G」与「单节点 2×5090-32G」上完整跑通 |
| 4 | 评测数据 | 1000–2000 条，任务分布与标签质量**优秀（已人工复核）** |
| 5 | 数据集血缘 | **需要跨版本追溯/血缘**，自研 manifest 机制（工作量约 1 人周） |
| 6 | SLA | 并发 5–20；据此默认 FP16 服务档，量化作备份档；模型规模双臂对比 0.8B / 1.7B |
| 7 | Jev-like 需求 | 确认即「工单分派/风险打分型 system-one 决策」；kev（jaredpalmer/kev，Apache-2.0）的 `questions{department/escalate/frustration}` 范式直接映射，P4 并行做 kev-0.8B 对照实验 |
| 8 | 交付范围 | 全景设计（P0–P7）+ **P0–P2 实物交付**（可导入 Pipeline JSON、自定义算子代码骨架）；P4 kev 实验属全景设计 |
| 9 | 网络 | 可联外网（hf-mirror / GitHub / PyPI 直连），无离线物料流程 |
| 10 | 实现路线 | **方案 A：薄算子 + 标准开源框架**（并按方案 C 预留二期 logit-KD 插槽，本期不实现） |

目标：以 27B 教师蒸馏出面向社会治理（T1 事件/工单分类、T2 风险预警、T3 矛盾纠纷调解辅助、T4 事件要素抽取）的 0.8B–1.7B 学生小模型，并在 cube-studio 开源版上以纯自建薄算子跑通「数据 → 蒸馏 → 训练 → 评测 → 部署 → 迭代」全链路。

---

## 1. 整体架构与交付物布局

### 1.1 端到端架构

```
┌─ 存储层 ─────────────────────────────────────────────────┐
│ /mnt/gov/  (NFS/MinIO 存储盘, 项目组=社会治理)             │
│   ├── eval/    金标评测集(dev 明文 + blind 只读封存)        │
│   ├── seeds/   蒸馏种子(无答案案情文本)                    │
│   ├── distill/ 教师生成原始数据 → 过滤后指令集(vN+manifest) │
│   └── models/  底座权重 / checkpoint / 量化产物             │
└──────────────────────────────────────────────────────────┘
┌─ 算力层(单节点二选一) ────────────────────────────────────┐
│ 卡0: gov-teacher-serve  Qwen3.8-27B-AWQ vLLM  OpenAI API  │
│ 卡1: gov-sft / gov-kev 训练 + gov-eval 评测(错峰)          │
│ 生产期: 卡0/卡1 各挂一个学生推理服务(并发 5–20)             │
└──────────────────────────────────────────────────────────┘
┌─ 编排层 ─ cube-studio Pipeline(Argo) ─────────────────────┐
│ P0 核验线 │ P1 评测集线 │ P2 蒸馏线 │ P4 训练评测线 │ P6 部署线 │
└──────────────────────────────────────────────────────────┘
```

### 1.2 交付物目录（本仓库新建）

```
gov-social-llm/
├── README.md                     # 总览 + 导入/注册操作手册
├── docs/
│   ├── task-spec/                # T1–T4 标签体系与输出 JSON schema、kev questions 映射表
│   └── prompts/                  # 教师蒸馏 prompt 模板(含 few-shot)、judge 模板
├── ops/                          # 6 个自定义算子代码骨架(每个=一个可 build 的镜像应用)
│   ├── gov-distill-gen/          #   {Dockerfile, start.py, requirements.txt}
│   ├── gov-distill-filter/
│   ├── gov-sft/                  #   封装标准开源 LLaMA-Factory
│   ├── gov-kev/                  #   封装 jaredpalmer/kev (Apache-2.0)
│   ├── gov-eval/
│   └── gov-manifest/             #   manifest 生成/血缘校验 + 共享库 lib
├── serving/
│   └── gov-teacher-serve/        #   27B-AWQ 部署参数包(deploy-service args + 健康检查)
├── pipelines/                    # P0–P2 可导入 Pipeline 示例 JSON(平台 {pipeline,tasks} 格式)
│   ├── gov-p0-env-check.json
│   ├── gov-p1-eval-build.json
│   └── gov-p2-distill-line.json
└── scripts/                      # 本地自检: pipeline JSON schema 校验、算子干跑单测
```

### 1.3 三条设计原则

1. **算子=镜像，平台=调度**：每个 `ops/*` 自带 Dockerfile；构建推送 registry 后，经平台「镜像管理」+「模板自定义」注册为 Pipeline 算子（参数类型用平台原生 int/float/json/select-input 等）。
2. **数据只走 `/mnt` 路径 + manifest**：算子间以 JSONL/JSON 文件传递；每个产出目录必带 `manifest.json`（§3.1）。
3. **两套 GPU 环境同构**：所有镜像版本与 args 以「2×4090-48G 或 2×5090-32G 任一可完整跑通」为硬约束（§3.2）。

### 1.4 非目标（YAGNI）

- 本期不做 logit 级在线知识蒸馏（二期插槽 `ops/README.md` 登记 `gov-kd-logits`，仅当 P4 蒸馏保留率 <90% 时启用）；
- 本期不做权重级剪枝（<2B 模型剪枝收益有限，工具链不成熟）；
- 不修改 cube-studio 上游任何代码；
- P4–P7 只出 Pipeline JSON 设计稿，不交付实物。

---

## 2. 算子接口与 Pipeline 编排

### 2.1 统一接口契约

- 镜像入口 `python start.py --参数…`（与平台「自定义镜像」模板 `job_template_command` 一致）；
- 输入/输出一律为 `/mnt/gov/...` 下 JSONL 文件 + `manifest.json`；
- 退出码 0=成功，非 0 时 Pipeline 实例标红并可重试；
- 每个产出目录由共享库 `ops/gov-manifest/lib` 自动写 manifest。

### 2.2 算子清单与参数

| 算子 | 关键参数 | 资源 | 输入 → 输出 |
|---|---|---|---|
| **gov-teacher-serve**（deploy-service 参数包，非算子） | `--model /mnt/gov/models/Qwen3.8-27B-AWQ --max-model-len 8192 --gpu-mem-util 0.85 --tp 1`；健康检查 `/health`；OpenAI 端点 `:8000/v1` | 1 GPU（AWQ 16–18G 权重+KV，32G/48G 单卡均可） | 底座权重 → 集群内教师服务地址 |
| **gov-distill-gen** | `--seeds <jsonl> --task T1..T4 --prompt-version vN --n-candidates 3 --temperature 0.7 --top-p 0.95 --endpoint <教师地址> --resume` | CPU 2核/4G | `seeds/T*/v*/seeds.jsonl` → `distill/T*/v{N}/raw.jsonl`（每行含 seed_id、候选输出、生成参数、教师响应元数据）+ `gen_report.json`；并发信号量限流、断点续跑 |
| **gov-distill-filter** | `--raw <jsonl> --schema docs/task-spec/schemas/T*.json --consistency-k 2 --max-len 4096` | CPU | `raw.jsonl` → 三闸过滤（①JSON schema 硬校验 ②同种子多候选多数投票一致性 ③长度/重复/异常规则）→ `train_alpaca.jsonl`（LLaMA-Factory 用）+ `train_sharegpt.jsonl` + `kev_format.jsonl`（systemone questions 格式）+ `filter_report.json`（各闸通过率、标签分布） |
| **gov-sft**（封装开源 LLaMA-Factory） | `--base /mnt/gov/models/Qwen3-{0.6B,1.7B} --dataset <jsonl> --method lora\|qlora --lora-r 32 --lr 1e-4 --epochs 3 --seq-len 4096 --merge --output /mnt/gov/models/students/{exp}/v{N}` | 1 GPU（1.7B LoRA 峰值≈20G；QLoRA<16G 兜底） | 指令集 vN → 学生模型目录 + `train_manifest.json`（数据集 manifest 摘要 + 底座权重摘要 + 超参） |
| **gov-kev**（封装 jaredpalmer/kev） | `--train-data <kev_format.jsonl> --base Qwen3-0.6B --init-from kev-0.8b --epochs 2 --lr 2e-5 --output /mnt/gov/models/students/kev-{exp}/v{N}` | 1 GPU（<16G） | kev 格式指令集 → LoRA+指针头 checkpoint；同镜像内置 `python -m kev.serve`（`/v1/systemone`），供 P6 部署 |
| **gov-eval** | `--endpoint <服务> 或 --model-path <本地>`；`--eval-set /mnt/gov/eval/{dev,blind}/v*/`；`--tasks T1,T2,T3,T4`；`--redteam <jsonl>`；`--judge <教师地址,可选>`；`--bench`；模式：dev/blind/smoke/safety/bench | CPU；`--bench` 时 1 GPU | → `metrics.json`（macro-F1、高危召回、格式合规率、拒答率、红队违规率、事实一致性抽检分、P50/P95、显存）+ `report.md` + echart JSON（平台原生表格/echart 结果可视化） |
| **gov-manifest** | 子命令 `generate <dir>` / `verify <dir> --parents` / `seal <dir>` | CPU | 目录 → manifest.json；`seal` 输出只读+封存标记 |

二期预留：`gov-kd-logits` 插槽接口继承 `gov-sft` 输入契约，本期不实现。

### 2.3 Pipeline 编排（平台 `{pipeline, tasks}` 导入格式）

全局约定：`pipeline.global_env` 设 `DATA_ROOT=/mnt/gov`；task 的 `volume_mount` 用项目组绑定存储盘（形如 `gov-nfs(pvc):/mnt`，与仓库 `init-pipeline.json` 中 deepseek 示例同构）；`job_templete` 引用注册后的算子名；训练线的前置步骤固定插入 `gov-manifest verify`。

**gov-p0-env-check（平台核验线，1 天）**
`python 自检算子(nvidia-smi/挂载/磁盘/driver)` → `deploy-service 拉起 gov-teacher-serve` → `gov-eval --smoke(10 条打通 API)`
出口判据：smoke metrics 全绿，自动生成《环境就绪单》。

**gov-p1-eval-build（评测集线，第 2–3 周）**
`dataset 导入(eval 原始)` → `nlp-replace-private-data 脱敏(开源算子)` → `python eval-split(7:3 分层切分 + 红队抽样 50–100 条, 开源 python 算子)` → `gov-manifest seal(blind 只读封存)`
出口判据：dev/blind/redteam 三份 manifest 落盘；Kappa≥0.8 复核记录入 `docs/`。

**gov-p2-distill-line（蒸馏线，第 3–5 周）**
`dataset 导入(seeds)` → `nlp-clean-data + nlp-filter-data(种子筛 ≤500)` → `gov-eval(教师摸底: 27B 跑 dev 集, 确立各任务天花板)` → ⛔ **人工闸门：某任务教师 macro-F1<0.85 → 修 `docs/prompts` 模板后重跑，不放量** → `gov-distill-gen(放量 5k–20k)` → `gov-distill-filter(三闸)` → `gov-manifest(指令集 v1)`
出口判据：filter_report 终态通过率≥80%、标签分布与评测集偏差达标；产出三格式指令集。

P4 线（`gov-sft` 双臂 + `gov-kev` 对照 + `gov-eval` 三方对照，dev 集内迭代）与 P6 线（`model-register` → 服务发布 → 灰度）本期只出 JSON 设计稿。

---

## 3. 血缘机制、双环境兼容、验收与 kev 实验

### 3.1 数据集 manifest / 血缘（自研，≈1 人周）

血缘链：**评测集 → 种子 → 蒸馏 raw → 指令集 → 训练 → 模型 → 部署**，每环一份 `manifest.json`，由共享库 `ops/gov-manifest/lib`（约 300 行）被所有算子自动写入。Schema：

```json
{
  "dataset": "distill/T1/v1",
  "producer": {"op": "gov-distill-filter", "image": "…:tag", "git_commit": "…", "args": {}},
  "parents": ["seeds/T1/v1/manifest.json@sha256:…"],
  "files": [{"path": "train_alpaca.jsonl", "sha256": "…", "rows": 12345}],
  "stats": {"label_dist": {}, "gate_pass_rate": {}, "masked": true},
  "sealed": false
}
```

规则：
- `gov-sft`/`gov-kev` 的 `train_manifest.json` 记录数据集 manifest 摘要 + 底座权重摘要 → 线上模型可反查训练数据与超参；
- `verify`：比对 parents 摘要与现存文件（防漂移/篡改），训练与终验前置必跑；
- `seal`：blind 集切分后立即封存（权限只读 + `sealed:true`）；任何算子读 blind 目录须在自己的 manifest 中留痕；P5 终验**只解封一次**并记录解封事件；
- 权限/隐私：脱敏算子强制在血缘链入口；敏感子目录用平台项目组存储盘绑定隔离（治理办组可读 seeds，评审组账号才可读 blind）。

### 3.2 两套 GPU 环境统一兼容策略

| 项 | 2×4090-48G (sm_89) | 2×5090-32G (sm_120) | 设计决策 |
|---|---|---|---|
| vLLM 镜像 | 老版本即可 | 需 cu128 新版本系（Blackwell 支持） | **统一取支持 Blackwell 的较新版本，双环境同一镜像 tag** |
| 教师 27B | BF16 TP=2 可行但占满 | BF16 放不下 | **统一 AWQ-INT4 单卡**（16–18G 权重 + KV，`--gpu-mem-util 0.85`，8k ctx，32G 足够） |
| 并行模式 | 卡0 教师 / 卡1 训练评测 | 同左 | 蒸馏放量期教师独占双卡批跑、训练错峰（Pipeline 定时调度控制） |
| 学生 1.7B LoRA | ~20G ✅ | ~20G ✅ | 默认 LoRA；QLoRA(<16G) 作显存兜底档 |
| 镜像 CUDA 架构 | — | — | 统一 `TORCH_CUDA_ARCH_LIST="8.9;12.0"`，CUDA≥12.8、torch≥2.7；宿主机 5090 需驱动 ≥570（P0 就绪单核对项） |
| 生产推理 | 1.7B-FP16 单卡并发 20 | 同 | 默认 FP16；AWQ 量化为边缘/挤兑备份档（P5 `--bench` 数据定夺） |

### 3.3 评测与验收流水线

- **P2 教师摸底（dev 集）**：确立各任务天花板；不过 0.85 闸门则修 prompt 不放量；
- **P4 学生迭代（仅 dev 集）**：最多 5 轮迭代预算（防盲测过拟合）；每轮产出三方对照表（教师 / 0.8B / 1.7B / kev），echart/表格节点固化在 Pipeline 实例；
- **P5 盲测终验（解封一次）**，验收线（与业务方已定初值）：
  - T1 分类、T4 抽取：macro-F1 ≥ 0.85 且 ≥ 教师得分 90%；
  - T2 风险预警：高危召回 ≥ 0.92，误报率 ≤ 15%；
  - T3 调解辅助：格式合规 ≥ 99%，人工「可用+良好」≥ 80%，事实性错误 ≤ 3%；
  - 安全：红队违规输出 ≤ 1%，隐私泄漏 = 0，拒答行为符合规范；
  - 性能：并发 20 下 P95 判别类 ≤ 200ms、生成类 ≤ 800ms；
  - 蒸馏总目标：质量保留率 ≥ 90% 且推理成本 ≤ 教师 1/10。
- 指标口径全部收敛于 `gov-eval` 单一算子（dev/blind/smoke/safety/bench 五模式），保证唯一实现。

### 3.4 kev-0.8B 对照实验（P4 并行支线）

kev = jaredpalmer/kev（Apache-2.0，可商用）：Qwen 底座 + LoRA + 指针头的 system-one 决策模型，`/v1/systemone` API，一次前向对类型化问题输出概率分布。映射：

| kev question | kev 类型 | 映射任务 | 定制内容 |
|---|---|---|---|
| `department` | choice | T1 工单分派 | 委办局选项与 criteria 描述按标签体系定制 |
| `escalate` | noul | T2 是否紧急人工介入 | 判据 = 风险预警高危标准 |
| `frustration` | score | T3 当事人情绪烈度 | 档位映射调解策略选择 |

- 数据：`gov-distill-filter` 第三路输出 `kev_format.jsonl`（state + 类型化 questions + 教师判定），零额外教师调用成本；
- 训练：`gov-kev` 镜像 `git clone kev → uv sync --extra serve`，底座 Qwen3-0.6B/0.8B 权重经 model-download 思路预取至 `/mnt/gov/models`；
- 评测：同一 blind 集对比 **准确率、校准误差 ECE、P95 延迟**；
- 裁决规则：kev 档 acc ≥ 生成式学生 −2pp 且 P95 ≤ 其 1/3 → T1/T2 生产采用 `kev.serve`；否则维持生成式学生，kev 结果入档作二期参考；
- 约束提醒：kev 指针头不在 LLaMA-Factory 支持范围，必须走「自定义镜像 + kev 自有训练脚本」，不可用 `gov-sft` 替代。

### 3.5 执行计划（全景，约 10 周至首次上线）

| 阶段 | 周期 | 人日 | 关键任务 | 交付物 | 出口判据 |
|---|---|---|---|---|---|
| P0 平台核验+算子开发 | 第1–2周 | 算法3 + 平台1 | 6 算子骨架+Dockerfile 构建、3 条 Pipeline JSON 编写并导入、p0 线实跑、GPU 驱动/CUDA 核对 | `gov-social-llm/` 全套骨架、镜像入 registry、算子注册完成 | p0 线全绿，就绪单签发 |
| P1 评测集工程化 | 第2–3周 | 数据2 | 1000–2000 条导入→脱敏→7:3 切分→红队抽样→blind 封存 | dev/blind/redteam 三 manifest | Kappa≥0.8 记录、seal 成功 |
| P2 教师摸底+蒸馏 | 第3–5周 | 算法2 | 27B-AWQ 拉起、dev 摸底过闸、放量 5k–20k、三闸过滤 | 指令集 v1（三格式）+ filter_report | 通过率≥80%、分布校验达标 |
| P4 学生训练+kev | 第5–7周 | 算法3 | gov-sft 双臂(0.8B/1.7B)、gov-kev 对照、平台超参搜索(Ray/NNI)搜 lr/lora_r/epoch | checkpoint ×3 + train_manifest | dev 集达教师 90% |
| P5 终验+压缩 | 第7–8周 | 算法1 | blind 解封终验、AWQ 量化备份档、bench 压测 | 盲测报告、量化档 | §3.3 验收线全过 |
| P6 部署 | 第8–9周 | 平台1 | model-register、vLLM/kev.serve 自定义 serving 发布、JWT、10% 灰度分流 | 生产 API | 灰度期 P95/错误率达标 |
| P7 运维迭代 | 第10周起 | 持续 | badcase 回流→季度增量蒸馏→重训→滚动升级/回滚 | 月报、模型 v1.1+ | 复评不低于首版 |

P3 已并入 P2/P4 行（蒸馏与训练为连续迭代，不再单列周块）。

---

## 4. 风险登记

1. **5090 vLLM 兼容**：Blackwell 消费卡对 vLLM/torch 版本敏感，P0 第 1 天先行验证（p0 线 smoke 节点即为此设）；
2. **教师天花板**：27B 在专业治理语料上的 dev 集得分若 <0.85，学生无法达标——P2 人工闸门强制先修 prompt/换 few-shot，仍不达标则升级讨论更大教师；
3. **小数据分布单一**：蒸馏数据全出自同一教师口癖——以种子多样化（≥500 条不同题材）、self-consistency 过滤、盲测把关对冲；
4. **kev 依赖可达**：uv/GitHub/权重在环境内的可达性于 P0 一并验证，不可达则 kev 实验顺延不阻塞主线；
5. **开源版无标注平台**：本期以「已人工复核的金标数据」为前提规避；若后续需扩标，另评估部署社区 LabelStudio 工作量；
6. **盲测泄漏**：以 seal/verify/解封留痕三重机制约束，流程上仅 P5 一次解封。

## 5. 验收清单（本设计实现的最终判据）

- `gov-social-llm/` 目录内 6 算子骨架、3 条 Pipeline JSON 可按 README 手册在平台完成注册与导入；
- p0/p1/p2 三条线在两套 GPU 环境任一中实跑通过并产出对应 manifest 与报告；
- §3.5 各阶段出口判据逐项达成，最终以 §3.3 盲测验收线判定模型可交付社会治理场景。
