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
