# 企业版「模型训练」功能点头脑风暴

> 来源：`docs/企业版功能.md` 第 48–58 行（模型训练部分，含自动调参）中所有 `[...]` 标注的企业版专属功能点。
> 目的：为每个功能点产出「定义与用户价值 / 实现思路 / 与开源版关系 / 难点与风险」的结构化头脑风暴素材，作为后续逐功能拆分正式设计文档（spec）的母文档。
> 范围口径：第 57 行「自定义镜像」无 `[]` 标注（纯开源功能），不纳入；第 59 行「TensorBoard 作业」虽为 `[]` 但未列入覆盖清单，不纳入。
> 补录口径：主题 F（具身智能 / VLA 训练，F1–F4）为新方向扩展补录，非企业版功能文档 `[...]` 标注提取，编号独立于 #1–#24 清单。

## §0 功能点全量清单与梳理方法

### 0.1 清单（24 组）

| # | 所在行/功能 | 企业版功能点 | 主题 |
|---|---|---|---|
| 1 | 48 拖拽编排 | 任务支持独占和共享占用 GPU | A |
| 2 | 48 | 支持 RDMA 资源占用 | A |
| 3 | 48 | 支持 GPU 不同厂商、不同卡型的占用 | A |
| 4 | 48 | 分布式任务模板支持 GPU 型号透传、RDMA 资源透传、拉取秘钥透传 | A |
| 5 | 48 | pipeline 支持定时调度、补录、并发限制、超时、实例依赖 | A |
| 6 | 48 | 任务输入输出、任务流全局常量、文本/图片/csv/json/表格/echart 结果可视化、workflow 暂停和恢复 | A |
| 7 | 48 | 单任务和 pipeline 运行中任务监听端口（运行中服务监听） | A |
| 8 | 48 | 定时调度支持最大保留实例数 | A |
| 9 | 48 | pipeline 支持任务流优先级 | A |
| 10 | 49 基础算子 | 逻辑节点、python 算子 | B |
| 11 | 49 数据同步 | 数据集导入支持 huggingface/魔塔数据集 | B |
| 12 | 49 | datax-import 算子 | B |
| 13 | 49 | 模型导入支持 huggingface/魔塔模型 | B |
| 14 | 49 | datax-import 支持 mysql、postgresql、clickhouse | B |
| 15 | 50 特征处理 | 特征处理算子集（整组，约 22 个子算子，详见 §3） | C |
| 16 | 51 数据工具 | hadoop 模板支持 hdfs、hive、spark 命令 | B |
| 17 | 51 文本处理 | paddleocr-vl pdf/doc/图片提取 markdown、markdown 提取问答对、问答扩展、清理异常数据、过滤数据、替换隐私数据、文本数据统计 | B |
| 18 | 51 图像处理 | 图片质量评估、去噪声、缩放、标准化、裁剪、均衡化、空间转换、旋转/平移/缩放/翻转 | B |
| 19 | 52 传统 ML | ray-sklearn 分布式 | D |
| 20 | 52 ML 算法 | ar/arima/random-forest(-regression)/lr/lightgbm/knn/kmean/gbdt/decision-tree/pca/lda/catboost/xgb 算法集，超参搜索 | D |
| 21 | 54 模型处理 | 模型评估、模型格式转换 | E |
| 22 | 55 算子自定义 | 自定义任务模板额外支持 int/float/list/bool/json 型，子类型 workdir/image/select-input/select2/project 类型，参数 tip 提醒 | E |
| 23 | 56 链路共享 | 示例 pipeline 任务流导入导出 | E |
| 24 | 58 自动调参 | 基于单机/分布式的自动超参搜索 | D |

### 0.2 梳理方法与代码校验结论

头脑风暴前对开源代码做了两点校验，结论影响多个条目的定位口径：

1. **开源代码实际能力**：`myapp/views/view_pipeline.py` 已存在 `schedule_type/cron_time/depends_on_past/max_active_runs` 等字段；`myapp/models/model_nni.py` 与 `images/nni/Dockerfile` 表明 NNI 超参搜索底座在开源代码中已有痕迹。`job-template/job/` 实际包含：dataset、datax、demo、deploy-service、model_download、model_offline_predict、model_register、pytorch、ray、ray_sklearn、tf、volcano、xgb、yolov8、video-audio。
2. **定位口径修正**：凡 wiki 文档标注企业版但开源代码已有基础的条目，本文定位为「复用 + 增强」而非「新增」；此类条目在正文中以 ⚠️ 显式标注。
3. **二轮校验（2026-11-08，序 3 spec 设计前复核）**：深入 `myapp/tasks/schedules.py` 调度逻辑与 `view_pipeline.py::make_workflow_yaml` 合成链路后修正两处判断——① **补录**（`cronjob_start_time` → RunHistory 逐时间点生成 + execution_date 去重）与**任务级超时**（`Task.timeout` → `activeDeadlineSeconds`）开源版**均已实现**，A5 的「缺口」判断失准（首轮仅核对字段存在，未核对逻辑）；② A8 的 expired_limit 删旧实例已实现但清理不完备（RunHistory 记录不删、artifact 不回收）；③ A9 的 priority 为**纯字段壳**（表单/合成/前端链路零使用），定位从「扩展」改判「新增」。修正已回写至 A5/A8/A9 各小节。

### 0.3 主题分组

按依赖关系分为 5 个主题：A 任务流编排与调度增强（#1–#9）、B 算子生态扩展（#10–#14、#16–#18）、C 特征处理算子集（#15）、D 传统 ML 与自动调参（#19/#20/#24）、E 模型处理与链路共享（#21–#23）；另有新方向扩展主题 F 具身智能 / VLA 训练（F1–F4，详见 §6）。

---

## §1 主题 A：任务流编排与调度增强

### A1. GPU 独占 + 共享占用（#1）
- **定义与用户价值**：同一 GPU 可被多个任务按比例共享占用（如 0.5 卡），提高小任务场景下昂贵 GPU 资源的利用率；与独占模式互补，覆盖推理/调试类轻负载。
- **实现思路**：基于 k8s device-plugin 扩展或 GPU sharing 方案（NVIDIA time-slicing / MIG / vGPU 厂商方案）；任务 YAML 注入资源注解，调度器侧做份额校验；前端任务表单增加「独占/共享」选项及份额值。
- **与开源版关系**：扩展——开源版已有 GPU 资源申请（resources.limits 卡数），需新增共享语义层。
- **难点与风险**：共享模式显存隔离天然不安全（进程可越界），需明确 SLA 边界；与 A3 的 device-plugin 需统一抽象，避免每厂商一套实现。

### A2. RDMA 资源占用（#2）
- **定义与用户价值**：任务可申请 IB/RoCE RDMA 网络资源，多机多卡训练（NCCL）获得数倍带宽，缩短大模型训练时间。
- **实现思路**：k8s SR-IOV / RDMA shared device plugin 注入 rdma/hca 资源；任务模板增加 rdma 开关与数量参数；节点预装 OFED 驱动并做 health check。
- **与开源版关系**：新增——开源版无 RDMA 调度链路。
- **难点与风险**：驱动与内核版本强耦合；IB + RoCE 混部网络配置复杂；故障表现为训练 hang 而非报错，排障成本高，需要预检连通性探针。

### A3. 多厂商多卡型 GPU 占用（#3）
- **定义与用户价值**：任务可指定卡型（T4/V100/A100/4090）乃至厂商（英伟达/昇腾/海光/沐曦），调度到匹配节点；用户按需选型，平台精细化运营异构算力。
- **实现思路**：节点打 label（gpu-type、gpu-vendor），任务 spec 通过 nodeSelector/affinity 选择；前端卡型字典由管理员维护（机器资源管理模块联动）。
- **与开源版关系**：扩展——开源版已有卡型选择前端入口，企业版需扩展到多厂商 device-plugin 与资源名（npu/dcu 等）统一映射。
- **难点与风险**：非英伟达厂商 device-plugin 成熟度参差；镜像与 CUDA/ROCm/CANN 运行时绑定，卡型×镜像组合爆炸，需镜像元数据登记约束可选组合。

### A4. 分布式任务模板透传（GPU 型号 / RDMA / 秘钥）（#4）
- **定义与用户价值**：tf/pytorch/ray 等分布式模板的 worker 参数可透传 GPU 型号、RDMA、secret 拉取配置，避免分布式任务比单机任务「少能力」。
- **实现思路**：改造 `job-template/job/{pytorch,tf,ray}` 的 args 模板，将三类参数从 worker 模板硬编码改为 pipeline DAG 传入；前端分布式任务表单暴露三组透传项。
- **与开源版关系**：扩展——模板已在开源版，透传链路为新增字段。
- **难点与风险**：模板参数变更多版本兼容（旧 pipeline JSON 反序列化）；secret 跨 namespace 引用需权限校验，防越权拉取。
- **依赖**：A2/A3（异构资源抽象）是 A4 透传的前提。

### A5. Pipeline 调度增强：定时/补录/并发限制/超时/实例依赖（#5）
- **定义与用户价值**：pipeline 具备生产级调度语义——crontab 定时、错过的周期补录（backfill）、并发实例上限、任务级超时、上游实例依赖（depends_on_past），支撑数仓式日常批处理场景。
- **实现思路**：复用 argo workflow 的 cron 与 activeDeadlineSeconds；补录逻辑在平台层遍历时间窗生成实例；max_active_runs 用平台锁或 argo 并发策略实现。
- **与开源版关系**：⚠️ 复用 + 增强（二轮校验修正）——定时触发、补录、并发限制、实例依赖、任务级超时**五要素开源版均已全部实现**（schedules.py `make_timerun_config`/`upload_timerun` + `Task.timeout`→`activeDeadlineSeconds`），本项企业版增量收敛为前端入口：Setting 面板补 `cronjob_start_time`（crontab 时展示，描述“可设为更早时间，自动补录错过的周期实例”）；后端调度逻辑不动，以回归护栏验证。
- **三轮校正（实施取证）：原“visionPlus 补 `expired_limit` 字段”为事实误判，已删除**——visionPlus 由后端以 `scenes=etl_pipeline` 打开（`view_etl_pipeline.py` L460），detail/save 走 `/etl_pipeline_modelview/api/config/<id>`，操作 **ETL_Pipeline** 模型；该模型仅 `name/describe/project_id/workflow/dag_json/config/expand` 七列，**无 `expired_limit`/`priority`/`schedule_type`/`cron_time`/`cronjob_start_time`**（其被注释的调度字段块是从 vision 复制的死代码）；且其 `savePipeline` 载荷仅 `{...initProject, dag_json, config}`，面板 `changed` 不进请求体。因此 pipeline 调度类 UI（#5/#8/#9）**唯一归属 vision 面板**；若需让 ETL_Pipeline 具备保留数/优先级，属跨模型跳调度引擎的新主题，需单独 spec。
- **难点与风险**：补录与实时调度冲突时的实例去重（开源已用 execution_date 查重缓解）；argo 版本升级对 cron API 的兼容。

### A6. 任务输入输出 / 全局常量 / 结果可视化 / workflow 暂停恢复（#6）
- **定义与用户价值**：任务间传递结构化产物（文件/指标），DAG 级全局常量统一注入，任务运行后输出文本/图片/CSV/JSON/表格/ECharts 直接在 UI 渲染；workflow 可暂停/恢复，节省长链路调试成本。
- **实现思路**：基于 argo artifact + 平台 sidecar 采集任务输出目录并登记；可视化按扩展名/mime 分派渲染组件；暂停=挂起后续节点（argo suspend node），恢复=resume。
- **与开源版关系**：新增为主（可视化与常量），暂停恢复为扩展（argo 原生支持，补 UI）。
- **难点与风险**：产物大小限制（大文件进对象存储 + 引用，不进 DB）；ECharts 渲染需前端安全过滤（防注入）；暂停语义与逻辑节点（B1）天然结合，接口需预留。

### A7. 运行中任务监听端口（#7）
- **定义与用户价值**：单任务/pipeline 任务运行中可暴露监听端口（如训练中的临时 API、tensorboard），用户从 UI 直接访问，形成「边训练边验证」闭环。
- **实现思路**：任务 spec 注入 ports + ingress 路由（复用推理服务的网关与泛域名机制），任务结束自动回收路由；访问鉴权复用平台登录态。
- **与开源版关系**：新增——开源版端口暴露仅限推理服务模块。
- **难点与风险**：临时端口的权限边界与安全审计；ingress 对象生命周期管理（任务崩溃后残留清理）；与多集群网关的兼容。

### A8. 定时调度最大保留实例数（#8）
- **定义与用户价值**：限制定时调度保留的历史实例数量，防止高频调度撑爆实例列表与 etcd。
- **实现思路**：调度触发时按保留数清理最旧实例（含 argo wf 删除）。
- **与开源版关系**：⚠️ 复用 + 增强——expired_limit 删旧实例逻辑已实现（argo wf 删除 + 表状态标记）；企业版补两层清理完备性：① RunHistory 终态记录清理（`pipeline_file` 为 Text(655360)，定时记录累积是 DB 膨胀主因；保留最新 expired_limit 条，仅删终态 Deleted/Succeeded/Failed，非终态保留以免干扰调度链路）；② minio `mlpipeline` bucket 按 workflow_name 前缀回收旧实例 artifact。已定边界：DB + artifact 两层，共享存储工作目录不动留 v2；清理失败 logging 不阻塞主流程。
- **难点与风险**：实例删除连带 artifact 清理的事务一致性。

### A9. 任务流优先级（#9）
- **定义与用户价值**：pipeline 整体设置优先级，资源紧张时高优任务流优先获得排队资源，保障核心业务 SLA。
- **实现思路**：映射 k8s PriorityClass / volcano 的 job priority + 队列权重；argo wf 模板注入 priority；前端 pipeline 表单加优先级档位（高/中/低）。
- **与开源版关系**：新增（二轮校验改判，原「扩展」）——`Pipeline.priority` 为纯字段壳（表单/合成/前端链路零使用），本项为全链路新建。技术路线已定：**双注入 + 双闸门**——档位命中时同时注入 argo `spec.priority` 数值（high=200/mid=100/low=0，controller 提交排序）与 `spec.templateDefaults.priorityClassName`（Pod 级调度优先级）；平台提供三档 PriorityClass 安装清单（**preemptionPolicy: Never** 防杀运行中训练任务），类名经 conf `PIPELINE_PRIORITY_CLASS` 映射，**缺省空 = 功能关闭不注入**，存量记录（含 default='high'）行为完全不变。volcano 队列权重不选：pipeline workflow 不走 volcano gang scheduling，改造面过大。
- **难点与风险**：抢占（preemption）可能杀死运行中训练任务，需默认仅排队序优先、抢占可配置；与多资源组配额（计量计费域）叠加时的语义冲突需定义清楚。

### 主题 A 小结
9 项中 #5、#8 实为「复用+增强」且程度超出预估（二轮校验：补录/超时/保留数均已实现，增量收敛为入口与清理完备性）；#9 虽标注扩展实为纯字段壳，是全主题唯一主体新增。#1–#4、#7 为调度资源侧硬能力，#6 为编排体验层。A2/A3（异构资源抽象）是 A4 透传的前提，建议 spec 拆分时归入同一实施批次。

---

## §2 主题 B：算子生态扩展

### B1. 逻辑节点、Python 算子（#10）
- **定义与用户价值**：「逻辑节点」提供 DAG 中的分支判断/汇聚/人工审核/延时等控制流能力；「Python 算子」让用户零镜像打包、直接写一段 Python 代码作为任务节点。两者把 pipeline 从「纯训练链路」升级为可表达业务逻辑的编排工具，覆盖 ETL 分支、条件告警、人工卡点等高频场景。
- **实现思路**：逻辑节点编译为 argo 的 switch/parallel/suspend 原生节点类型，前端画布以特殊图标渲染；Python 算子复用平台统一基础镜像 + 代码挂载（类似 `job-template/job/demo` 的脚本注入模式），支持在线编辑代码框与 pip 依赖声明。
- **与开源版关系**：新增——开源版 `job-template/job/` 无对应模板；argo 底座能力原生存在，属「底座已有、模板与 UI 缺失」。
- **难点与风险**：逻辑节点条件表达式语法设计（建议复用 DAG 全局常量的取值语法，避免发明第二套 DSL）；Python 算子的依赖安装耗时与镜像缓存策略；用户代码逃逸风险（默认跑在受限资源与网络策略下）。

### B2. 数据集导入支持 HuggingFace / 魔塔（#11）
- **定义与用户价值**：在平台内直接搜索并导入 HF/ModelScope 数据集到内部数据集管理/对象存储，免去手动下载搬运；内网客户配合镜像源可用。
- **实现思路**：封装 datasets-sdk（HF）+ modelscope SDK 的导入 job（新增 `dataset/huggingface-import` 模板），参数含 repo id、split、子集、目标路径；任务内做断点续传与校验和；对接已有 dataset 算子的输出规范。
- **与开源版关系**：新增——开源版 dataset 模板面向本地/已有存储。
- **难点与风险**：HF 网络可达性（国内需 hf-mirror 配置项）；脚本型数据集存在任意代码执行风险，需白名单或提示用户审阅；大表格数据集的存储成本预估。
- **公共依赖**：与 B3 共用 HF/ModelScope 对接层（凭据、镜像源、断点续传）。

### B3. 模型导入支持 HuggingFace / 魔塔（#13）
- **定义与用户价值**：一键拉取模型权重到模型仓库，衔接后续注册/微调/部署链路。
- **实现思路**：复用/扩展开源版已有 `model_download` 模板，增加 HF/ModelScope source 类型参数与凭据注入；下载后走 model_register 登记规格。
- **与开源版关系**：扩展——底座模板已有，新增源类型与断点续传/完整性校验。
- **难点与风险**：大权重文件（几十至几百 GB）的磁盘水位与失败重试；gated 模型的 token 凭据管理（接入平台密钥体系，勿落明文）。

### B4. datax-import 算子 + 多数据源支持（#12、#14）
- **定义与用户价值**：以 datax 为引擎的结构化数据导入算子，支持 mysql/postgresql/clickhouse 源到平台存储，让传统数仓数据零代码进入 MLOps 链路；与开源 datax 算子形成读写闭环。
- **实现思路**：基于开源 `job-template/job/datax` 封装 import 方向模板，JSON 配置由表单生成（源库类型/表/where/分片列到 reader 配置）；连接信息走平台密钥，不进 DAG JSON 明文。
- **与开源版关系**：扩展——datax 算子已有，新增 import 方向与三种 reader 插件（mysqlreader/postgresqlreader 为 datax 官方自带，clickhouse reader 依赖社区插件需验证）。
- **难点与风险**：datax 对 clickhouse 的 reader 插件成熟度一般，可能退化为 JDBC reader；大表全量同步的分片与限速策略；datax json 中的密码脱敏（启用 datax 配置文件加密机制）。

### B5. Hadoop 模板：HDFS / Hive / Spark 命令（#16）
- **定义与用户价值**：在 pipeline 中直接提交 hdfs shell、hive SQL、spark-submit（含 spark on k8s），把平台与已有大数据集群打通，覆盖「数据在 Hadoop 体系」的主流国企/金融客户场景。
- **实现思路**：新增 `job-template/job/hadoop` 模板：轻量客户端镜像（hdfs/hive/beeline/spark-submit CLI），两种模式——直连客户已有 yarn 集群（KRB5 认证参数化）与 spark on k8s operator；可参考 `images/jupyter-notebook/bigdata` 已有客户端栈作为镜像基础。
- **与开源版关系**：新增（模板层）；bigdata notebook 镜像的客户端能力可复用。
- **难点与风险**：Kerberos keytab/票据生命周期管理；spark on k8s 与客户 yarn 二选一的架构分歧需在 spec 中定死（建议 v1 只做客户端直连，spark on k8s 列为后续增强）；大数据版本碎片化（CDH/HDP/开源 3.x）导致客户端兼容矩阵庞大。

### B6. 文本数据处理算子集（#17）
- **定义与用户价值**：文档理解与语料加工流水线：pdf/doc/图片 OCR 转 markdown（paddleocr-vl）、markdown 抽问答对、问答扩展、异常数据清理、规则/模型过滤、隐私替换（脱敏）、文本统计——直接服务大模型微调数据准备场景。
- **实现思路**：每个能力封装为独立 job-template（对齐本仓库 gov-social-llm 的算子封装惯例：start.py + Dockerfile + args.json + 测试），paddleocr-vl 走 GPU 推理；问答扩展与过滤支持调用已部署的 LLM 服务。
- **与开源版关系**：新增——开源版 video-audio 模板仅覆盖媒体；本仓库 gov-social-llm 已有同构私有实现（gov-distill-gen/gov-distill-filter），企业版可作为其泛化版本，代码组织上保持算子隔离（算子间禁止跨模块 import，公共约定仅限 manifest 性质共享库）。
- **难点与风险**：paddleocr-vl 的 GPU 依赖与模型体积（镜像数 GB）；隐私替换的召回/误杀评估缺客观标准；「清理异常数据」规则集需沉淀为可配置规则库而非硬编码。

### B7. 图像数据处理算子集（#18）
- **定义与用户价值**：训练前的标准图像预处理链：质量评估、去噪、缩放、标准化、裁剪、均衡化、色彩空间转换、几何变换——视觉训练数据集加工的基础设施。
- **实现思路**：OpenCV/PIL 封装单任务模板（CPU 即可），参数全部表单化（目标尺寸、插值方式、翻转概率等）；大数据量场景可选 ray 分布式批处理（与开源 ray 模板组合）。
- **与开源版关系**：新增——开源版无图像加工算子。
- **难点与风险**：纯参数堆叠型算子的表单配置项庞大，UI 需折叠分组；原地写回 vs 新目录输出的语义需统一定义（建议默认新目录 + manifest，避免污染源数据集）。

### 主题 B 小结
8 项中仅 B3 是对已有模板的扩展，其余为新增，是 24 项中「纯新增加权」最高的主题。B2/B3 共用 HF/ModelScope 对接层；B6/B7 与主题 C 共同构成「企业版算子库」交付物，建议按「HF/魔塔对接层 / hadoop / 文本 / 图像」四个独立 spec 推进。

---

## §3 主题 C：特征处理算子集（#15）

### C1. 特征处理算子框架 + 22 子算子
- **定义与用户价值**：面向结构化数据（表格）建模场景，在 pipeline 画布上以拖拽方式完成端到端特征工程：清洗到变换到编码到降维/筛选到采样/拆分。用户价值核心是把 sklearn 式的 Notebook 代码工程「模板化」——非算法背景分析师也能组装标准特征链路，算法工程师省去重复造轮子。这是企业版「降低 AI 使用门槛」叙事中分量最重的一块，也是同类竞品的标配能力。
- **实现思路**：
  1. 子算子按 6 个家族批量实现（每家族 1–2 个模板 + 参数表单，而非 22 个独立模板）：
     - 组合与去重（union、join、去重）：pandas/ray 折叠，join 需表单化 keys 与 how；
     - 数值变换（boxcox、二值化、类型转换、dct、函数转换、ma 移动平均、多项式展开）：函数转换仅支持白名单表达式（禁用对用户输入的 eval，避免 lambda 序列化安全问题）；
     - 编码与缺失（hash、统计量转换、one-hot、异常值检测、填充缺失值、去除单一值变量、删除高缺失率列、获取统计量）；
     - 标准化与离散化（最大绝对值/最大最小/z_score 标准化、正则化、等宽/等频/聚类离散化）；
     - 结构操作（索引处理、排序、执行 sql、hadamard 乘积、特征组合、相关性计算）：执行 sql 复用开源版已集成的 sqllab 引擎连接体系；
     - 降维/筛选/拆分/采样（pca、卡方降维、特征重要性 rf/lr/xgb 到 iv/互信息/方差、列内/列间/行间拆分、svd、随机/分层/过/欠采样）：采样用 sklearn/imblearn。
  2. 统一骨架：所有子算子共享同一输入输出契约（parquet/csv 输入，parquet 输出 + schema manifest），共享一个基础镜像（pandas/sklearn/imblearn/xgboost），按家族只换入口脚本与表单 schema（对齐 gov-social-llm 算子封装惯例：start.py + args.json + Dockerfile + 测试）。
  3. 拟合-应用分离：fit 类算子输出「变换器产物」（scaler/分箱边界/one-hot 映射表）到工作目录并在 UI 可视查看，供下游 transform 与推理链路引用。
- **与开源版关系**：新增——开源版 `job-template/job/` 无任何特征处理模板；依赖底座全部现成（argo workflow、dataset 算子、ray 模板可作分布式后端）。
- **难点与风险**：
  - 量大是首要风险：22 子算子若逐个精雕将拖垮交付节奏，必须按家族批量交付、家族内参数从简（v1 只做单机 pandas，ray 分布式留 v2）；
  - 拟合-应用分离是正确性红线，漏做会导致训练/线上特征漂移这一类最难排查的缺陷，列为硬性验收项；
  - hadamard、多项式展开等数学性算子的参数可解释性差，表单必须配 tip 与示例（与 #22 参数 tip 能力联动）；
  - 过采样（SMOTE 类）在类别极度不平衡时的行为需文档化预期。

### 主题 C 小结
这是全部 24 项中工作量最大的单体。核心设计决策三条：按 6 家族批量交付而非 22 个独立 spec；统一输入输出契约与共享基础镜像；fit/transform 分离作为硬性验收项。建议独立成一份 spec，并给出 v1（单机）/ v2（ray 分布式）的分期边界。

---

## §4 主题 D：传统机器学习与自动调参

### D1. ray-sklearn 分布式训练算子（#19）
- **定义与用户价值**：sklearn 单机训练在大表数据上跑不动，ray-sklearn（Ray Train + joblib backend）提供数据并行/任务并行的 sklearn 生态分布式能力，让 GridSearchCV、preprocessing、模型训练横向扩展，补齐开源版「sklearn 只能单机」的短板。
- **实现思路**：扩展开源版已有 `ray` / `ray_sklearn` 模板：补齐参数表单（n_workers、cpus_per_worker、数据输入源），默认以 joblib 后端包裹 sklearn 估计器；输出模型产物到统一工作目录衔接 model_register。
- **与开源版关系**：扩展——底座模板已在开源版（ray、ray_sklearn 目录已确认存在），企业版重点是参数化完备与数据集/特征算子（主题 C）的输入输出契约打通。
- **难点与风险**：ray 与 sklearn/joblib 的兼容矩阵（ray 对 python 版本敏感）；分布式训练对「单机可复现」的挑战（固定随机种子与数据分片策略）；ray head 节点故障的作业恢复能力有限，超大作业建议文档引导改用 ray datasets。

### D2. 传统机器学习算法集（#20）
- **定义与用户价值**：把 13 类常用算法（ar/arima 时间序列、random-forest(-regression)、lr、lightgbm、knn、kmeans、gbdt、decision-tree、pca、lda、catboost、xgb）封装成「选算法-填参数-出模型+指标」的零代码算子，让非算法背景用户完成分类/回归/聚类/时序建模，并直接衔接模型注册与部署。
- **实现思路**：
  1. 统一算法算子框架：一个通用模板 + 每算法一份「参数 schema + 指标计算配置」，而非 13 个独立 Dockerfile（对齐主题 C 家族化策略与算子隔离原则）；
  2. 输出契约统一：模型文件（joblib/onnx 可选）+ 训练指标 JSON（与 #21 模型评估、模型指标可视化下游衔接）；开源 xgb 模板作为输出契约参考基准；
  3. ar/arima 用 statsmodels；lightgbm/catboost/xgb 三大 GBDT 并存（v1 全保留，不强行归一）。
- **与开源版关系**：新增为主——开源版仅 xgb 有模板；算法表单中预留超参搜索挂接点（衔接 D3）。
- **难点与风险**：13 个算法参数空间差异大，表单 schema 治理成本高（建议 JSON Schema 驱动动态表单）；时序类输入数据形状（时间列/频率）与其他算法不同，表单需条件分支；分类/回归/聚类/时序四套评价指标口径需在 spec 中定死，避免各算子自定义。

### D3. 基于单机/分布式的自动超参搜索（#24）
- **定义与用户价值**：用户声明搜索空间（lr、树深、batch size 等）与搜索算法（网格/随机/贝叶斯/TPE/Hyperband），平台自动拉起多组训练任务并汇报最优 trial，覆盖单机与分布式训练任务。训练平台高频刚需，也是 GPU 资源营销点。
- **实现思路**：
  1. 底座选 NNI（⚠️ 开源版 `myapp/models/model_nni.py` 与 `images/nni/Dockerfile` 已存在——NNI 数据模型与镜像底座在开源代码中已有痕迹，本项定位为「复用唤醒 + 企业版增强」而非全新开发）；
  2. 单机：NNI trial 直接跑；分布式：NNI trial 内嵌 tf/pytorch job；
  3. 搜索空间与算法表单配置，产出最优超参一键回填训练任务表单；
  4. v1 范围收敛：TPE + 网格/随机 + 单机 + 传统 ML/DL 模板；贝叶斯进阶与 NAS 留 v2。
- **与开源版关系**：复用 + 增强——开源代码已有 NNI 模型与总资源视图中的 NNI 关联逻辑；企业版价值在于把已有 NNI 底座做成完整产品化闭环（搜索空间 UI、trial 并发与配额联动、结果可视化、最优参数回填），而非从零实现。
- **难点与风险**：NNI 社区活跃度下降，长期可能需迁移到 optuna/ray tune（spec 中预留 trial 协议抽象层降低迁移成本）；trial 数量大时对配额/计量计费模块的联动计费口径要提前定义；分布式 trial 的日志聚合与失败重试策略。

### 主题 D 小结
三者依赖上呈递进关系——D1（分布式底座）到 D2（算法集，表单内挂接 D3）到 D3（调参闭环）。关键认知修正：NNI 超参搜索底座在开源代码中已存在，企业版定位应为「产品化闭环增强」，后续 spec 验收标准应聚焦 UI/配额/回填闭环而非底层框架。

---

## §5 主题 E：模型处理与链路共享

### E1. 模型处理：模型评估 + 模型格式转换（#21）
- **定义与用户价值**：「模型评估」对已注册模型跑标准评估集（分类/回归指标、混淆矩阵、ROC 等）并出报告，形成「训练到评估到注册到部署」的完整质量门禁；「模型格式转换」把训练产物（pytorch pth、sklearn joblib、tf saved_model 等）转为部署所需格式（onnx、triton 后端格式、tensorrt engine），消除「训练能跑、部署不认」的断点。
- **实现思路**：
  1. 模型评估：评估 job 模板（输入=模型产物+评估数据集，输出=指标 JSON+图表数据），指标口径复用 D2 的四套指标体系，结果落库供模型指标可视化消费——评估算子与可视化是同一契约的两端，必须在同一 spec 中定义；
  2. 格式转换：在 `job-template/job/model_register` 旁新增 `model_convert` 模板，按「源格式×目标格式」矩阵实现（v1 收敛三条主路径：pytorch 到 onnx、sklearn 到 onnx（skl2onnx）、saved_model 到 tflite/serving，其余矩阵项明确标注不支持）；
  3. 转换产物登记为模型新版本，保持血缘（来源版本号写入 expand 字段，与 gov-social-llm 的 manifest 血缘设计同构）。
- **与开源版关系**：新增——开源版有 model_register/model_offline_predict/deploy-service，但无独立评估与转换算子；离线预测模板可提供评估算子的「读模型+跑数据」骨架参考。
- **难点与风险**：格式转换矩阵是维护黑洞（框架版本×格式组合），必须用「支持矩阵白名单 + 明确报错」策略控制范围；onnx 转换对含自定义算子的模型失败率高，需给出降级路径（自定义推理镜像）；评估的标准指标口径需与模型管理模块对齐，避免两套定义。

### E2. 自定义任务模板参数类型扩展（#22）
- **定义与用户价值**：补齐 int、float、list、bool、json 五种标量/容器类型，以及 workdir、image、select-input、select2、project 五种子类型，支持参数 tip 提醒。价值在于让企业用户把内部算法封装成「给别人用得顺」的算子——参数表单表达力直接决定算子生态繁荣度，是主题 B/C/D 所有算子表单的公共基础设施。
- **实现思路**：
  1. 参数类型系统落在 pipeline DAG 节点参数 schema：每种类型定义「表单控件 + 序列化格式 + 校验规则」三元组；list/json 用前端动态控件，workdir 自动挂共享工作目录并注入环境变量，image 弹镜像选择器（对接镜像仓库模块），select-input 选择上游任务输出，select2 下拉远程选项源，project 绑定项目内资源；
  2. tip 提醒作为参数 schema 标准字段（describe + 示例值），渲染为表单 tooltip；
  3. 校验在后端统一做（类型/必填/范围），不信任前端。
- **与开源版关系**：扩展——开源版自定义算子注册链路已存在，本项是对参数 schema 子系统的类型扩充；新类型对旧 DAG JSON 向后兼容（未知类型按 string 降级）。
- **难点与风险**：select-input 造成参数与 DAG 拓扑耦合，任务删除/改名时的引用一致性需级联校验；json 类型成为「万能后门」，容易破坏表单可校验性（建议 json 类型必须配 JSON Schema 声明）；该能力是所有算子表单的前置依赖，后续 spec 排期应优先于主题 B/C/D 的算子实现。

### E3. 示例 pipeline 任务流导入导出（#23）
- **定义与用户价值**：面向「链路共享/自动学习」场景，把调好的 pipeline 导出为文件（含 DAG 结构、算子参数、全局常量模板），供他人/他环境一键导入；支撑示例库分发、最佳实践沉淀、跨环境迁移（开发到生产）与售前 demo 快速搭建。
- **实现思路**：
  1. 导出格式为自描述 JSON 包（pipeline 元信息 + dag_json + 参数占位符 + 依赖清单：算子镜像列表、数据集/模型引用），对齐本仓库 `pipelines/*.json` 与 `scripts/validate_pipelines.py` 的既有校验惯例——导出即过校验器；
  2. 导入时做依赖解析：缺失算子/镜像给出缺口清单而非静默失败；含项目绑定（project 类型）的参数转为导入向导中的必填项；
  3. 与 AIHUB「示例 pipeline 任务流导入导出」口径一致，导出包可直接作为 aihub 分发物（预留）。
- **与开源版关系**：扩展——开源版已有 pipeline 的 dag_json 持久化与文件上传表单，本项重点是把「文件上传」升级为「带依赖解析与校验的导入导出协议」。
- **难点与风险**：跨环境差异（镜像 tag、集群、存储路径）是导入失败主因，导出包中环境相关值必须参数化为占位符并在导入向导中收集；DAG schema 演进的版本兼容需要包内记录 schema version 并做前向兼容策略；密钥类参数严禁进入导出包（导出前强制脱敏扫描，安全红线）。

### 主题 E 小结
三项的公共特征是「打通闭环」：E1 打通训练到部署的质量闭环，E2 打通算子生态的表达力底座，E3 打通最佳实践的传播闭环。E2 是公共依赖，建议在后续 spec 拆分中排期最优先。

---

## §6 主题 F：具身智能 / VLA 训练（新方向扩展）

> 来源口径：本主题非企业版功能文档 `[...]` 标注提取，为具身智能新方向的能力补齐与售前叙事。技术底座锚定 HuggingFace LeRobot（0.6.2 验证）：`lerobot-train`/`lerobot-eval` CLI 训练评测形态与本仓库已验证的算子封装模式（gov-social-llm 的 build_train_cmd + dry-run + manifest 血缘）同构；策略库 ACT/Diffusion/VQ-BeT/TDMPC/VLA（SmolVLA、π0 等）；数据格式 LeRobotDataset v3（parquet+mp4+json）。
> 三项已对齐的范围决策：① v1 GPU 锚点为单卡 ≤24G（ACT/Diffusion/SmolVLA 级），π0/GR00T 等大 VLA 全量训练列 v2 并注明 A100 80G 级卡型要求；② 仿真器 v1 用 lerobot 原生 gym 环境（MuJoCo/Aloha sim 等，headless 可跑），Isaac Lab 列 v2；③ F4 平台侧只做产物分发与指标回流，不碰真机控制链路。

### F1. LeRobot 训练算子（模板 + 镜像）
- **定义与用户价值**：将 HuggingFace LeRobot 的 `lerobot-train` CLI 封装为 pipeline 算子，覆盖 VLA/模仿学习策略训练（ACT、Diffusion、VQ-BeT、SmolVLA 等），具身智能训练与平台既有训练链路同构——拖拽配置、GPU 调度、日志、指标、模型注册全复用。
- **实现思路**：对齐算子封装惯例（start.py + args.json + Dockerfile + 测试）：`lerobot-train --policy.path=… --dataset.repo_id=… --batch_size=… --steps=… --output_dir=…` 参数表单化，dry-run 校验；产物（checkpoint + train_config.json + 指标）落统一工作目录并登记 manifest 血缘（同构 gov-social-llm）；复用 `job-template/job/pytorch` 的 PyTorchJob 底座（v1 单机，多卡 accelerate 分布式列 v2）；策略选择 select2 下拉预置策略路径；v1 锚定单卡 ≤24G，大 VLA 全量训练列 v2。
- **与开源版关系**：新增——`job-template/job/` 无具身智能模板；训练底座（PyTorchJob CRD + volcano + GPU 调度 + 镜像自定义）现成。
- **难点与风险**：lerobot 版本迭代快（策略 API 变动），镜像需锁版本并预留升级验证；策略库依赖体积大（torch + lerobot + 各策略附加依赖，镜像 10G+ 级）；VLA 策略需拉取基础权重，HF 网络可达性（mirror 配置，联动 B2/B3 对接层）。

### F2. LeRobotDataset 数据集接入与画像
- **定义与用户价值**：LeRobotDataset v3（parquet + mp4 + json 元数据）是具身智能数据的事实格式之一；接入让真机遥操作/仿真采集的 episode 数据进入平台数据集管理，配套 episode 级画像，衔接 F1 训练输入契约。
- **实现思路**：扩展现有 `job-template/job/dataset` 模板家族：新增 `dataset/lerobot-import`（本地路径 / Hub repo id 双来源，大库走 StreamingLeRobotDataset 流式拉取）；导入后生成画像 manifest（episode 数、总帧数、fps、分辨率、任务标签分布、视频时长直方图）接入数据集画像体系；episode 抽帧可回传 LabelStudio 标注（复用已交付的双向接口）；view_dataset 登记 lerobot 数据集类型。
- **与开源版关系**：扩展——dataset 模板家族新增成员；数据集管理/画像/标注链路现成。
- **难点与风险**：v3 含视频文件，存储成本高（对象存储 vs NFS 选型）；Hub 流式拉取的网络与断点续传；数据格式版本兼容（v2.1 → v3 有格式变更，导入需声明兼容版本范围）。

### F3. 仿真评测 job
- **定义与用户价值**：训练产出的策略在仿真环境 rollout 评测（成功率、轨迹指标），形成「训练 → 评测 → 注册」质量门禁，对齐 E1 模型评估闭环叙事；lerobot 原生 gym 环境（MuJoCo/Aloha sim 等）headless 可跑，单卡 ≤24G 内完成。
- **实现思路**：新增 `job-template/job/lerobot-eval` 模板：输入 = checkpoint（引用 F1 产物）+ 仿真环境名 + 评测 episode 数；封装 `lerobot-eval` CLI；输出评测指标 JSON（成功率/平均回报/轨迹长度）对齐 E1 指标契约与模型指标可视化消费端；评测视频抽样保存供 UI 预览。
- **与开源版关系**：新增——开源版无评测算子；与 E1（模型评估）共用指标契约，spec 拆分时建议同批定义。
- **难点与风险**：MuJoCo headless EGL 渲染在无 GPU 节点性能差，需卡型亲和配置；环境名与策略任务空间的匹配性校验（错配应显式报错）；评测结果与训练 run 的血缘关联需 run id 传递约定。

### F4. checkpoint 分发与指标回流（边缘闭环）
- **定义与用户价值**：训练/评测通过的 checkpoint 注册进模型仓库后，边缘侧（真机运行机）通过平台 API 拉取部署，真机运行指标回流平台形成数据飞轮叙事。平台只做「产物分发 + 指标接收」，真机实时控制（USB 串口/推理循环）都在边缘机本地，不纳入平台链路。
- **实现思路**：复用 model_register/model_download 底座：checkpoint 注册为模型版本，边缘机以 token 拉取；指标回流 = 边缘机 POST 最小指标 JSON 到平台 API，落模型指标体系（与 E1 可视化共用）；血缘串联：数据集 → 训练 run → 评测 → 模型版本 → 边缘部署 → 回流指标。
- **与开源版关系**：扩展——模型注册/下载/指标底座已有，新增边缘拉取协议与回流 API。
- **难点与风险**：边缘机网络环境（离线/弱网），需断点续传与导出兜底；回流指标无强制 schema 时易进脏数据，需定义最小指标契约；安全边界（边缘机 token 吊销、防越权跨项目拉取模型）。

### 主题 F 小结
4 项依赖递进：F2（数据）→ F1（训练）→ F3（评测）→ F4（分发回流）。F1 表单依赖 E2（select2/tip），F3 对齐 E1 指标口径，建议排期序置于 E 组后，视客户售前需求可前插。与主题 B 的公共依赖：F1/F2 的 HF 权重与数据集拉取复用 B2/B3 的 HF/ModelScope 对接层（镜像源、凭据、断点续传）。

---

## §7 跨主题共性结论

### 7.1 复用/扩展/新增分布

| 定位 | 条目 | 说明 |
|---|---|---|
| 复用 + 增强（⚠️ 文档标注偏保守） | #5、#8、#24 | 调度五要素均已实现（仅余入口与清理完备性增量）、NNI 底座；#9 经二轮校验改判纯壳新建 |
| 扩展（开源底座已有，补链路） | #1、#3、#4、#13、#12/#14、#19、#22、#23 | 卡型/GPU 语义、HF 模型导入、datax import、ray-sklearn、参数类型、导入导出协议 |
| 新增 | #2、#6、#7、#9、#10、#11、#15、#16、#17、#18、#20、#21 | RDMA、编排体验层、控制流算子、特征处理、hadoop、文本/图像算子、ML 算法集、模型评估/转换 |

### 7.2 公共依赖与建议排期序

公共依赖链：**E2（参数类型系统）是 B/C/D 所有算子表单的前置**；A2/A3（异构资源抽象）是 A4 的前提；B2/B3 共用 HF/魔塔对接层；D2 的指标口径契约被 E1 复用；主题 F 的 F1 依赖 E2 表单类型与 B2/B3 HF 对接层，F3 对齐 E1 指标契约。

建议排期序：E2 → 主题 A（调度与资源）→ 主题 B（算子生态）→ 主题 C（特征处理）→ 主题 D（ML/调参）→ E1/E3（模型处理与链路共享）→ 主题 F（具身智能，视客户售前需求可前插）。

### 7.3 全局设计约定（沿袭本仓库既有决策）

1. 算子封装统一惯例：start.py + args.json + Dockerfile + 配套测试，Pipeline JSON 需过 `scripts/validate_pipelines.py` 校验；
2. 算子隔离优先：算子间禁止跨模块 import，公共约定收敛到单一共享库（manifest 性质）；
3. CLI 参数约定：算子命令行统一 flag-value 单元素风格；
4. 密钥与敏感信息：一律走平台密钥体系，禁止进入 DAG JSON、导出包与日志；
5. 所有算子输出遵循统一产物契约（模型/指标 JSON/manifest 血缘），衔接模型注册与指标可视化。

### 7.4 横切风险

- **文档与代码偏差**：3 处「标注企业版但开源已有」，后续 spec 与产品话术需对齐实际边界，避免重复建设；
- **卡型×镜像×框架组合爆炸**：A3/C/D 均受影响，需要统一的镜像元数据登记与兼容性约束机制；
- **表单 schema 治理**：E2 的类型系统、D2 的 13 算法参数、C 的 22 子算子参数共用一套治理方案（JSON Schema 驱动动态表单），避免三套并行。
- **上游快速迭代**：主题 F 锚定的 lerobot/LeRobotDataset v3 均处于活跃演进期，镜像锁版本 + 兼容版本范围声明是共性防线，评测/回流契约应尽量落在平台自有 schema 而非上游格式。

## §8 后续 spec 拆分建议（约 11 份）

| 序 | 建议 spec | 覆盖条目 | 备注 |
|---|---|---|---|
| 1 | 自定义模板参数类型系统 | #22 | 最优先，公共依赖 |
| 2 | 异构 GPU/RDMA 资源调度 | #1、#2、#3、#4 | 含 device-plugin 抽象与透传 |
| 3 | Pipeline 调度增强 | #5、#8、#9 | 补录/超时/优先级 |
| 4 | 编排体验：I/O、常量、可视化、暂停恢复、运行中监听 | #6、#7 | 含 artifact 契约 |
| 5 | HF/魔塔对接层与数据同步算子 | #10、#11、#12、#13、#14 | 逻辑节点可并入或独立 |
| 6 | Hadoop 模板 | #16 | v1 客户端直连 |
| 7 | 文本与图像数据加工算子 | #17、#18 | 泛化 gov-social-llm 既有实现 |
| 8 | 特征处理算子集 | #15 | v1 单机 / v2 ray |
| 9 | 传统 ML 算法集与 ray-sklearn | #19、#20 | 指标口径契约定义 |
| 10 | 模型评估/格式转换与自动调参、导入导出 | #21、#24、#23 | NNI 闭环 + 转换矩阵 + 导出协议 |
| 11 | 具身智能/VLA 训练功能组 | F1–F4 | 新方向扩展；v1 单卡 ≤24G 锚点，F3 与 E1 指标契约同批定义，F1/F2 复用 B2/B3 HF 对接层 |

> 拆分仅为建议，正式排期由 writing-plans 阶段结合资源与优先级确定。
