# 数据集表格一键探索（S4）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 csv/jsonl 表格数据集提供真实数据预览（修复 stub）与一键逐列统计分析能力。

**Architecture:** 新建零 Flask 依赖的读取层 `myapp/utils/dataset_reader.py` 与统计层 `myapp/utils/dataset_profile.py`（均为纯函数、独立可测），`view_dataset.py` 的 API 与 FAB action 仅做薄封装；数据集页面为 FAB 后端模板体系（React 侧无数据集详情页），探索结果页用 Jinja 模板 + 纯 CSS 条形图渲染（项目 static 无 echarts 库文件，不引 CDN）。

**Tech Stack:** Python 3.9 / pandas 2.1.2（已有依赖）/ Flask-AppBuilder @expose_api + @action / Jinja2 / pytest

**Spec:** `docs/superpowers/specs/2026-11-07-dataset-explore-design.md`

## Global Constraints

- 采样上限 `SAMPLE_ROWS = 10000`；`row_count` 等于采样内实际行数，`truncated: true` 明示未全量扫描（spec §5）。
- 错误消息固定中文文案：`数据集文件不存在` / `暂不支持该格式探索`（spec §5）。
- jsonl 坏行跳过并计入 `bad_rows`；csv 不计 bad_rows（pandas `on_bad_lines='skip'`）（spec §5）。
- v1 仅支持 `.csv` / `.jsonl` 后缀，其余一律拒绝（spec §3）。
- 新增 util 文件（dataset_reader.py / dataset_profile.py）**禁止 import 任何 `myapp.*` 模块**——项目 boot 需要 `MYSQL_SERVICE` 等外部环境，测试环境无法创建 Flask app。
- 路径规则沿用代码库先例：`/mnt/` 前缀替换为 `/data/k8s/kubeflow/pipeline/workspace/`（`model_dataset.py path_html` 同逻辑）；目录则拼接 `data.csv`；缺省目录 `/data/k8s/kubeflow/global/dataset/{name}/{version or 'latest'}/`（`post_delete` 同逻辑）。
- 测试全部跨平台：`tmp_path` + UTF-8 显式编码，不依赖 NFS/`/data` 真实目录。
- 测试命令在仓库根目录执行：`python -m pytest tests/ -v`（仓库根当前无 pytest.ini，顶层 tests/ 为本次新建）。
- 每个 Task 结束 commit；提交信息用 `feat:` / `test:` 前缀。

## 测试边界说明（与 spec §6 的偏差）

spec 写「API 测试用 FAB test client」。实际勘察结论：创建 FAB test client 需 boot 整个 `myapp` app，而 `myapp/config.py` 的 `SQLALCHEMY_DATABASE_URI = os.getenv('MYSQL_SERVICE','')` 在本地为空串会直接抛异常，且 app 初始化耦合 DB/redis。因此本计划将 **TDD 完整覆盖两个纯函数模块**（读取层 + 统计层，即全部业务逻辑），API handler 保持薄（无分支逻辑超出参数解析与异常转换），API 的集成验证由 Task 5 的手工验收清单承担。执行者不得为了「可测 API」而 boot Flask app。

---

### Task 1: 数据读取层 `dataset_reader.py`

**Files:**
- Create: `myapp/utils/dataset_reader.py`
- Test: `tests/test_dataset_reader.py`

**Interfaces:**
- Consumes: 无（零项目依赖，仅 pandas/os/json）。
- Produces（Task 3、S1 计划依赖，签名必须逐字一致）:
  - `SAMPLE_ROWS = 10000`
  - `class DatasetReadError(Exception)`
  - `def resolve_dataset_path(dataset) -> str`（`dataset` 为鸭子类型对象，读取 `.path/.name/.version` 属性；路径不可用时 raise `DatasetReadError('数据集文件不存在')`）
  - `def load_dataframe(path: str, segment=None, rows: int = SAMPLE_ROWS) -> tuple[pd.DataFrame, int, bool]`（返回 `(df, bad_rows, truncated)`；`df` 最多 `rows` 行；失败 raise `DatasetReadError`）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_dataset_reader.py`：

```python
import os
from types import SimpleNamespace

import pandas as pd
import pytest

from myapp.utils.dataset_reader import (
    SAMPLE_ROWS,
    DatasetReadError,
    load_dataframe,
    resolve_dataset_path,
)


def test_load_csv_basic(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,x\n2,y\n3,\n", encoding="utf-8")
    df, bad_rows, truncated = load_dataframe(str(p))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 3
    assert bad_rows == 0
    assert truncated is False


def test_load_csv_truncation(tmp_path):
    lines = ["a"] + [str(i) for i in range(20)]
    p = tmp_path / "data.csv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    df, _bad, truncated = load_dataframe(str(p), rows=10)
    assert len(df) == 10
    assert truncated is True


def test_load_csv_empty_file(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("", encoding="utf-8")
    df, bad_rows, truncated = load_dataframe(str(p))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert bad_rows == 0 and truncated is False


def test_load_jsonl_basic_and_bad_rows(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text(
        '{"text": "a"}\nnot-json\n{"text": "b"}\n\n{"text": "c"}\n',
        encoding="utf-8",
    )
    df, bad_rows, truncated = load_dataframe(str(p))
    assert len(df) == 3
    assert bad_rows == 1
    assert truncated is False


def test_load_jsonl_truncation(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text(
        "".join(f'{{"i": {i}}}\n' for i in range(20)), encoding="utf-8"
    )
    df, _bad, truncated = load_dataframe(str(p), rows=5)
    assert len(df) == 5
    assert truncated is True


def test_unsupported_suffix(tmp_path):
    p = tmp_path / "data.parquet"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(DatasetReadError, match="暂不支持该格式探索"):
        load_dataframe(str(p))


def test_file_not_exists(tmp_path):
    with pytest.raises(DatasetReadError, match="数据集文件不存在"):
        load_dataframe(str(tmp_path / "nope.csv"))


def test_resolve_path_from_dataset_path(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a\n1\n", encoding="utf-8")
    dataset = SimpleNamespace(name="ds", version="v1", path=str(p))
    assert resolve_dataset_path(dataset) == str(p)


def test_resolve_path_dir_to_data_csv(tmp_path):
    data_dir = tmp_path / "ws"
    data_dir.mkdir()
    (data_dir / "data.csv").write_text("a\n1\n", encoding="utf-8")
    # 目录 -> 拼 data.csv（path_html 同构逻辑；/mnt/ 前缀替换由代码评审覆盖，见 Step 3 注意）
    dataset = SimpleNamespace(name="ds", version="v1", path=str(data_dir))
    assert resolve_dataset_path(dataset) == str(data_dir / "data.csv")


def test_resolve_path_default_root(tmp_path, monkeypatch):
    import myapp.utils.dataset_reader as reader
    root = tmp_path / "root"
    ds_dir = root / "ds" / "v1"
    ds_dir.mkdir(parents=True)
    (ds_dir / "data.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setattr(reader, "DATASET_ROOT", str(root))
    dataset = SimpleNamespace(name="ds", version="v1", path="")
    assert resolve_dataset_path(dataset) == str(ds_dir / "data.csv")


def test_resolve_path_version_latest_fallback(tmp_path, monkeypatch):
    import myapp.utils.dataset_reader as reader
    root = tmp_path / "root"
    ds_dir = root / "ds" / "latest"
    ds_dir.mkdir(parents=True)
    (ds_dir / "data.csv").write_text("a\n1\n", encoding="utf-8")
    monkeypatch.setattr(reader, "DATASET_ROOT", str(root))
    dataset = SimpleNamespace(name="ds", version="", path="")
    assert resolve_dataset_path(dataset) == str(ds_dir / "data.csv")


def test_resolve_path_missing_raises():
    dataset = SimpleNamespace(name="ghost", version="v9", path="")
    with pytest.raises(DatasetReadError, match="数据集文件不存在"):
        resolve_dataset_path(dataset)


def test_sample_rows_constant():
    assert SAMPLE_ROWS == 10000
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_dataset_reader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'myapp.utils.dataset_reader'`（若 `myapp/utils/__init__.py` 不存在导致包导入失败，先创建空的 `myapp/utils/__init__.py`——已存在则跳过）

- [ ] **Step 3: 最小实现**

创建 `myapp/utils/dataset_reader.py`：

```python
# 数据集表格文件读取层：csv/jsonl -> DataFrame（采样上限内）
# 注意：本模块禁止 import 任何 myapp.* 模块，保持可独立测试
import json
import os

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
    raise DatasetReadError('暂不支持该格式探索')
```

注意：`test_resolve_path_mnt_prefix_and_dir` 只验证「目录 → data.csv」分支；`/mnt/` 前缀替换与 `path_html`（model_dataset.py L113-114）同构，由代码评审覆盖，不为它构造假 `/mnt` 挂载点。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_dataset_reader.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/dataset_reader.py tests/test_dataset_reader.py
git commit -m "feat: 数据集读取层 dataset_reader（csv/jsonl 采样读取，S4）"
```

---

### Task 2: 统计层 `dataset_profile.py`

**Files:**
- Create: `myapp/utils/dataset_profile.py`
- Test: `tests/test_dataset_profile.py`

**Interfaces:**
- Consumes: 无（纯 pandas/numpy）。
- Produces（Task 3 依赖）:
  - `def profile_dataframe(df: pd.DataFrame) -> list[dict]`——逐列返回：
    - 公共：`{'name': str, 'dtype': 'numeric'|'datetime'|'boolean'|'categorical', 'null_rate': float(0~1, 4位小数)}`
    - numeric 增：`unique_count:int, min, max, quantiles:{p25,p50,p75}, histogram:{bins:[float], counts:[int]}`（固定 20 桶，NaN 丢弃）
    - datetime 增：`unique_count:int, min:str, max:str`
    - boolean 增：`unique_count:int, counts:{'True':n,'False':n}`
    - categorical 增：`unique_count:int, top_values:[{'value':str,'count':int}]`（Top-20）
    - 全部值为 Python 原生类型（numpy 标量经 `_clean` 转换），可直接 jsonify。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_dataset_profile.py`：

```python
import pandas as pd

from myapp.utils.dataset_profile import profile_dataframe


def test_numeric_column_profile():
    df = pd.DataFrame({"age": [18, 22, 25, 30, 65, None]})
    cols = profile_dataframe(df)
    col = cols[0]
    assert col["name"] == "age"
    assert col["dtype"] == "numeric"
    assert abs(col["null_rate"] - 1 / 6) < 0.001
    assert col["min"] == 18 and col["max"] == 65
    assert set(col["quantiles"].keys()) == {"p25", "p50", "p75"}
    hist = col["histogram"]
    assert len(hist["counts"]) == 20
    assert sum(hist["counts"]) == 5  # None 被丢弃
    assert all(isinstance(v, (int, float)) for v in hist["bins"])


def test_categorical_top_values():
    df = pd.DataFrame({"city": ["杭州"] * 3 + ["上海"] * 2 + [None]})
    col = profile_dataframe(df)[0]
    assert col["dtype"] == "categorical"
    assert col["top_values"][0] == {"value": "杭州", "count": 3}
    assert col["unique_count"] == 2


def test_boolean_and_datetime():
    df = pd.DataFrame({
        "flag": [True, False, True],
        "dt": pd.to_datetime(["2024-01-01", "2024-06-01", None]),
    })
    cols = profile_dataframe(df)
    assert cols[0]["dtype"] == "boolean"
    assert cols[0]["counts"] == {"True": 2, "False": 1}
    assert cols[1]["dtype"] == "datetime"
    assert cols[1]["min"] == "2024-01-01 00:00:00"
    assert cols[1]["max"] == "2024-06-01 00:00:00"


def test_top_values_limit_20():
    values = [f"v{i}" for i in range(30)]
    df = pd.DataFrame({"x": values + ["v0"]})  # v0 出现 2 次居首
    col = profile_dataframe(df)[0]
    assert len(col["top_values"]) == 20


def test_empty_dataframe():
    cols = profile_dataframe(pd.DataFrame())
    assert cols == []


def test_all_null_column():
    df = pd.DataFrame({"x": [None, None]})
    col = profile_dataframe(df)[0]
    assert col["null_rate"] == 1.0
    assert col["unique_count"] == 0


def test_values_are_native_types():
    df = pd.DataFrame({"n": [1, 2, 3]})
    col = profile_dataframe(df)[0]
    assert isinstance(col["min"], int) and not hasattr(col["min"], "dtype")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_dataset_profile.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'myapp.utils.dataset_profile'`

- [ ] **Step 3: 最小实现**

创建 `myapp/utils/dataset_profile.py`：

```python
# 数据集逐列统计分析（纯函数，禁止 import 任何 myapp.* 模块）
import numpy as np
import pandas as pd

TOP_N = 20      # categorical top_values 数量
HIST_BINS = 20  # numeric 直方图桶数


def _clean(value):
    """numpy 标量 -> Python 原生类型；NaN -> None，保证可直接 jsonify"""
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _column_profile(series) -> dict:
    null_rate = round(float(series.isna().mean()), 4) if len(series) else 1.0
    profile = {'name': str(series.name), 'dtype': 'categorical', 'null_rate': null_rate}
    if len(series) == 0:
        profile.update({'unique_count': 0, 'top_values': []})
        return profile
    if pd.api.types.is_bool_dtype(series):
        profile['dtype'] = 'boolean'
        counts = series.value_counts(dropna=True)
        profile.update({
            'unique_count': int(series.nunique()),
            'counts': {str(k): int(v) for k, v in counts.items()},
        })
        return profile
    if pd.api.types.is_numeric_dtype(series):
        profile['dtype'] = 'numeric'
        clean = series.dropna()
        if len(clean) == 0:
            profile.update({'unique_count': 0, 'min': None, 'max': None,
                            'quantiles': {}, 'histogram': {'bins': [], 'counts': []}})
            return profile
        counts, bins = np.histogram(clean, bins=HIST_BINS)
        profile.update({
            'unique_count': int(clean.nunique()),
            'min': _clean(clean.min()), 'max': _clean(clean.max()),
            'quantiles': {q: _clean(clean.quantile(pos))
                          for q, pos in (('p25', .25), ('p50', .5), ('p75', .75))},
            'histogram': {'bins': [_clean(b) for b in bins],
                          'counts': [int(c) for c in counts]},
        })
        return profile
    if pd.api.types.is_datetime64_any_dtype(series):
        profile['dtype'] = 'datetime'
        clean = series.dropna()
        profile.update({
            'unique_count': int(clean.nunique()),
            'min': str(clean.min()) if len(clean) else None,
            'max': str(clean.max()) if len(clean) else None,
        })
        return profile
    # 其余一律 categorical
    text = series.dropna().astype(str)
    top = text.value_counts().head(TOP_N)
    profile.update({
        'unique_count': int(text.nunique()),
        'top_values': [{'value': v, 'count': int(c)} for v, c in top.items()],
    })
    return profile


def profile_dataframe(df) -> list:
    return [_column_profile(df[col]) for col in df.columns]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_dataset_profile.py -v`
Expected: 7 passed

- [ ] **Step 5: 全量回归 + Commit**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（含 Task 1 的 12 个）

```bash
git add myapp/utils/dataset_profile.py tests/test_dataset_profile.py
git commit -m "feat: 数据集逐列统计 profile_dataframe（数值/分类型/布尔/时间，S4）"
```

---

### Task 3: explore API + preview 修复

**Files:**
- Modify: `myapp/views/view_dataset.py`（`Dataset_ModelView_Api` 类，L455 附近；`preview` 方法 L395-420）

**Interfaces:**
- Consumes: Task 1 的 `resolve_dataset_path/load_dataframe/DatasetReadError`，Task 2 的 `profile_dataframe`（签名见 Task 1/2 Produces）。
- Produces:
  - `GET/POST /dataset_modelview/api/explore/<dataset_name>/<dataset_version>[/<dataset_segment>]`，成功响应 `{'status':0,'message':'success','result':{'row_count':int,'sampled_rows':int,'truncated':bool,'bad_rows':int,'columns':[...]}}`，失败 `{'status':1,'result':{},'message':<中文文案>}`
  - `preview` 响应结构不变：`{'status':0,'message':'success','result':{'rows':[{'row_idx':int,'row':dict,'truncated_cells':[]}]}}`

- [ ] **Step 1: 在 view_dataset.py 顶部补充 import**

在 `from myapp.utils import core` 之后加入：

```python
from myapp.utils.dataset_reader import DatasetReadError, load_dataframe, resolve_dataset_path
from myapp.utils.dataset_profile import profile_dataframe
```

- [ ] **Step 2: 修复 preview（替换 L398-420 的 stub 函数体）**

将现有 `preview` 方法整体替换为（保持方法签名 `def preview(self)` 与三个 `@expose_api` 装饰器不动，参数从 `request.view_args` 取——与现 stub 兼容）：

```python
    def preview(self):
        _args = request.get_json(silent=True) or {}
        _args.update(request.args)
        _args.update(json.loads(request.args.get('form_data', '{}')))
        view_args = request.view_args or {}
        dataset_name = view_args.get('dataset_name', '')
        dataset_version = view_args.get('dataset_version', '')
        dataset_segment = view_args.get('dataset_segment', '')
        query = db.session.query(Dataset).filter_by(name=dataset_name)
        if dataset_version:
            query = query.filter_by(version=dataset_version)
        dataset = query.order_by(Dataset.id.desc()).first()
        if not dataset:
            return jsonify({'status': 1, 'result': {}, 'message': '数据集不存在'})
        try:
            path = resolve_dataset_path(dataset)
            df, _bad, _truncated = load_dataframe(path, segment=dataset_segment, rows=50)
        except DatasetReadError as e:
            return jsonify({'status': 1, 'result': {}, 'message': str(e)})
        rows = []
        for idx, record in enumerate(df.to_dict(orient='records')):
            row = {}
            for key, value in record.items():
                if hasattr(value, 'item'):       # numpy 标量 -> Python 原生
                    value = value.item()
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    value = ''
                row[str(key)] = value
            rows.append({'row_idx': idx, 'row': row, 'truncated_cells': []})
        return jsonify({'status': 0, 'message': 'success', 'result': {'rows': rows}})
```

并在文件顶部 import 区补 `import math`（该文件当前未导入）。

- [ ] **Step 3: 新增 explore API（加在 `Dataset_ModelView_Api` 类内，`route_base` 定义之后）**

```python
    @expose_api(description="探索指定数据集", url="/explore/<dataset_name>/<dataset_version>", methods=["GET", "POST"])
    @expose_api(description="探索指定数据集指定分片", url="/explore/<dataset_name>/<dataset_version>/<dataset_segment>", methods=["GET", "POST"])
    def explore(self, dataset_name, dataset_version, dataset_segment=''):
        query = db.session.query(Dataset).filter_by(name=dataset_name)
        if dataset_version and dataset_version != 'latest':
            query = query.filter_by(version=dataset_version)
        dataset = query.order_by(Dataset.id.desc()).first()
        if not dataset:
            return jsonify({'status': 1, 'result': {}, 'message': '数据集不存在'})
        try:
            path = resolve_dataset_path(dataset)
            df, bad_rows, truncated = load_dataframe(path, segment=dataset_segment)
        except DatasetReadError as e:
            return jsonify({'status': 1, 'result': {}, 'message': str(e)})
        result = {
            'row_count': int(len(df)),
            'sampled_rows': int(len(df)),
            'truncated': truncated,
            'bad_rows': bad_rows,
            'columns': profile_dataframe(df),
        }
        return jsonify({'status': 0, 'message': 'success', 'result': result})
```

- [ ] **Step 4: 跑全量测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（view_dataset 不在本计划单测覆盖内，见「测试边界说明」）

- [ ] **Step 5: Commit**

```bash
git add myapp/views/view_dataset.py
git commit -m "feat: 数据集 explore 统计 API + preview 真实数据修复（S4）"
```

---

### Task 4: 一键探索入口（FAB action + 模板）

**Files:**
- Modify: `myapp/views/view_dataset.py`（`Dataset_ModelView_Api` 类内新增 action 与页面）
- Create: `myapp/templates/myapp/dataset_explore.html`

**Interfaces:**
- Consumes: Task 3 的 explore 渲染逻辑同源（直接在服务端调 profile，不经过 explore API）。
- Produces: 数据集列表页 row action「一键探索」→ `GET /dataset_modelview/api/explore_html/<dataset_id>` 渲染统计页。

- [ ] **Step 1: 新增 action 与 explore_html（加在 Task 3 的 `explore` 方法之后）**

```python
    @action("explore_dataset", "一键探索", "对表格数据集执行一键探索统计?", "fa-bar-chart", single=True, multiple=False)
    def explore_dataset_action(self, dataset):
        return redirect('/dataset_modelview/api/explore_html/%s' % dataset.id)

    @expose_api(description="数据集探索页面", url="/explore_html/<dataset_id>", methods=["GET"])
    def explore_html(self, dataset_id):
        dataset = db.session.query(Dataset).filter_by(id=dataset_id).first()
        if not dataset:
            flash('数据集不存在', 'warning')
            return redirect('/dataset_modelview/api/')
        row_count, bad_rows, truncated, columns, error = 0, 0, False, [], ''
        try:
            path = resolve_dataset_path(dataset)
            df, bad_rows, truncated = load_dataframe(path)
            columns = profile_dataframe(df)
            row_count = int(len(df))
        except DatasetReadError as e:
            error = str(e)
        return self.render_template('myapp/dataset_explore.html', dataset=dataset,
                                    row_count=row_count, bad_rows=bad_rows,
                                    truncated=truncated, columns=columns, error=error)
```

确认文件顶部已具备：`from flask import flash, redirect`（若现有 import 行未含，补充到已有的 `from flask import ...` 行中）。

- [ ] **Step 2: 创建模板**

创建 `myapp/templates/myapp/dataset_explore.html`：

```html
{% extends 'appbuilder/baselayout.html' %}
{% block content %}
<div style="padding:16px">
  <h3>数据集探索：{{ dataset.label or dataset.name }}（{{ dataset.version or 'latest' }}）</h3>
  {% if error %}
  <div class="alert alert-warning">{{ error }}</div>
  {% else %}
  <p>
    采样行数 <b>{{ row_count }}</b>
    {% if truncated %}（已达采样上限，统计基于采样非全量）{% endif %}
    {% if bad_rows %}，跳过坏行 {{ bad_rows }}{% endif %}
  </p>
  <div>
    {% for col in columns %}
    <div class="panel panel-default" style="display:inline-block;vertical-align:top;width:360px;margin:8px">
      <div class="panel-heading">
        <b>{{ col.name }}</b>
        <span class="label label-default">{{ col.dtype }}</span>
        <span style="float:right">空值率 {{ col.null_rate }}</span>
      </div>
      <div class="panel-body">
        {% if col.dtype == 'numeric' %}
          <p>最小 {{ col.min }} ／ 最大 {{ col.max }} ／ 唯一值 {{ col.unique_count }}</p>
          <p>分位数：p25={{ col.quantiles.p25 }} p50={{ col.quantiles.p50 }} p75={{ col.quantiles.p75 }}</p>
          {% set max_count = col.histogram.counts | max %}
          {% for count in col.histogram.counts %}
            {% if max_count > 0 %}
            <div style="height:10px;margin:2px 0;background:#337ab7;width:{{ (100 * count / max_count) | round(1) }}%"></div>
            {% endif %}
          {% endfor %}
          <p style="color:#999">直方图（{{ col.histogram.counts | length }} 桶）</p>
        {% elif col.dtype == 'boolean' %}
          <p>True: {{ col.counts.get('True', 0) }} ／ False: {{ col.counts.get('False', 0) }}</p>
        {% elif col.dtype == 'datetime' %}
          <p>{{ col.min }} ~ {{ col.max }}（唯一值 {{ col.unique_count }}）</p>
        {% else %}
          {% set max_count = col.top_values[0].count if col.top_values else 0 %}
          {% for item in col.top_values %}
          <div style="margin:2px 0">
            <span style="display:inline-block;width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle">{{ item.value }}</span>
            <span style="display:inline-block;height:12px;background:#5cb85c;vertical-align:middle;width:{{ (90 * item.count / max_count) | round(1) }}%"></span>
            <span>{{ item.count }}</span>
          </div>
          {% endfor %}
          {% if not col.top_values %}<p style="color:#999">无数据</p>{% endif %}
        {% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: 全量测试回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add myapp/views/view_dataset.py myapp/templates/myapp/dataset_explore.html
git commit -m "feat: 数据集一键探索入口与统计页模板（S4）"
```

---

### Task 5: 手工验收清单（部署环境执行，不阻塞合并）

**Files:**
- 无代码改动；验收结果记录到 PR/合并说明。

- [ ] **Step 1: 准备验证数据集**——在数据集页面创建/复用一个 csv 数据集（path 指向可访问文件），确认列表页出现「一键探索」action。
- [ ] **Step 2: 点击一键探索**——确认统计页渲染：行数、各列卡片、数值列直方图条形、categorical Top-N 条形。
- [ ] **Step 3: 验证 preview**——调用 `GET /dataset_modelview/api/preview/<name>/<version>`，确认返回真实前 50 行且结构与旧 stub 一致（`rows/row/truncated_cells`）。
- [ ] **Step 4: 异常分支**——对一个 path 指向不存在文件的数据集执行探索，确认页面/接口返回「数据集文件不存在」；对一个 parquet 数据集确认「暂不支持该格式探索」。
- [ ] **Step 5: 大文件采样**——对一个 >10000 行的 csv 确认 `truncated: true` 且 `sampled_rows == 10000`。
