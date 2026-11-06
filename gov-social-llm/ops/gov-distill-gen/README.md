# gov-distill-gen — 教师蒸馏批量生成算子

方案 A「薄算子」之一（spec §2.2）。读取种子案情 JSONL，按 `distill-{task}-{ver}.md` prompt 模板
构建消息，**并发调用教师模型 OpenAI 兼容接口**，多候选采样写入 `raw.jsonl`，供下游
`gov-distill-filter` 三闸过滤。CPU 算子，本身不占 GPU；教师服务地址经 `--endpoint` 传入。

## 关键参数（注册为平台算子后的 args）

| 参数 | 缺省 | 说明 |
|---|---|---|
| `--seeds` | 必填 | 种子 JSONL（行：`{"seed_id","task","state"}`） |
| `--task` | 必填 | 任务标识 T1..T4 |
| `--prompt-version` | v1 | 对应 `docs/prompts/distill-{task}-{ver}.md` |
| `--endpoint` | 必填 | 教师 `/chat/completions` 集群内地址 |
| `--model` | teacher | 教师服务模型名 |
| `--n-candidates` | 3 | 每种子采样数（self-consistency 投票基础） |
| `--temperature` / `--top-p` / `--max-tokens` | 0.7 / 0.95 / 1024 | 采样参数 |
| `--concurrency` | 4 | 线程并发 |
| `--no-resume` | 关 | 断点续跑：默认跳过 out 中已有 `(seed_id,candidate_id)` |
| `--out-dir` | 必填 | `/mnt/gov/distill/{task}/{ver}` |
| `--seed-manifest` | — | 上游种子 manifest（登记血缘 parent） |

## 产出

```
{out-dir}/
├── raw.jsonl         # 每行 {seed_id,task,prompt_version,candidate_id,state,messages,output,meta}
├── gen_report.json   # {seeds_total,seeds_ok,seeds_failed,failed[],total_rows}
└── manifest.json     # gov_manifest.write_manifest(op="gov-distill-gen", …)
```

**容错**：某种子重试耗尽（`call_teacher` retries=3）仅记入 `gen_report.failed[]`，不中断整体批次。

## 本地

```bash
pytest tests/test_distill_gen.py -v      # HTTP 全 monkeypatch，不依赖网络
```
