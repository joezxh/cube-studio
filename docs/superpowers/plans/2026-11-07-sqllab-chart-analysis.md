# Sqllab 查询结果可视化分析（S3）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Sqllab（datasearch）结果查看弹窗中新增「图表分析」tab，对内存中的结果集做分组聚合并渲染柱状/饼/折线图。

**Architecture:** 聚合逻辑实现为无 UI 依赖的纯函数模块 `frontend/src/utils/chartAgg.ts`（jest 单测），渲染复用项目已有 `components/EchartCore/EchartCore.tsx` 封装（全量 echarts import，`option: echarts.EChartsOption`），入口接在 `pages/DataSearch/TaskList.tsx` 的结果 Modal（`handleResultData` 处）。纯前端、零后端改动。

**Tech Stack:** React 17 / antd 4.21 / echarts 5.4.2（均已有依赖）/ jest（frontend 已有完整 jest 基建）

**Spec:** `docs/superpowers/specs/2026-11-07-sqllab-chart-analysis-design.md`

## Global Constraints

- 纯前端实现，**不新增/不修改任何后端 API**（spec §2）。
- 聚合规则（spec §4.1）：`agg=count` 或 `yCol=null` → 按 X 列分组计数；`sum/avg` → Y 列无法数值化的行跳过；类别数超过 `limit`（默认 50）时按聚合值降序取前 limit 组，其余合并为「其他」。
- 不做达梦/人大金仓引擎接入（用户决定，spec §1）。
- echarts 引用一律通过 `components/EchartCore/EchartCore.tsx`，不得在页面直接 `import echarts`（保持现有引入惯例）。
- 测试命令在 `myapp/frontend/` 目录执行：`CI=true npm test -- --watchAll=false --testPathPattern=chartAgg`（scripts/test.js 为 CRA runner，需 CI=true 关闭 watch）。
- jest 配置已存在（package.json `jest` 段：roots `<rootDir>/src`、testMatch `*.test.{ts,tsx}`、jsdom），不需要新增测试配置。
- 每个 Task 结束 commit，提交信息 `feat:` / `test:` 前缀。

---

### Task 1: 聚合纯函数 `chartAgg.ts`（TDD）

**Files:**
- Create: `myapp/frontend/src/utils/chartAgg.ts`
- Test: `myapp/frontend/src/utils/chartAgg.test.ts`

**Interfaces:**
- Consumes: 无（纯函数，与后端 get_result 返回结构对齐：`rows` 首行为表头的二维数组）。
- Produces（Task 2 依赖，签名逐字一致）:

```typescript
export type AggType = 'count' | 'sum' | 'avg';
export function aggregate(
  rows: (string | number)[][],
  xCol: string,
  yCol: string | null,
  agg: AggType,
  limit = 50
): { categories: string[]; values: number[] }
```

- [ ] **Step 1: 写失败测试**

创建 `myapp/frontend/src/utils/chartAgg.test.ts`：

```typescript
import { aggregate } from './chartAgg';

const rows = [
  ['city', 'amount'],
  ['杭州', '10'],
  ['杭州', '20'],
  ['上海', '5'],
  ['上海', 'abc'], // 非数值行
  ['深圳', '1'],
];

describe('chartAgg.aggregate', () => {
  it('count 聚合按 X 列分组计数', () => {
    const r = aggregate(rows, 'city', null, 'count');
    expect(r.categories).toEqual(['杭州', '上海', '深圳']);
    expect(r.values).toEqual([2, 2, 1]);
  });

  it('yCol=null 等价于 count', () => {
    expect(aggregate(rows, 'city', null, 'sum')).toEqual(
      aggregate(rows, 'city', null, 'count')
    );
  });

  it('sum 跳过无法数值化的行', () => {
    const r = aggregate(rows, 'city', 'amount', 'sum');
    expect(r.values).toEqual([30, 5, 1]); // 上海的 'abc' 被跳过
  });

  it('avg 组内平均', () => {
    const r = aggregate(rows, 'city', 'amount', 'avg');
    expect(r.values).toEqual([15, 5, 1]);
  });

  it('超过 limit 取聚合值前 limit 组其余合并为其他', () => {
    const big = [['k']];
    for (let i = 0; i < 60; i++) {
      big.push([`g${i}`]);
    }
    const r = aggregate(big as string[][], 'k', null, 'count', 50);
    expect(r.categories.length).toBe(51); // 50 组 + 其他
    expect(r.values.filter((v) => v === 1).length).toBe(50);
    expect(r.categories[50]).toBe('其他');
  });

  it('空结果返回空数组', () => {
    expect(aggregate([['a']], 'a', null, 'count')).toEqual({
      categories: [],
      values: [],
    });
  });

  it('xCol 不存在返回空', () => {
    expect(aggregate(rows, 'nope', null, 'count')).toEqual({
      categories: [],
      values: [],
    });
  });

  it('sum 时全部行无法数值化返回空', () => {
    const bad = [['c', 'v'], ['a', 'x'], ['b', 'y']];
    const r = aggregate(bad, 'c', 'v', 'sum');
    expect(r).toEqual({ categories: [], values: [] });
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run（在 `myapp/frontend/` 下）: `CI=true npm test -- --watchAll=false --testPathPattern=chartAgg`
Expected: FAIL，`Cannot find module './chartAgg'`

- [ ] **Step 3: 最小实现**

创建 `myapp/frontend/src/utils/chartAgg.ts`：

```typescript
// Sqllab 结果集前端聚合（纯函数，与后端 get_result 结构对齐：rows 首行为表头）
export type AggType = 'count' | 'sum' | 'avg';

interface AggResult {
  categories: string[];
  values: number[];
}

export function aggregate(
  rows: (string | number)[][],
  xCol: string,
  yCol: string | null,
  agg: AggType,
  limit = 50
): AggResult {
  const result: AggResult = { categories: [], values: [] };
  if (!rows || rows.length < 2) {
    return result;
  }
  const header = rows[0] || [];
  const xIdx = header.indexOf(xCol);
  if (xIdx < 0) {
    return result;
  }
  const yIdx = yCol ? header.indexOf(yCol) : -1;
  if (yCol && yIdx < 0) {
    return result;
  }

  // 分组：保持首次出现顺序
  const groups: { key: string; count: number; sum: number; numCount: number }[] = [];
  const groupMap = new Map<string, { key: string; count: number; sum: number; numCount: number }>();
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i] || [];
    const key = String(row[xIdx] ?? '');
    let g = groupMap.get(key);
    if (!g) {
      g = { key, count: 0, sum: 0, numCount: 0 };
      groupMap.set(key, g);
      groups.push(g);
    }
    g.count += 1;
    if (yCol && agg !== 'count') {
      const num = parseFloat(String(row[yIdx]));
      if (!isNaN(num)) {
        g.sum += num;
        g.numCount += 1;
      }
    }
  }

  const hasY = !!yCol && agg !== 'count';
  const pairs = groups.map((g) => {
    let value: number;
    if (!hasY) {
      value = g.count;
    } else if (agg === 'avg') {
      value = g.numCount > 0 ? g.sum / g.numCount : NaN;
    } else {
      value = g.sum;
    }
    return { key: g.key, value };
  });

  // sum/avg 时丢弃整组无数值的组；count 场景 numCount 无意义
  const valid = hasY ? pairs.filter((p) => !isNaN(p.value)) : pairs;
  if (valid.length === 0) {
    return result;
  }

  // 按聚合值降序，超 limit 合并「其他」
  valid.sort((a, b) => b.value - a.value);
  if (valid.length <= limit) {
    for (const p of valid) {
      result.categories.push(p.key);
      result.values.push(p.value);
    }
    return result;
  }
  let otherSum = 0;
  for (let i = 0; i < valid.length; i++) {
    if (i < limit) {
      result.categories.push(valid[i].key);
      result.values.push(valid[i].value);
    } else {
      otherSum += valid[i].value;
    }
  }
  result.categories.push('其他');
  result.values.push(otherSum);
  return result;
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `CI=true npm test -- --watchAll=false --testPathPattern=chartAgg`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/frontend/src/utils/chartAgg.ts myapp/frontend/src/utils/chartAgg.test.ts
git commit -m "feat: Sqllab 结果前端聚合纯函数 chartAgg（S3）"
```

---

### Task 2: 图表面板组件 `ChartPanel.tsx`

**Files:**
- Create: `myapp/frontend/src/pages/DataSearch/ChartPanel.tsx`

**Interfaces:**
- Consumes:
  - Task 1：`aggregate(rows, xCol, yCol, agg, limit)`、`AggType`。
  - 已有组件：`components/EchartCore/EchartCore.tsx` 默认导出（props：`option: echarts.EChartsOption, isNoData?: boolean`）。
- Produces: `export default function ChartPanel(props: { result: (string | number)[][] })`——Task 3 在结果 Modal 中以 `<ChartPanel result={result} />` 使用。

- [ ] **Step 1: 创建组件**

创建 `myapp/frontend/src/pages/DataSearch/ChartPanel.tsx`：

```tsx
import React, { useMemo, useState } from 'react';
import { Radio, Select } from 'antd';
import EchartCore from '../../components/EchartCore/EchartCore';
import { aggregate, AggType } from '../../utils/chartAgg';

interface IProps {
  // 与后端 get_result 结构一致：首行为表头
  result: (string | number)[][];
}

const CHART_TYPES = [
  { label: '柱状图', value: 'bar' },
  { label: '饼图', value: 'pie' },
  { label: '折线图', value: 'line' },
];

const AGG_TYPES = [
  { label: '计数', value: 'count' },
  { label: '求和', value: 'sum' },
  { label: '平均', value: 'avg' },
];

export default function ChartPanel(props: IProps) {
  const { result } = props;
  const header: string[] = (result && result[0]) || [];
  const [chartType, setChartType] = useState<string>('bar');
  const [xCol, setXCol] = useState<string>(header[0] || '');
  const [yCol, setYCol] = useState<string | null>(null);
  const [agg, setAgg] = useState<AggType>('count');

  const option = useMemo(() => {
    const { categories, values } = aggregate(result || [], xCol, yCol, agg);
    if (chartType === 'pie') {
      return {
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie',
          radius: '60%',
          data: categories.map((name, i) => ({ name, value: values[i] })),
        }],
      };
    }
    return {
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value' },
      series: [{ type: chartType as 'bar' | 'line', data: values }],
    };
  }, [result, xCol, yCol, agg, chartType]);

  const isEmpty = !result || result.length < 2;

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Select
          style={{ width: 160, marginRight: 8 }}
          placeholder="X 轴列"
          value={xCol || undefined}
          onChange={(v: string) => setXCol(v)}
          options={header.map((h) => ({ label: h, value: h }))}
        />
        <Select
          style={{ width: 160, marginRight: 8 }}
          placeholder="指标列（可选）"
          value={yCol}
          allowClear
          onChange={(v: string | null) => setYCol(v ?? null)}
          options={header.map((h) => ({ label: h, value: h }))}
        />
        <Select<AggType>
          style={{ width: 110, marginRight: 8 }}
          value={agg}
          onChange={(v: AggType) => setAgg(v)}
          options={AGG_TYPES}
        />
        <Radio.Group
          optionType="button"
          value={chartType}
          onChange={(e) => setChartType(e.target.value)}
          options={CHART_TYPES}
        />
      </div>
      <EchartCore option={option} isNoData={isEmpty} />
      {isEmpty && <div style={{ color: '#999' }}>查询结果为空，无法生成图表</div>}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查确认编译通过**

Run（在 `myapp/frontend/` 下）: `npx tsc --noEmit -p tsconfig.json` 
Expected: 无本文件相关错误（项目其他文件存在的历史类型错误可忽略，只要不新增 `ChartPanel.tsx` 的报错；若全仓 tsc 噪音过大，改用 `CI=true npm run buildSelf` 观察 webpack 编译无本文件错误）

- [ ] **Step 3: Commit**

```bash
git add myapp/frontend/src/pages/DataSearch/ChartPanel.tsx
git commit -m "feat: Sqllab 结果图表分析面板 ChartPanel（柱/饼/线 + 聚合控件，S3）"
```

---

### Task 3: 接入结果 Modal（表格/图表双 tab）

**Files:**
- Modify: `myapp/frontend/src/pages/DataSearch/TaskList.tsx`（结果查看 Modal，L348-365 附近 `handleResultData(result)` 之后渲染 `TableBox` 的位置）

**Interfaces:**
- Consumes: Task 2 的 `ChartPanel`（`result` props）。
- Produces: 用户可见行为——结果查看 Modal 顶部出现 Tabs：「数据表格」（原有 TableBox）/「图表分析」（ChartPanel）。

- [ ] **Step 1: 修改 Modal 内容为 Tabs**

在 `TaskList.tsx` 顶部 import 区加入：

```tsx
import { Tabs } from 'antd';
import ChartPanel from './ChartPanel';
```

找到结果查看 Modal（`Modal.info({ title: '结果查看', ... })`）中 `content: (<div>...</div>)` 里现有的 `<TableBox ... />` 节点，将其与图表包进 Tabs（保持 TableBox 的现有 props 原样平移，不改动其属性）：

```tsx
content: (
  <div>
    <Tabs defaultActiveKey="table" items={[
      {
        key: 'table',
        label: '数据表格',
        children: (
          <TableBox
            size={"small"}
            loading={false}
            /* ……此处保留现有 TableBox 的全部 props，逐字平移…… */
          />
        ),
      },
      {
        key: 'chart',
        label: '图表分析',
        children: <ChartPanel result={result} />,
      },
    ]} />
  </div>
)
```

注意：该 Modal 处于 `handleResultData` 被调用的回调作用域内，`result` 变量已在作用域（L344 `const result = res.data.result`）；若该处 `result` 类型与 `handleResultData` 入参一致（`(string | number)[][]`）则直接传，若存在 null 情况传 `result || []`。antd 4.21 的 Tabs 支持 `items` 属性（4.21+ 已引入）；若运行时发现该版本不支持 `items`，则改用 `<Tabs><Tabs.TabPane tab="数据表格" key="table">...</Tabs.TabPane><Tabs.TabPane tab="图表分析" key="chart">...</Tabs.TabPane></Tabs>` 写法（项目 DataSearch.tsx L445 现有 TabPane 用法先例）。

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit -p tsconfig.json`（忽略历史噪音，确认无本文件新增错误）
Expected: 无 `TaskList.tsx` 新增报错

- [ ] **Step 3: 前端单测回归**

Run: `CI=true npm test -- --watchAll=false --testPathPattern=chartAgg`
Expected: 8 passed

- [ ] **Step 4: Commit**

```bash
git add myapp/frontend/src/pages/DataSearch/TaskList.tsx
git commit -m "feat: Sqllab 结果弹窗接入图表分析 tab（S3）"
```

---

### Task 4: 手工验收清单（本地起前端联调，不阻塞合并）

**Files:**
- 无代码改动。

- [ ] **Step 1:** `myapp/frontend/` 下 `npm start` 起本地前端，登录后进入「数据探索」页面。
- [ ] **Step 2:** 运行一条返回类别列+数值列的 SQL（如 `select city, amount from t limit 1000`），查询成功后打开结果查看 Modal，切换「图表分析」tab。
- [ ] **Step 3:** 验证三种图型（柱/饼/线）渲染正确；切换 X 列、Y 列、count/sum/avg 图表即时刷新且不发请求。
- [ ] **Step 4:** 空结果查询 → 图表区显示空态提示；全非数值 Y 列 + sum → 图表区为空不报错。
- [ ] **Step 5:** 大结果集（>1 万行）切换聚合参数无明显卡顿（echarts 渲染 <1s 量级即可）。
