# 数据集表格一键探索（S4）设计文档

> 日期：2026-11-07 ｜ 来源：docs/企业版功能.md L43「数据管理-数据集管理：[对表格数据支持数据集一键探索功能]」
> 状态：待评审

## 1. 背景与现状

- 开源版已有 `Dataset` 模型（name/version/segment/path/features/file_type 等）与数据集 CRUD 页面。
- **关键缺口**：`myapp/views/view_dataset.py` 的 `preview` API（L398-420）是硬编码 stub，只返回假数据 `col1/col2/col3`——企业版裁剪掉的是「数据读取层」本体。
- `features` 字段已按 HuggingFace datasets 格式存储列类型信息，可被直接消费。
- 前端已依赖 `echarts ^5.4.2`（package.json）。

## 2. 目标

对 `file_type` 为 csv/jsonl 的数据集：
1. 修复 `preview` API：返回真实数据前 N 行（保持现有 `rows/row/truncated_cells` 响应结构）。
2. 新增 `explore` API：逐列统计分析，一次调用返回全部统计结果。
3. 前端数据集详情页提供「一键探索」入口，渲染统计卡片与图表。

## 3. 非目标

- 图片/音频/视频/parquet 数据集的探索（v1 仅 csv/jsonl）。
- 数据修改、异步统计任务、全量数据扫描（采样上限兜底）。

## 4. 架构设计

### 4.1 数据读取层（新增共享 util）

`myapp/utils/dataset_reader.py`：

```python
SAMPLE_ROWS = 10000  # 采样上限

def resolve_dataset_path(dataset) -> str
    # dataset.path 缺省拼接 /data/k8s/kubeflow/global/dataset/{name}/{version}/

def load_dataframe(path, segment=None, rows=SAMPLE_ROWS) -> pd.DataFrame
    # 按 .csv/.jsonl 后缀分发：pd.read_csv / pd.read_json(lines=True)
    # jsonl 大文件用 chunksize 累积到 rows 行即停
    # 未知后缀 / 文件不存在 → raise DatasetReadError(msg)
```

### 4.2 explore API

`view_dataset.py` 内 `Dataset_ModelView_Api` 新增：

```
GET/POST /dataset_modelview/api/explore/<dataset_name>/<dataset_version>/<dataset_segment>
```

响应（沿用平台 `{status, message, result}` 约定）：

```json
{
  "status": 0,
  "result": {
    "row_count": 10000,
    "sampled_rows": 10000,
    "truncated": false,
    "columns": [
      {
        "name": "age", "dtype": "numeric", "null_rate": 0.02,
        "unique_count": 57, "min": 18, "max": 65,
        "quantiles": {"p25": 30, "p50": 36, "p75": 44},
        "histogram": {"bins": [18,23,28], "counts": [120, 340]}
      },
      {
        "name": "city", "dtype": "categorical", "null_rate": 0.0,
        "unique_count": 23, "top_values": [{"value": "杭州", "count": 900}]
      }
    ]
  }
}
```

- dtype 判定：数值（int/float）、日期时间、布尔、其余归入 categorical。
- categorical：`top_values` 取 Top-20；数值：固定 20 桶直方图。
- 权限：走 `MyappModelRestApi` 既有机制与 `Dataset_Filter` 过滤器（与 list/show 同源，不新开权限面）。

### 4.3 preview 修复

`preview` 改为经 `load_dataframe(rows=50)` 返回真实前 50 行，响应结构与现 stub 完全一致，前端零改动。

### 4.4 前端

数据集详情页（`frontend` 中 dataset 详情组件）：
- `file_type ∈ {csv, jsonl}` 时显示「一键探索」按钮。
- 点击调 explore，渲染：行数/列数/采样说明卡片 + 每列统计卡（数值列配 echarts 直方图，categorical 配 Top-N 条形图）。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| path 不存在 / 后缀不支持 | `status:1` + 中文 message（`数据集文件不存在` / `暂不支持该格式探索`） |
| 空文件 / 全空列 | 返回空统计（row_count=0 / null_rate=1），不报错 |
| 坏行（jsonl 解析失败） | 跳过并计入 `bad_rows` 字段返回 |
| 超大文件 | 采样到 SAMPLE_ROWS 即停；`row_count` 等于采样内实际行数，`truncated: true` 明示未全量扫描 |

## 6. 测试方案（TDD）

- 单测 `tests/test_dataset_reader.py`：tmp_path 造 csv/jsonl——数值/文本/混合列、空文件、坏行、超采样截断、格式不支持。
- 单测 explore 统计函数（纯函数 `profile_dataframe(df)` 独立于 Flask）：null 率、分桶、Top-N 正确性。
- API 测试用 FAB test client 走 `/dataset_modelview/api/explore/...`（mock dataset 记录与本地临时文件）。
- 全部跨平台（tmp_path + 相对路径），不依赖 NFS。

## 7. 风险

- 数据集 `path` 存储格式存在历史差异（相对/绝对）——`resolve_dataset_path` 做两种回退并在文档说明约定。
- pandas 已是平台依赖（sqllab base_impl 已用），无新增依赖。
