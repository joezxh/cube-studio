# LabelStudio 桥接层：task 转换/幂等去重/导出解析（纯函数 + REST 客户端）
# 注意：本模块禁止 import 任何 myapp.* 模块，保持可独立测试
import requests

VALID_TASK_TYPES = ('text_classification', 'image_classification')


def rows_to_ls_tasks(df, task_type, text_col='', image_col='', dataset_name=''):
    if task_type not in VALID_TASK_TYPES:
        raise ValueError('不支持的任务类型: %s' % task_type)
    value_col = text_col if task_type == 'text_classification' else image_col
    tasks = []
    for row_idx, record in enumerate(df.to_dict(orient='records')):
        value = record.get(value_col, '')
        tasks.append({
            'data': {
                task_type == 'text_classification' and 'text' or 'image': str(value if value is not None else ''),
                'meta': {'dataset': dataset_name, 'row_idx': row_idx},
            }
        })
    return tasks


def dedupe_tasks(tasks):
    seen, result = set(), []
    for task in tasks:
        meta = task.get('data', {}).get('meta', {})
        key = (meta.get('dataset'), meta.get('row_idx'))
        if key in seen:
            continue
        seen.add(key)
        result.append(task)
    return result


def _first_label(annotation):
    for item in annotation.get('result', []):
        choices = (item.get('value') or {}).get('choices') or []
        if choices:
            return str(choices[0])
    return None


def ls_export_to_records(export_json):
    records = []
    for task in export_json or []:
        data = dict(task.get('data') or {})
        meta = data.pop('meta', {})
        label = ''
        for annotation in task.get('annotations') or []:
            first = _first_label(annotation)
            if first is not None:
                label = first
                break  # 多标注取首个
        records.append({**data, 'label': label, 'meta': meta})
    return records
