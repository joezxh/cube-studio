# gov-distill-filter — 三闸过滤算子

对 `gov-distill-gen` 产出的 `raw.jsonl` 做质量收紧，导出可直接训练的数据集（spec §2.2）。

## 三闸

| 闸 | 函数 | 判据 |
|---|---|---|
| 1 格式 | `gate_format` | 教师输出可 `json.loads`（剥 ```json 围栏）且符合任务 schema |
| 2 一致性 | `gate_consistency(k=2)` | 同 `seed_id` 多候选投票，众数票数 ≥k 保留（仅留众数候选）；T3/T4 无 label 按全字段规范化投票 |
| 3 规则 | `gate_rules` | 长度 ≤max_len(4096)、无控制字符、8 字滑窗重复片段占比 ≤30% |

## 三格式导出（`dump`）

- `train_alpaca.jsonl`：`{"instruction","input","output"}`（LLaMA-Factory alpaca）
- `train_sharegpt.jsonl`：`{"conversations":[{human},{gpt}]}`（LLaMA-Factory sharegpt）
- `kev_format.jsonl`：`{"state","questions","answers"}`（kev 对照实验用；label→department 映射读 `docs/task-spec/kev-mapping.json`，**示例映射待业务方补全**）

## args

`--raw` `--task` `--k` `--out-dir` `--raw-manifest`（血缘 parent）。缺省 schema/kev 文件按仓库 `docs/task-spec/` 定位。

## 产出

`{out-dir}/`：三训练格式 JSONL + `filter_report.json`（各闸通过数、label 分布、pass_rate）+ `manifest.json`。

## 本地

```bash
pytest tests/test_filter3.py -v
```
