# gov-eval — 评测算子

对社会治理学生模型做能力/安全/性能验收（spec §2.2、§3.3 验收线）。指标核心为纯函数，
`start.py` 提供五模式；smoke/bench 经 HTTP 调用被测服务，本算子自身为 CPU。

## 五模式

| `--mode` | 输入 | 输出 |
|---|---|---|
| `smoke` | `--eval-set`(含 state) + `--endpoint` | 前 `--limit` 条逐条推理，可解析率（服务连通性） |
| `dev` | `--eval-set`(gold) + `--pred` + `--task` | `score_all` 全指标；`--redteam` 违规率；`--judge` 事实一致性抽检 |
| `blind` | 同 dev，路径含 `/blind/` | 同 dev，**manifest 留痕 `blind_touched_at`**（盲测解封审计） |
| `safety` | `--redteam` | 仅红队违规率 |
| `bench` | `--eval-set` + `--endpoint` | 并发 `--concurrency` 压测 P50/P95 延迟（perf_counter） |

## 指标（`metrics.score_all` → metrics.json）

`macro_f1` / `per_class_p` / `per_class_r` / `high_risk_recall` / `false_alarm_rate` /
`format_compliance` / `refusal_rate`（+ 可选 `redteam_violation`）。

- `format_compliance`：拒答行（含"无法回答"）不计入分母，与 `refusal_rate` 分离度量。
- `schema=None` 时跳过格式检查（记 null）。
- 自包含 `parse_output`，不跨算子依赖 gov-distill-filter（仅共享 gov_manifest 库）。

## 产出

`{out-dir}/metrics.json` + `report.md` + `manifest.json`（`op="gov-eval"`）。

## 本地

```bash
pytest tests/test_metrics.py -v
```
