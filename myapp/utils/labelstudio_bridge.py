# LabelStudio 桥接层：task 转换/幂等去重/导出解析（纯函数 + REST 客户端）
# 注意：本模块禁止 import 任何 myapp.* 模块，保持可独立测试
import requests
from urllib.parse import urlencode

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


class LsApiError(Exception):
    """LS REST 调用失败，message 直接面向用户展示（含 LS 响应摘要）"""


def ls_headers(ls_token):
    return {'Authorization': 'Token %s' % ls_token}


def _require_token(ls_token):
    if not ls_token:
        raise LsApiError('LS token 缺失：请传入 ls_token 或配置 LABELSTUDIO_TOKEN')


def _ls_error(resp, action):
    return LsApiError('LS %s 失败(%s): %s' % (action, resp.status_code, str(resp.text)[:200]))


def create_or_get_project(ls_url, ls_token, name, label_config):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.get(base + '/api/projects/?' + urlencode({'name': name}),
                        headers=ls_headers(ls_token), timeout=30)
    if resp.status_code >= 400:
        raise _ls_error(resp, '查询项目')
    results = resp.json().get('results') or []
    if results:
        return results[0]['id']  # 已存在同名项目，复用
    resp = requests.post(base + '/api/projects/', json={'name': name, 'label_config': label_config},
                         headers=ls_headers(ls_token), timeout=30)
    if resp.status_code >= 400:
        raise _ls_error(resp, '创建项目')
    return resp.json()['id']


def push_tasks(ls_url, ls_token, project_id, tasks):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.post(base + '/api/projects/%s/import' % project_id,
                         json=dedupe_tasks(tasks),
                         headers=ls_headers(ls_token), timeout=120)
    if resp.status_code >= 400:
        raise _ls_error(resp, '导入任务')
    return resp.json()


def fetch_export(ls_url, ls_token, project_id):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.get(base + '/api/projects/%s/export?exportType=JSON' % project_id,
                        headers=ls_headers(ls_token), timeout=300)
    if resp.status_code >= 400:
        raise _ls_error(resp, '导出标注')
    return resp.json()
