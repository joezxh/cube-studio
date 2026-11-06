# gov-social-llm — 社会治理大模型蒸馏与微调（P0–P2 交付）

在 **cube-studio** 平台上以「方案 A：薄算子 + 标准开源框架」落地社会治理领域模型的
蒸馏数据生产、学生微调（LoRA / kev 双臂）与评测验收。**平台只做调度**，AI 能力封装进
自定义镜像算子（入口统一 `python start.py`，退出码 0=成功），数据经 `/mnt/gov` 下的
JSONL 文件 + `manifest.json` 血缘在算子间传递。

> 规格：`docs/superpowers/specs/2026-11-06-gov-social-llm-distill-design.md`
> 计划：`docs/superpowers/plans/2026-11-06-gov-social-llm-p0-p2.md`

## ① 目录导览

```
gov-social-llm/
├── ops/                    # 6 个自定义算子代码包（各含 start.py + Dockerfile）
│   ├── gov-manifest/       #   共享血缘库（唯一可被跨算子 import）+ CLI(generate|verify|seal)
│   ├── gov-distill-gen/    #   教师多候选采样蒸馏生成
│   ├── gov-distill-filter/ #   三闸过滤 + alpaca/sharegpt/kev 三格式导出
│   ├── gov-eval/           #   指标核心 + smoke/dev/blind/safety/bench 五模式
│   ├── gov-sft/            #   LLaMA-Factory LoRA/QLoRA 封装
│   └── gov-kev/            #   kev(system-one) 对照臂封装
├── pipelines/              # 3 条可导入 cube-studio 的 Pipeline JSON
├── scripts/                # validate_pipelines.py 校验器 + eval_split.py 切分脚本
├── serving/gov-teacher-serve/  # 教师服务 deploy-service 参数包（含 4090/5090 presets）
├── docs/task-spec/         # schema、prompt 模板、kev-mapping.json
├── tests/                  # 本地 pytest（不依赖 GPU/网络）
└── conftest.py / pytest.ini / requirements-dev.txt
```

## ② P0 操作手册（从镜像到 Pipeline）

1. **构建算子镜像**（在 `ops/<算子>/` 内）：
   ```bash
   docker build -t REGISTRY/gov-distill-gen:v0.1.0 .   # 其余算子同理
   docker push REGISTRY/gov-distill-gen:v0.1.0
   ```
   GPU 算子（gov-sft / gov-kev）镜像已设 `TORCH_CUDA_ARCH_LIST="8.9;12.0"`、基础镜像 CUDA≥12.8。
2. **平台「镜像管理」登记** 各镜像。
3. **平台「模板自定义」注册算子**：类型/参数对照 spec §2.2；入口 `python start.py`，args 键一律以 `--` 开头。
4. **导入 Pipeline**：在 Pipeline 页导入 `pipelines/gov-p0-env-check.json`（先自检环境）→
   `gov-p1-eval-build.json`（构建并封存评测集）→ `gov-p2-distill-line.json`（蒸馏主线）。

## ③ 数据目录规范（/mnt/gov 四子树 + manifest）

```
/mnt/gov/
├── seeds/      种子（raw→clean→v1）
├── distill/    蒸馏产出 {task}/{ver}：raw.jsonl / filtered/(alpaca|sharegpt|kev)
├── eval/       评测集：raw / masked / dev / blind(封存只读) / redteam / smoke
└── models/     底座与教师权重（不打入镜像，运行时挂载）
sft/  kev/       训练产出（adapter / run + train_manifest.json）
```
每个产出目录均有 `manifest.json`（`gov_manifest.write_manifest`），含 `self_digest`、
`parents[].digest` 上游血缘、`files[].sha256`；`seal` 后置只读。`DATA_ROOT=/mnt/gov` 经
Pipeline `global_env` 注入。

## ④ 两套 GPU 环境差异（spec §3.2）

| 维度 | 2×RTX 4090 48G | 2×RTX 5090 32G |
|---|---|---|
| 计算架构 | Ada `sm_89` | Blackwell `sm_120` |
| 教师 AWQ `--gpu-memory-utilization` | 0.90 | 0.85 |
| 教师 `--max-num-seqs` | 32 | 16 |
| 适配要点 | 显存余量大，可放并发 | 显存偏紧，降 KV 并发防 OOM |
| 权重架构支持 | 均需 CUDA≥12.8 覆盖 sm_120 | 同左 |

取值以 `serving/gov-teacher-serve/args.json` 的 `presets` 为准。

## ⑤ 本地开发

```bash
pip install -r requirements-dev.txt
pytest                    # 全量：schema/manifest/distill/eval/sft/kev/validate（不依赖 GPU/网络）
python scripts/validate_pipelines.py   # 校验 3 条 Pipeline JSON 格式（exit 0=通过）
```
Windows 注意：`pytest.ini` 已设 `--basetemp=.pytest-tmp`，规避 seal 只读残留导致的
系统临时目录清理 WinError 5（详见 conftest.py 的只读清理 fixture）。
