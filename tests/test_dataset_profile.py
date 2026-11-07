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
