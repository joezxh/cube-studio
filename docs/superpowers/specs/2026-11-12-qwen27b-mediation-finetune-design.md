# Qwen3.8-27B 社会治理／矛盾调解领域微调优化方案（设计）

> 状态：builder 审阅完成、用户已选定路线与数据方案，待最终批准。本文是设计方案，未改动产品代码；`gov-social-llm/data-samples/` 下的三份数据是**待评审草稿**（spike），不进最终训练集。
> 适用范围：`d:/projects/github/cube-studio` 的 `gov-social-llm` 项目，2026-11-12 快照。
> 目标读者：实施训练与数据工程的工程师、需要评审方案的业务/平台方。

---

## 1 意图与为什么

在已有真实语料（本地法条与类案 JSON、`mediation_db` 业务库）之上，把社会治理与矛盾调解的领域能力落到**三个**模型：`Qwen3.8-27B` 量化本体，以及 `Qwen3.5-0.8B` / `1.7B` 两个学生档（用户定版，覆盖 2026-11-06 spec 中「优先 Qwen3.8 小档、Qwen3.5 退选」的旧规则）。27B 用现成的 AWQ-INT4 权重以保证当前卡能部署；不执行量化任务、不产出新的量化权重文件。同时把模型被问及自身身份时的回答统一为「我是杭州天阙大模型」。

训练目标输出**全部从真实语料的结构化字段直接派生，取消独立教师蒸馏线**（用户选定，见 §4 第二组路线）。27B 教师服务只在 P0 门禁和评测对照时临时使用，不常驻、不生产训练数据。

为什么这样做：可用算力被定死在单节点 `2×RTX 4090-48G` 或 `2×RTX 5090-32G` 任一都能跑通，资源效率优先；领域语料充足且含人工撰写的调解过程与点评，不必靠大规模合成或教师生成；身份与领域能力要同时进最终上线的模型，而不是只留在教师服务里。

---

## 2 目标／非目标／反目标

### 目标

1. 数据：三源接入（本地 9384 篇案例 JSON、业务库结构化案例、合成的身份/负例/红队），完成脱敏、去重、**结构化字段直接派生**与 dev/blind 分层切分，全链路带 manifest 血缘。
2. 训练：27B 量化本体 + 0.8B/1.7B 双臂都完成 LoRA SFT；只产出 adapter，不产出量化权重。
3. 部署：27B 用现成 AWQ 权重 + adapter + 服务层 system prompt，单卡在当前卡上可部署；学生档服务参数包本期新建。
4. 评估：领域指标沿用 `gov-eval` 并扩展其字段解析，新增身份一致性与 27B 微调前后对照，重定「教师天花板」基准。
5. 交付：数据清洗与派生规则、量化影响说明、超参配置、评测口径、硬件规格与分档推荐配置，可直接在社区版环境复现。

### 非目标

- 不跑 AWQ/GPTQ/任何量化流程，不产出量化权重，不做学生量化备份档（原有 P5 量化档取消）。
- **不建教师蒸馏链**：不常驻教师服务、不批量生成候选、不做多候选一致性投票与三闸过滤。
- 不做 27B 全参数微调、不做 logit 级在线知识蒸馏、不做权重级剪枝。
- 不改平台后端调度代码，不复制/重写 `pytorchjob` launcher。
- 不把模型权重、真实案件原文、数据库凭据打进镜像或写进仓库/DAG JSON。
- 不在本期引入多机 RDMA 训练。

### 反目标（跑通也算失败）

- 用凭空编造的案情、法条编号、当事人信息当训练数据；训练目标输出无法追溯到某条真实案例。
- 身份数据只有正例，导致模型对任何业务问题都回复「我是杭州天阙大模型」。
- 跳过 P0 门禁直接开训，最后发现 AWQ 权重挂不上 adapter。
- 27B 被微调后仍沿用旧的「≥教师 90%」验收基准。
- 把含姓名/电话/身份证号的原始业务文本送进训练集。
- 为了挂 adapter 偷偷重新做一次量化，把已取消的任务请回来。

---

## 3 约束（已核实的仓库与语料事实）

| 约束 | 依据 | 对方案的影响 |
|---|---|---|
| 既有定版 spec 把 27B 定为**冻结教师**、学生为 Qwen3.8 小档；本方案改为 27B 本体也微调、学生定版 Qwen3.5 | `docs/superpowers/specs/2026-11-06-gov-social-llm-distill-design.md:14,24,105,191` | 教师天花板漂移，验收基准必须重定；底座 ID/SHA256 按用户定版在 P0 就绪单登记 |
| 27B 已定 AWQ-INT4 单卡部署：16–18G 权重+KV、8k ctx、`--gpu-memory-util 0.85`；BF16 约 60–70G | 同 spec `:102,160`、`gov-social-llm/serving/gov-teacher-serve/args.json` | 训练只能走参数高效路线，且必须复用同一份量化权重 |
| 既有服务配置自相矛盾：`args.json` 两套 preset 写 `tensor_parallel_size: "2"`、4090 档 0.90，而 spec 写 `--tp 1`、`gov-p0-env-check.json` 为 `resource_gpu:1` + 0.85 | 三份文件实测 | **本方案以单卡 TP=1 为准**；`args.json` 的 TP=2 列为待清理残留，不在本期改 |
| 两套 GPU 环境必须同时跑通：2×4090-48G（sm_89）/ 2×5090-32G（sm_120）；CUDA≥12.8、torch≥2.7、5090 驱动≥570、`TORCH_CUDA_ARCH_LIST=8.9;12.0` | spec `:15,78,157-163`、`gov-social-llm/README.md:57-67` | 超参要按 32G 卡收敛，镜像双环境同 tag |
| 既有学生 LoRA：`r32 / lr 1e-4 / 3 epoch / seq 4096 / batch 1 / ga 8 / bf16`，QLoRA 4bit 作显存兜底 | spec `:105,162`、`ops/gov-sft/sft_cmd.py:27-57` | 学生档沿用，不重新发明 |
| `gov-eval` 的 `score_all` 只认行级 `label`/`risk`；T2 schema 用 `risk_level`，T3/T4 无 `label` | `ops/gov-eval/metrics.py:63-69,100-129`、`docs/task-spec/schemas/T2.json` | 评测行必须补扁平字段并扩展算子解析，否则 T2 高危召回与 T4 F1 恒为 0 |
| `filter3.py` 的 `to_alpaca/to_sharegpt` 要求 `messages/state/output` 字段 | `ops/gov-distill-filter/filter3.py:88-99` | 与本方案规范化字段不一致，格式导出不直接复用该函数 |
| `eval_split.py` 实为普通随机切分（非 spec 文字的「分层」），红队输出直接写空数组 | `gov-social-llm/scripts/eval_split.py:29-54` | 数据工程必须修正这两处，否则 blind 分布偏、红队验收无法执行 |
| 本地语料：`人民法院案例库` 5119 篇 JSON、`人民调解工作` 4265 篇 JSON、`起诉状` 1 个 PDF；位于用户本机 `D:/work/docs/legal`，容器不可直接访问 | 实测 | 必须先脱敏导出到 `/mnt/gov/raw/<version>` 共享卷并登记 manifest |
| 业务库：`mediation_db.public` 319 表；`kms_dispute_case`≈22561、`kms_legal_case`≈9084、向量表 2 张；大量 `*_bak_*`/`*_snapshot` 备份表 | 只读探查（information_schema / pg_class） | 备份/快照/向量表不得进训练集；向量表只作去重辅助 |
| `case_info` 含 `applicant_name/phone`、`respondent_name/phone`、`address_detail` 等 PII 列 | 只读字段探查 | 仅用于关联 ID，PII 列整列不导出；正文再正则脱敏 |
| 既有 `nlp-replace-private-data` 等脱敏算子是商业版空壳（`gitpath` 目录不存在、`args={}`） | `init-job-template.json:2640-2658` | 脱敏必须在本方案内自实现 |
| 仓库里无金标评测集、盲测集、红队样本、指令集实体；仅有 4 个测试夹具（3/6/8/8 行） | `gov-social-llm/tests/fixtures/` | 评测集必须从真实语料构建并人工复核，是 P1 出口判据 |
| LLaMA-Factory 支持在预量化 AWQ/GPTQ 模型上做 LoRA（省略 `quantization_bit/method`），也支持 `quantization_bit:4 + quantization_method:bitsandbytes` 的 NF4 QLoRA | 官方文档与 `examples/train_qlora/*.yaml` | 训练主形态可直接用现成 AWQ 权重，消除 adapter 跨量化迁移风险 |
| vLLM 是否支持「AWQ 权重 + LoRA adapter」存在版本相关限制，公开资料口径不一 | 检索结论 | 必须列为 P0 硬门禁，以实测为准 |
| 身份数据草稿已生成并校验：训练 64 条 / 评测 18 条 / 规格 1 份；全仓及草稿文件检索凭据 0 命中 | `gov-social-llm/data-samples/` | 待评审，批准后扩量到 300–500 条 |

---

## 4 方案选择（Approaches）

### 4.1 训练与部署路线

| 路线 | 做法 | 取舍 | 结论 |
|---|---|---|---|
| **1 训练只产 adapter，部署挂现成 AWQ 权重（带 P0 门禁）** | 27B 用 LoRA 训练，只落 adapter；部署在 `Qwen3.8-27B-AWQ` 上；学生双臂照常 LoRA | 不产出量化权重，符合「取消量化任务」；当前卡可跑；身份与领域能力直接进最终上线模型。代价：AWQ 权重 + LoRA 的训练/推理兼容性需实测，教师天花板漂移要重定基准 | **用户选定** |
| 2 27B 冻结 + system prompt/RAG，只微调学生 | 完全规避量化+LoRA 兼容风险，资源最省 | 「27B 本体微调」落空；领域能力依赖检索与提示，不能沉淀进权重 | 门禁失败时的退路 |
| 3 BF16 多卡训练 + 合并 + 重新量化部署 | 精度与部署最干净 | 需 2×80G 级显存，且必须重做量化，打破「不做量化」约束 | 未采纳 |

**实现细节（已定）**：用户批准路线 1 时描述的是「NF4 QLoRA 训练 → adapter 迁移到 AWQ 权重」。查证后改为**直接用现成的 AWQ 权重作为训练底座**（LLaMA-Factory 加载预量化模型时省略 `quantization_bit/method`，只挂 LoRA）：训练底座与部署底座是同一份权重，adapter 无需跨量化格式迁移。此形态定为**唯一主形态**，因此**不需要预取 54G 的 BF16 27B 权重**；NF4 QLoRA 只在主形态 P0 门禁不通时启用，届时须额外准备未量化底座并做迁移掉点对照。两者都不产出量化权重文件。

### 4.2 训练目标输出的产生方式

| 路线 | 做法 | 取舍 | 结论 |
|---|---|---|---|
| **A 结构化字段直接派生，取消独立蒸馏线** | T1 用 `case_type/keywords`、T2 用 `urgency_level/severity`、T3 用 `mediation_essentials + 调解结果/案例点评` 改写为建议语气、T4 从事实段抽要素；法条只引用语料真实出现项 | 省掉教师常驻、5k–20k 候选生成、三闸与通过率闸门；输出全部可追溯到真实案例，资源最省。代价：风格偏「案例文本腔」，需人工抽审与少量改写增广 | **用户选定** |
| B 保留教师蒸馏线 | 由（已微调的）27B 生成候选 → 三闸过滤 → 学生 SFT，与既有 `gov-p2-distill-line.json` 一致 | 输出更自然；但多一整条 GPU 排期与生成成本，且教师被微调后天花板与数据基准都要重定义 | 未采纳 |
| C 混合 | T1/T2/T4 派生，T3 用教师改写增广 + 人工抽审 | 折中；两套来源要统一 manifest，管线最复杂 | 未采纳 |

选 A 的理由：本地 9384 篇案例 + 业务库约 3.1 万条结构化记录足够，且 `调解过程 / 调解结果 / 案例点评` 是人工撰写的高质量领域文本，比教师生成更权威；取消蒸馏线后，「学生 ≥ 微调后 27B 90%」在同一套数据口径下可比。

### 4.3 身份能力路线

服务层 system prompt 主保障 + 1%–3% SFT 兜底（双层 canonical 句逐字一致），优于纯 SFT（易稀释、成本更高）。用户选定，见 §11。

---

## 5 数据预处理与清洗策略

### 5.1 三源接入

| 源 | 内容 | 接入方式 |
|---|---|---|
| 本地语料 | `人民法院案例库` 5119 篇（`title/content/content_quality/api_data`，含案号、裁判要旨、法条引用）；`人民调解工作` 4265 篇（`案情简介/调解过程/调解结果/案例点评/full_content`）；`起诉状` 1 个 PDF 模板 | 先在数据源侧按 `content_quality` 与正文长度过滤并脱敏，**导出到 `/mnt/gov/raw/<version>` 共享卷**并登记 manifest；容器不直接访问 Windows 路径；PDF 仅作模板参考，不进训练 |
| 业务库 | `kms_dispute_case`（case_type / case_summary / mediation_essentials / mediation_process / case_result / legal_provisions / keywords / applicable_scene / difficulty_level）、`kms_legal_case`（legal_basis / controversy_focus / court_opinion / case_summary）、`case_dispute_point`、`case_fact`、`case_protocol`、`mediation_knowledge_entry` | **只读视图 / 只读账号**；`deleted=false`、按 `tenant_id` 限定租户范围、按 `create_time` 增量抽取；排除 `*_bak_*`/`*_snapshot`/`*_copy`/向量表；凭据由环境变量/平台密钥注入，不写入任何仓库文件 |
| 业务库（辅助） | `case_info` | 仅用于取关联 ID 与 `case_type/urgency_level` 等非 PII 列；`applicant_name/phone`、`respondent_name/phone`、`address_detail` 等 PII 列整列不导出 |
| 合成 | 身份正例、防串扰负例、诱导改身份样本、隐私/伪造拒绝样本、红队样本、边界与长度样本 | 按 §11 规格生成；全部标注 `synthetic`，不混入真实案情 |

数据使用授权由数据提供方在 P1 入口确认，作为前置条件记录，不阻塞设计。

### 5.2 清洗流水线（每步产出 manifest）

1. **规范化**：统一为 `{source, source_id, case_no, case_type, title, facts, process, result, legal_refs, labels, text_len, quality}`，保留来源与原文哈希（脱敏后）。
2. **PII 脱敏**：`case_info` 的姓名/电话/地址/当事人列整列排除；正文用正则替换姓名（`某某`/`X某`）、手机号、身份证号、银行卡、详细门牌、案号为占位符；脱敏后二次抽检（人工 ≥100 条），脱敏规则配套单元测试。
3. **去重**：先按规范化 `case_no` / 标题去重，再用文本指纹（simhash）或 `dispute_case_vector` 相似度做跨源去重；人民法院案例库与 `kms_legal_case` 可能同源，必须去重后再切分，防 train/eval 泄漏。
4. **质量闸**：`content_quality`、长度区间、控制字符、8 字滑窗重复占比 >30% 丢弃；结构化字段缺失率超阈值的行不进训练。
5. **法条真实性**：`policy_points` / `legal_refs` 只允许引用语料 `legal_provisions`、`legal_basis` 或正文中真实出现的《…》第…条；无可靠引用时写「需核实法律依据」，**禁止生成法条编号**。
6. **任务化派生（训练目标输出的唯一来源，无教师生成）**，对齐 `docs/task-spec/schemas/T1–T4.json`：
   - T1 事件分类：`case_type`/`dispute_type`/`keywords` → `label / confidence / reason`；
   - T2 风险预警：`urgency_level`/`severity`/重复投诉/冲突描述 → `risk_level / evidences / escalate`；
   - T3 调解辅助：`case_summary + mediation_essentials` 作输入，`调解结果 / 案例点评 / mediation_process` **改写为建议语气**后生成 `disputes / policy_points / suggestion`；去掉「最终达成协议/支付金额」等结果剧透，避免把答案直接抄进输出；
   - T4 要素抽取：事实段落 → `entities / relations`。
   每条样本记录 `source_id` 与所用字段，保证输出可追溯。
7. **格式导出**：直接写 Alpaca（`instruction/input/output`）与 ShareGPT（`conversations`）目标格式，训练侧经 `dataset_info.json` 注册。**不复用** `ops/gov-distill-filter/filter3.py` 的 `to_alpaca/to_sharegpt`（它要求 `messages/state/output` 中间字段，与本方案规范化结构不一致；如确需复用须先做字段适配并补测试）。
8. **规则闸（无教师候选、无一致性投票、无 ≥80% 通过率闸门）**：T1–T4 JSON schema 硬校验、法条引用真实性、长度/控制字符/重复滑窗规则、人工抽审 ≥100 条；不合格行退回改写或丢弃，记录原因与数量。
9. **切分与封存**：dev/blind **分层** 7:3（按任务 × 纠纷类型 × 风险等级分层，seed 42），修正 `eval_split.py` 的普通随机切分；blind 用 `gov-manifest seal` 置只读、全程封存、终验只解封一次；红队 50–100 条由合成生成，修正当前写空文件的实现；标注一致性 Kappa ≥ 0.8。
10. **防止同源污染与血缘**：训练种子不带答案；评测金标人工复核；训练/评测集去重并留痕；每环一份 `manifest.json`（既有 `gov-manifest` 契约）。

### 5.3 规模与配额

真实语料去重后约 2.5–3.5 万篇；任务化派生目标 5k–20k 条指令（**派生**而非蒸馏），金标评测 1000–2000 条（**当前尚需构建与人工复核，是 P1 出口判据**），身份集评审后扩量到 300–500 条。合成只补缺口，不追求全量生成。

---

## 6 量化：选型依据、精度与显存影响（不执行量化任务）

**边界**：本方案不跑量化流程、不产出量化权重、不做学生量化档。`Qwen3.8-27B-AWQ` 是现成输入；备选形态的 4bit 只是运行时显存手段，不落盘。原需求中的「量化方案选择」改为「现成量化权重的选择依据与影响说明」。

| 形态 | 权重显存 | 训练状态显存 | 用途 |
|---|---|---|---|
| BF16 27B 全精度 | ≈54G（推理需 60–70G） | 全参 AdamW 需 >400G | 本期不可行；主形态也无需预取 |
| AWQ-INT4 预量化（现成） | ≈16–18G（+ KV） | — | 27B 部署与**训练底座**（主形态） |
| NF4 QLoRA（运行时量化，仅备选） | ≈16–18G | + LoRA 优化器 ≈1–3G、激活 ≈8–15G（grad ckpt、seq 1024–2048、batch 1） | 合计 ≈28–36G；48G 卡稳、32G 卡需短序列 + offload |
| 学生 1.7B LoRA | ≈3–4G | 峰值 ≈20G（既有 spec） | 单卡 24G 足够 |

**精度影响**：4bit 权重量化在分类/抽取类任务上通常有 1–3pp 的指标损失，对高危召回这类敏感指标影响需单独测；生成类任务表现为要点覆盖率与格式合规率略降。本地验证：在 dev 集上做「AWQ 权重无 adapter / AWQ 权重 + adapter /（若 2×4090 可跑）BF16 TP=2 基线」三方对照，量化引入的 macro-F1 差建议 ≤2pp；若 BF16 基线跑不起来，则引用官方 AWQ 基准 + 抽样人工评审，并在报告中注明未做本地全精度对照。

**选型理由**：AWQ-INT4 在 32G 卡上单卡可部署（既有双环境硬约束），且 LLaMA-Factory 支持直接在预量化权重上挂 LoRA，使训练与部署共用同一底座；GPTQ/AWQ 现场量化与 FP8 均不引入，既无必要也超出「取消量化任务」的边界。

---

## 7 微调方法选型与理由

| 模型 | 方法 | 理由 |
|---|---|---|
| `Qwen3.8-27B-AWQ` | **LoRA SFT，直接在现成 AWQ 权重上训练**（主形态）：`finetuning_type: lora`，省略 `quantization_bit/method`；备选：`quantization_bit:4 + quantization_method:bitsandbytes`（NF4 QLoRA） | 当前卡只放得下参数高效训练；全参数 27B 需 >400G 优化器显存，直接排除。主形态训练/部署同一份权重，无 adapter 迁移风险；备选仅在主形态内核/反向传播不通时启用 |
| `Qwen3.5-0.8B` / `1.7B`（用户定版） | LoRA SFT（既有 `gov-sft`），QLoRA 4bit 仅作 32G 卡显存兜底 | 低数据量、迭代快、单卡可训；两个参数档做对照，按验收线与 P95 选生产档；底座 ID/SHA256 在 P0 就绪单登记后不得更换 |
| 三个模型共用 | 身份集按 1%–3% 混入 + 服务层 system prompt 双层保障 | 纯 SFT 改身份易被稀释且成本高；双层最省，但 canonical 句必须逐字一致 |

**部署配置口径（本期 P6 必做）**：27B 服务按**单卡 TP=1** 新建参数包，命令含 `--quantization awq --enable-lora --lora-modules <adapter>`、`--gpu-memory-utilization`（4090 档 0.90 / 5090 档 0.85，沿用既有 preset 数值）、`--max-model-len 8192`；`serving/gov-teacher-serve/args.json` 的 `tensor_parallel_size: "2"` 与旧 describe「教师服务」属残留，列为待清理项，不在本期改文件。学生档目前 `serving/` 下无参数包，**需新建**（FP16 服务档 + adapter 或合并权重，二选一在 P6 按 P95 与显存实测决定）。

**明确不选**：27B 全参数微调、DeepSpeed ZeRO 多机、logit/在线 KD、权重剪枝、量化后重训、kev 指针头对照臂、教师蒸馏链。

---

## 8 训练流程与关键超参

### 8.1 阶段（P0 拆分，解决门禁与数据的先后依赖）

```
P0-a 环境与技术门禁（不依赖任何训练数据/评测集）
  → P0-b 最小闭环验证（合成 mini 集 + 1 步临时 adapter，验证后丢弃）
  → P1 数据接入/脱敏/金标评测集构建与复核
  → P2 任务化派生 + 身份集扩量
  → 开训前准入复核（正式 dev + 首轮 adapter 对照）
  → P3 27B LoRA 正式训练
  → P4 学生双臂
  → P5 评测与三方对照
  → P6 部署（AWQ + adapter + system prompt）
```

P0-b 的 1 步临时训练是**门禁手段**，不属于「正式开训」；「任何门禁项不过不得开训」约束的是 P3。正式 dev 集在 P1 才建好，因此指标对照放在开训前复核，不放在 P0-a。

### 8.2 27B 主形态配置（LLaMA-Factory YAML 字段，数值为建议初值，以 P0 实测收敛）

```yaml
### model
model_name_or_path: /mnt/gov/models/Qwen3.8-27B-AWQ   # 现成预量化权重，不量化、不合并
trust_remote_code: true
# 注意：预量化模型省略 quantization_bit / quantization_method
### method
stage: sft
do_train: true
finetuning_type: lora
lora_rank: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target: all
### dataset
dataset: gov_t1,gov_t2,gov_t3,gov_t4,identity
dataset_dir: /mnt/gov/data/<version>
template: qwen                 # 与底座 tokenizer 一致，P0 核对
cutoff_len: 1024               # 32G 卡；48G 卡可放宽到 2048
max_samples: <按 5k–20k 派生指令集规模>
overwrite_cache: true
preprocessing_num_workers: 8
### output
output_dir: /mnt/gov/models/students/27b-lora/<version>
logging_steps: 10
save_steps: 200
plot_loss: true
report_to: none
overwrite_output_dir: true
### train
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
gradient_checkpointing: true
learning_rate: 1.0e-4
num_train_epochs: 2.0            # 身份集占比小，2 轮起，按 dev 曲线决定
lr_scheduler_type: cosine
warmup_ratio: 0.03
max_grad_norm: 1.0
bf16: true
seed: 42
```

- 备选形态追加：`quantization_bit: 4`、`quantization_method: bitsandbytes`、`double_quantization: true`，并把 `model_name_or_path` 换成未量化底座；此时 adapter 与 AWQ 底座不同源，必须增加迁移掉点对照。
- 32G 卡 OOM 时优先压 `cutoff_len`（1024→512）、开 `gradient_checkpointing`、减少 `preprocessing_num_workers`，最后才考虑 CPU offload；不要靠加大 `gradient_accumulation_steps` 掩盖 OOM。
- 只保存 adapter 与配置，不保存合并后的全量权重副本；`save_steps` 产生的中间 adapter 定期清理，保留最近 2 个。

### 8.3 学生档配置（沿用既有定版）

`lora_rank 32 / lr 1e-4 / epochs 3 / cutoff_len 4096 / batch 1 / ga 8 / bf16 / template qwen / plot_loss / report_to none`；QLoRA 4bit 仅作 32G 卡兜底。超参搜索范围沿用 `lr 1e-4~2e-4`、`lora_r 16/32/64`、`epoch 2~4`，用 dev 集迭代，**最多 5 轮**防盲测过拟合。

### 8.4 身份数据混入

- `identity` 集按总样本 1%–3% 混入，三个模型共用同一份；禁止重复过采样，扩量靠问法改写与上下文变体。
- 服务层 system prompt 的 canonical 句与 SFT 数据逐字一致：「我是杭州天阙大模型」。
- 每个模型训练后都跑 §10.2 的 identity 评测，串扰超阈值即降低混入比例重训。

### 8.5 产物契约

```
<output>/
├── adapter/                 # LoRA 权重（唯一必需产物）
├── train.yaml               # 最终生效配置
├── train_cmd.sh             # 可复现命令
├── train.log                # 训练日志（stdout 同步进 Argo 归档）
├── metrics.json             # loss 序列与摘要
├── training_loss.png / loss.csv
└── train_manifest.json      # 数据集 manifest 摘要 + 底座权重摘要 + 超参 + 镜像 tag + 退出码
```

`/metric.json` 按平台既有算子惯例尽力写（社区版无消费端），不作为验收项。退出码 `0` 成功 / `2` 参数校验失败 / 其余透传训练进程。

---

## 9 P0 硬门禁与退路

主形态的两个技术风险（AWQ 权重能否承载 LoRA 训练、vLLM 能否在 AWQ 权重上挂 adapter）必须先实测：

**P0-a（不依赖训练数据）**
1. 镜像/驱动核对：`nvidia-smi`、`torch.version.cuda`、sm_89 / sm_120 内核可用、`autoawq`/`peft`/`bitsandbytes` 版本组合。
2. **前向+反向**：AWQ 权重加载 + LoRA，用合成 mini 集跑 1 个 mini-batch 的前向与反向，确认无内核报错、loss 可下降。

**P0-b（合成 mini 集 + 1 步临时 adapter，验证后丢弃）**
3. **部署链路**：vLLM 以 `--quantization awq --enable-lora` 加载同一权重 + 临时 adapter，跑一次身份问答与一次 T3 调解问答，确认返回正常。
4. **32G 卡 OOM 边界**：在 5090-32G 上按 §8.2 配置跑 10 步，记录峰值显存；48G 卡同时跑一遍作对照。
5. **最小指标检查**：合成 mini 集上「AWQ 无 adapter / + 临时 adapter」的格式合规与 identity 召回，确认 adapter 生效且不串扰。

**开训前准入复核（P1 建好正式 dev 后）**：用正式 dev 集与首轮 adapter 做 macro-F1 和 identity 召回对照，确认领域指标不下降；不过则回到 §9 退路。

门禁失败时的退路（按代价递增）：① 切备选形态 B（NF4 QLoRA）+ 迁移掉点评估；② 27B 冻结 + system prompt/RAG，只交付学生双臂（路线 2），并明确告知 27B 本体微调未达成；③ 需要放宽「不做量化」或升级到 2×80G 硬件才能走路线 3，须重新评审。

---

## 10 评估指标与验证方法

### 10.1 领域指标与评测行字段契约

`gov-eval` 单一口径：`macro_f1 / per_class_p / per_class_r / high_risk_recall / false_alarm_rate / format_compliance / refusal_rate / redteam_violation`；五模式 `smoke / dev / blind / safety / bench`。

**字段契约（本期必做，否则指标恒为 0）**：评测行统一带扁平字段 `label` 与 `risk`——派生时把 T1 的 `label`、T2 的 `risk_level` 映射为 `risk`；T3/T4 的 `output` 内 JSON 由新增解析函数抽取后再交给 `score_all`；`format_compliance` 继续校验 `output` 字符串。即**扩展 `gov-eval` 的字段解析**，保持指标口径不变，不新造第二套评测算子。

验收线沿用既有定版，但**基准重定**：原「≥教师 90%」中的教师已被微调，改为「学生 ≥ **微调后 27B** 得分 90%」；其余不变：T1/T4 macro-F1 ≥ 0.85、T2 高危召回 ≥ 0.92 且误报 ≤ 15%、T3 格式合规 ≥ 99% 且人工「可用+良好」≥ 80% 且事实性错误 ≤ 3%、红队违规 ≤ 1%、隐私泄漏 0、并发 20 下 P95 判别 ≤ 200ms / 生成 ≤ 800ms、整体质量保留率 ≥ 90% 且推理成本 ≤ 27B 的 1/10。

### 10.2 新增指标

| 指标 | 口径 | 建议阈值 |
|---|---|---|
| identity 召回 | 身份类问法（中英文、直接/间接/上下文）输出含 canonical 句 | ≥ 99% |
| identity 诱导保持 | 诱导改身份、索要系统提示时仍保持身份 | ≥ 99% |
| identity 串扰 | 业务问题误答身份句 | ≤ 1% |
| 拒绝能力不退化 | 隐私/伪造类拒绝率不低于微调前基线 | 不下降 |
| 27B 微调前后对照 | AWQ 无 adapter vs + adapter 的 dev 指标 | 领域指标不下降，身份达标 |
| 量化精度影响 | 见 §6 三方对照 | macro-F1 差 ≤ 2pp（或注明未做全精度本地对照） |

### 10.3 验证流程

`smoke`（门禁内）→ `dev`（最多 5 轮迭代，三方对照：微调后 27B / 0.8B / 1.7B）→ `blind` 终验（只解封一次并记录）→ `safety`（红队 + 隐私）→ `bench`（P50/P95、显存、并发 20）。所有结果写 `metrics.json + report.md + manifest.json`；数据切分、脱敏、去重、法条真实性各有一份可回归的质量报告。

---

## 11 身份／版权信息变更

**范围澄清**：SFT 只改变生成式回答中的自我身份表述，**不能改变法律意义上的版权/许可归属**。后者需要另改发布物料：`model card`（模型名、作者、license）、`LICENSE` 文件、发布仓库元数据、服务 `/v1/models` 返回的 model id、Web UI 品牌位——方案列出这份清单，**本期不实施**，避免与训练任务混淆。

**服务层 system prompt 注入属本期 P6 必做**（vLLM/平台服务参数，或 `tokenizer_config.json` 的默认 system 提示），是身份的主保障；SFT 只兜底。两者 canonical 句必须逐字一致，否则模型会出现两种自相矛盾的身份表述。

**数据草稿**（`gov-social-llm/data-samples/`，待评审、不进最终训练集）：`identity_sft_draft.jsonl` 64 条、`identity_eval_draft.jsonl` 18 条、`identity_dataset_spec.json` 规格。七类覆盖：中英文直接问法、间接问法、带业务上下文的多轮、诱导改身份的防御样本、16 条防串扰负例、隐私/伪造拒绝样本。出品方全称、版本号、授权口径一律不臆造，统一指向部署方模型说明；评审通过后按规格扩量到 300–500 条。

---

## 12 硬件要求与推荐配置

### 12.1 规格要求

| 维度 | 要求 | 理由 |
|---|---|---|
| 显存 | 27B 训练单卡 ≥48G 稳；32G 需 `cutoff_len≤1024` + grad ckpt + 可能 offload；27B 部署单卡 16–18G + KV（8k ctx）；学生训练/部署单卡 ≥24G | §6 显存账；双环境硬约束 |
| 算力 | 单节点双卡，训练与推理错峰；27B QLoRA 吞吐低，训练时长按「5k–20k 样本 × 2–3 epoch」估到数小时～1–2 天量级，以 P0 实测为准 | 不给虚构 TFLOPS，按实测排期 |
| CPU / 内存 | ≥32 核、≥128GB RAM | 语料解析、tokenization 并行、CPU offload 缓冲 |
| 存储 | 本地 NVMe ≥1TB 可用（建议 2TB）：AWQ 权重 ≈18G、学生权重 ≈3–4G×2、语料与派生数据若干 GB、adapter 几十～几百 MB、日志与 checkpoint；共享卷 NFS/CephFS ≥1TB 供 `/mnt/gov` 多任务读写 | 只存 adapter 不存合并权重副本，控制容量 |
| 网络 | 内网到 `mediation_db` 与共享卷建议 10GbE；单机训练**不需要 RDMA**；多机扩展才需 IB/RoCE；外网仅用于 hf-mirror/PyPI 拉依赖，内网环境改离线物料 | 单节点拓扑，避免无谓带宽成本 |
| 软件栈 | CUDA ≥12.8、torch ≥2.7、5090 驱动 ≥570、`TORCH_CUDA_ARCH_LIST=8.9;12.0`；LLaMA-Factory 锁定版本镜像（不用 latest）；vLLM 支持 Blackwell 的同一 tag | 双环境同一镜像 tag，既有定版 |
| 数据访问 | 只读账号 + 视图、凭据走环境变量/平台密钥，禁止写入仓库/DAG/日志 | PII 与凭据安全 |

### 12.2 分档推荐

| 档 | 配置 | 适用 |
|---|---|---|
| **最低可跑（现有）** | 单节点 `2×RTX 4090-48G` **或** `2×RTX 5090-32G`，64GB RAM，1TB NVMe，10GbE；卡0 27B 训练/部署，卡1 学生训练 + 评测错峰 | 满足既有硬约束，32G 档需按 §8.2 压序列 |
| **推荐（性价比最优）** | `2×RTX 4090-48G` + 128GB RAM + 2TB NVMe + 共享 NFS + 只读 DB 视图 + 本地权重/镜像缓存 | 48G 余量让 27B 训练可放宽到 2048 序列，卡1 可并行学生训练与评测，P0 门禁风险最低 |
| **扩展（非本期）** | `2×A100/H100 80G` + IB/RoCE，或 4×48G + ZeRO-3 offload | 仅当 P0 门禁全失败、必须走 BF16 训练或全参路线时才升级 |

**资源效率措施**：LoRA 只训 adapter、只存 adapter；训练目标直接派生，省掉教师常驻与候选生成；三个模型共用一份身份集与派生语料；训练/评测/推理错峰复用同一对卡；DB 增量抽取不落全量副本；盲测集只解封一次避免反复重训；量化任务取消，省掉一次离线量化与回归。

---

## 13 交付物清单与已定决定

**交付物**：本设计文档；数据接入/脱敏/派生规则与质量报告模板；27B 与学生档训练 YAML；身份集（草稿→评审后扩量）；P0 门禁脚本与报告；评测报告与三方对照表；硬件就绪核对单；发布物料版权变更清单（§11）；27B 与学生服务参数包（§7）。

**用户决定**：路线 1（带 P0 门禁）；27B 量化本体 + `Qwen3.5-0.8B/1.7B` 双臂都微调；27B 用现成量化版且当前卡可部署；取消量化任务；新增业务库数据源；身份回答统一为「我是杭州天阙大模型」；数据先生成待评审；**A 结构化字段直接派生、取消独立教师蒸馏线**。

**我在 builder 审阅后补定、需批准时核对的决定**：

1. 训练主形态为**直接在现成 AWQ 权重上挂 LoRA**（省略 `quantization_bit/method`），NF4 QLoRA 仅为门禁失败退路，不需预取 54G BF16 权重。
2. 验收基准「≥教师 90%」改为「≥ 微调后 27B 90%」。
3. 数据以真实语料派生为主（本地 9384 篇 + 业务库约 3.1 万条），合成只补身份/负例/红队/边界；排除备份表与 PII 列；修正分层切分与红队空占位；本地语料先脱敏导出到共享卷，业务库走只读视图 + 增量抽取。
4. 身份能力用 system prompt（P6 必做）+ SFT（1%–3%）双层；法律意义上的版权只列发布物料清单、不在训练里做。
5. 数据库凭据不写入任何仓库文件，方案内只保留库名/表名与「只读账号 + 环境变量注入」约定。
6. P0 拆为 P0-a（不依赖数据）/ P0-b（合成 mini 集 + 1 步临时 adapter）/ 开训前准入复核（正式 dev），消除门禁与数据的循环依赖。
7. 部署按单卡 TP=1 + `--enable-lora` 新建 27B 服务参数包（`args.json` 的 TP=2 列为待清理），学生服务参数包本期新建。
8. 评测行补扁平 `label/risk` 字段并扩展 `gov-eval` 解析 T2/T3/T4，保持指标口径单一。
9. 学生底座按用户定版 `Qwen3.5-0.8B/1.7B` 覆盖旧 spec 的 Qwen3.8 小档优先规则，P0 就绪单登记 ID/SHA256 后不得更换。

**留给实施者**：`template` 与底座 tokenizer 的核对结果、`cutoff_len/ga/epoch` 的最终收敛值、vLLM 与 LLaMA-Factory 的具体锁定 tag、P0 各项门禁的脚本实现、金标评测集的人工复核与 Kappa 计算、身份集准确文案（出品方/版本/授权）由用户提供后再替换占位句、硬件就绪单的实测数值、学生服务采用「adapter」还是「合并权重」部署（P6 按 P95 与显存实测决定）。
