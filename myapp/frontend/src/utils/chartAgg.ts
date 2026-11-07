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
      // sum：整组无非数值有效值时视为无效（与 avg 语义一致，被 valid 过滤）
      value = g.numCount > 0 ? g.sum : NaN;
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
