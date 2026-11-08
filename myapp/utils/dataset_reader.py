# 数据集表格文件读取层：csv/jsonl -> DataFrame（采样上限内）
# 注意：本模块禁止 import 任何 myapp.* 模块，保持可独立测试
import json
import os
from glob import iglob

import pandas as pd

SAMPLE_ROWS = 10000

# 数据集缺省存储根目录（与 view_dataset.post_delete 的 remote_dir 约定一致）
DATASET_ROOT = '/data/k8s/kubeflow/global/dataset'
MNT_PREFIX = '/mnt/'
MNT_REPLACE = '/data/k8s/kubeflow/pipeline/workspace/'


class DatasetReadError(Exception):
    """数据集读取失败（文件不存在/格式不支持等），message 直接面向用户展示"""


def _first_path_line(dataset_path) -> str:
    """path 字段为多行文本，取首个非空行（与 path_html 的解析先例一致）"""
    for line in (dataset_path or '').split('\n'):
        line = line.strip()
        if line:
            return line
    return ''


def _first_lerobot_parquet(dataset_dir) -> str:
    """lerobot 数据集目录 -> data/ 下首个 parquet 分片（含 chunk-* 子目录）。

    命中条件：存在 data/ 子目录且有 *.parquet；否则返回 ''（非 lerobot 布局）。"""
    data_dir = os.path.join(dataset_dir, 'data')
    if not os.path.isdir(data_dir):
        return ''
    for f in sorted(iglob(os.path.join(data_dir, '**', '*.parquet'),
                          recursive=True)):
        return f
    return ''


def resolve_dataset_path(dataset) -> str:
    path = _first_path_line(getattr(dataset, 'path', ''))
    if path:
        if path.startswith(MNT_PREFIX):
            path = MNT_REPLACE + path[len(MNT_PREFIX):]
        if os.path.isdir(path):
            data_csv = os.path.join(path, 'data.csv')
            if os.path.exists(data_csv):
                path = data_csv
            else:
                # §3.4 lerobot 布局：目录无 data.csv 时探索入口指向 data/*.parquet
                parquet = _first_lerobot_parquet(path)
                if parquet:
                    path = parquet
    else:
        # 缺省存储中心路径：dataset/{name}/{version}/data.csv
        version = getattr(dataset, 'version', '') or 'latest'
        name = getattr(dataset, 'name', '')
        path = os.path.join(DATASET_ROOT, str(name), str(version), 'data.csv')
    if not os.path.exists(path):
        raise DatasetReadError('数据集文件不存在')
    return path


def load_dataframe(path, segment=None, rows=SAMPLE_ROWS):
    """读取数据集文件为 DataFrame。

    返回 (df, bad_rows, truncated)：
    - df: 最多 rows 行的采样
    - bad_rows: 解析失败被跳过的行数（仅 jsonl 统计，csv 由 pandas skip）
    - truncated: 采样达到 rows 上限且文件还有更多行
    """
    if not os.path.exists(path):
        raise DatasetReadError('数据集文件不存在')
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        try:
            # 多读一行用于判定 truncated
            df = pd.read_csv(path, nrows=rows + 1, on_bad_lines='skip')
        except pd.errors.EmptyDataError:
            return pd.DataFrame(), 0, False
        truncated = len(df) > rows
        return df.head(rows), 0, truncated
    if ext == '.jsonl':
        records, bad_rows, truncated = [], 0, False
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if len(records) >= rows:
                    truncated = True
                    break
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    bad_rows += 1
        df = pd.json_normalize(records) if records else pd.DataFrame()
        return df, bad_rows, truncated
    if ext == '.parquet':
        # §3.4 lerobot data/*.parquet 直接消费（引擎 pyarrow，随镜像提供）
        try:
            df = pd.read_parquet(path)
        except Exception as e:  # ImportError(缺引擎)/OSError/解析失败均面客展示
            raise DatasetReadError('parquet 读取失败: %s' % e)
        truncated = len(df) > rows
        return df.head(rows), 0, truncated
    raise DatasetReadError('暂不支持该格式探索')
