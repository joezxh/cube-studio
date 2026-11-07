# Sqllab 查询结果可视化分析（S3）设计文档

> 日期：2026-11-07 ｜ 来源：docs/企业版功能.md L42「数据管理-数据计算：…[支持数据分析建模]」，经确认按「查询结果可视化分析」落地
> 状态：待评审

## 1. 背景与现状

- 开源版 Sqllab 已具备多引擎查询（mysql/presto/clickhouse/postgres/impala/hive，`view_sqllab.py`），结果落 CSV（`/data/k8s/kubeflow/global/sqllab/result/{qid}.csv`），前端页面（路由映射 `MODEL_URLS["sqllab"]="/frontend/data/datasearch/data_search"`）以表格渲染并可下载。
- 前端已依赖 `echarts ^5.4.2`（package.json），pipeline 可视化已在用。
- **缺口**：查询结果只有表格形态，无图表分析能力。
- 依据用户决定：**不做达梦/人大金仓引擎接入**。

## 2. 目标

在 Sqllab 结果页新增「图表分析」面板：
- 对当前已加载的结果集，用户选择 X 轴列 + Y 轴列 + 聚合方式（计数/求和/平均），渲染柱状图/饼图/折线图。
- 纯前端实现，**不新增后端 API**（结果数据已在浏览器内存中）。

## 3. 非目标

- 后端聚合查询、SQL 改写。
- 查询编辑器、引擎接入改造。
- 图表保存/分享（可作后续增强）。

## 4. 架构设计

### 4.1 聚合逻辑（可单测的纯函数）

新建 `frontend/src/utils/chartAgg.ts`：

```typescript
export type AggType = 'count' | 'sum' | 'avg';

// rows: 结果集二维数组（首行为表头，与后端 get_result 返回结构一致）
// 返回 echarts 可直接消费的 {categories, values}
export function aggregate(rows: string[][], xCol: string, yCol: string | null, agg: AggType, limit = 50): {categories: string[]; values: number[]}
```

规则：
- `agg=count` 或 `yCol=null`：按 X 列分组计数。
- `sum/avg`：Y 列无法数值化的行跳过；X 组内聚合。
- 类别数超过 `limit` 时取计数前 limit 组、其余合并为「其他」。

### 4.2 前端 UI

- datasearch 结果区新增「图表分析」tab（与现有表格视图并列）。
- 控件：图型（柱/饼/线）、X 列下拉、Y 列下拉（可选）、聚合方式。
- 渲染：echarts 实例复用项目现有引入方式（按需 import echarts 模块，避免全量打包）。
- 定位方式：实施时以 `MODEL_URLS["sqllab"]` 指向的 `/frontend/data/datasearch/data_search` 为入口，在 `frontend/src` 中检索 datasearch 页面组件（plan 阶段锁定具体文件）。

### 4.3 数据流

查询完成 → 前端已有 `rows`（表头+数据）→ 图表 tab 直接消费内存数据 → 用户切换聚合参数时前端重新 `aggregate`，零请求。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 结果为空 | 面板显示空态提示，图表区不渲染 |
| Y 列全部无法数值化 | 提示「所选指标列不含数值」，不渲染 |
| X 列唯一值过多 | 走 limit 合并「其他」，tooltip 说明 |

## 6. 测试方案（TDD）

- `chartAgg.ts` 用前端测试框架（若 frontend 无 jest 基建，则将该文件设计为无 UI 依赖纯模块，先补最小 jest 配置仅跑 utils，避免全站测试改造）：count/sum/avg、非数值行跳过、limit 合并、空输入。
- 手工验收清单：各图型渲染、切换聚合、空结果、大数据集（>1 万行）响应时间。
- 后端零改动，无后端测试。

## 7. 风险

- frontend 缺测试基建 → 已在方案中限定「仅 utils 补最小 jest」，不牵动全站。
- echarts 按需引入需遵循项目现有 import 惯例，避免 bundle 膨胀（实施时检查现有 echarts 引入方式并保持一致）。
