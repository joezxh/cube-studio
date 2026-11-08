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
    # 真正未知的后缀仍报错；parquet 已由 §3.4 lerobot 支持接管，不再是拒绝样本
    p = tmp_path / "data.xyz"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(DatasetReadError, match="暂不支持该格式探索"):
        load_dataframe(str(p))


def test_load_parquet_sample(tmp_path, monkeypatch):
    # §3.4 lerobot data/*.parquet 可被表格读取器消费（读取引擎 pyarrow，测试环境
    # 未安装故 monkeypatch pd.read_parquet，仅验证分支派发/采样/truncated 语义）
    import myapp.utils.dataset_reader as reader
    p = tmp_path / "file-000.parquet"
    p.write_bytes(b"PAR1")
    df = pd.DataFrame({"observation.state": [[0.1, 0.2]] * 3})
    monkeypatch.setattr(reader.pd, "read_parquet", lambda path: df)
    out, bad, truncated = load_dataframe(str(p), rows=10)
    assert list(out.columns) == ["observation.state"]
    assert len(out) == 3
    assert bad == 0 and truncated is False


def test_load_parquet_truncation(tmp_path, monkeypatch):
    import myapp.utils.dataset_reader as reader
    p = tmp_path / "chunk-000.parquet"
    p.write_bytes(b"PAR1")
    monkeypatch.setattr(reader.pd, "read_parquet",
                        lambda path: pd.DataFrame({"i": range(20)}))
    out, _bad, truncated = load_dataframe(str(p), rows=5)
    assert len(out) == 5
    assert truncated is True


def test_load_parquet_missing_engine_maps_error(tmp_path, monkeypatch):
    # 引擎缺失/读取失败须映射为面向用户的 DatasetReadError，不裸抛 ImportError
    import myapp.utils.dataset_reader as reader
    p = tmp_path / "c.parquet"
    p.write_bytes(b"PAR1")

    def boom(path):
        raise ImportError("Unable to find a usable engine")

    monkeypatch.setattr(reader.pd, "read_parquet", boom)
    with pytest.raises(DatasetReadError, match="parquet"):
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


def test_resolve_path_lerobot_dir_to_parquet(tmp_path):
    # §3.4 探索入口对 lerobot 目录指向 data/ 下首个 parquet 分片（chunk 子目录）
    root = tmp_path / "ds"
    chunk = root / "data" / "chunk-000"
    chunk.mkdir(parents=True)
    (chunk / "file-000.parquet").write_bytes(b"PAR1")
    (chunk / "file-001.parquet").write_bytes(b"PAR1")
    dataset = SimpleNamespace(name="ds", version="v1", path=str(root))
    assert resolve_dataset_path(dataset) == str(chunk / "file-000.parquet")


def test_resolve_path_prefers_data_csv_over_parquet(tmp_path):
    # 既有 csv 数据集零回归：目录同时有 data.csv 与 data/*.parquet 时仍走 data.csv
    root = tmp_path / "ds"
    (root / "data" / "chunk-000").mkdir(parents=True)
    (root / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"PAR1")
    (root / "data.csv").write_text("a\n1\n", encoding="utf-8")
    dataset = SimpleNamespace(name="ds", version="v1", path=str(root))
    assert resolve_dataset_path(dataset) == str(root / "data.csv")


def test_resolve_path_missing_raises():
    dataset = SimpleNamespace(name="ghost", version="v9", path="")
    with pytest.raises(DatasetReadError, match="数据集文件不存在"):
        resolve_dataset_path(dataset)


def test_sample_rows_constant():
    assert SAMPLE_ROWS == 10000
