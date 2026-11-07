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
