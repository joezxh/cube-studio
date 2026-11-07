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
