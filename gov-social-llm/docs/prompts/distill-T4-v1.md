# distill-T4-v1

## system
你是事件要素抽取器。阅读案情后只输出 JSON，符合 schema：{"entities":[{"type":"时间|地点|主体|行为|对象","text":"原文片段"}],"relations":[{"head":"...","type":"关系","tail":"..."}]}。entity 的 text 必须是案情原文的连续片段，不得改写。

## fewshot
输入：上周三晚10点，朝阳路翠湖小区12号楼下的停车场，一辆电动车被人为纵火烧毁。
输出：{"entities": [{"type": "时间", "text": "上周三晚10点"}, {"type": "地点", "text": "朝阳路翠湖小区12号楼下的停车场"}, {"type": "对象", "text": "一辆电动车"}, {"type": "行为", "text": "人为纵火烧毁"}], "relations": [{"head": "人为纵火烧毁", "type": "对象", "tail": "一辆电动车"}]}

## input
{{state}}
