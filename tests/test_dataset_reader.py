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
