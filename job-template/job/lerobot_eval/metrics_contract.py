"""lerobot-eval stdout → 平台自有指标契约 v1（spec §5.2；上游漂移只改解析器）。"""
import re

_RATE = re.compile(r"success[_ ]?rate[:=\s]+([0-9]+(?:\.[0-9]+)?)\s*(%?)", re.I)
_CNT = re.compile(r"\((\d+)\s*/\s*(\d+)\)", re.I)
_RET = re.compile(r"(?:mean|avg)[_ ]?(?:return|reward)[:=\s]+([-+0-9.eE]+)", re.I)
_LEN = re.compile(r"(?:mean|avg)[_ ]?ep(?:isode)[_ ]?len(?:gth)?[:=\s]+([-+0-9.eE]+)", re.I)


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_eval_summary(text):
    text = text or ""
    m = _RATE.search(text)
    rate = None
    if m:
        v, pct = _f(m.group(1)), m.group(2)
        rate = v / 100.0 if (v is not None and (pct or v > 1)) else v
    # 计数只在 rate 匹配所在行内搜索，避免误取进度条等其他括号计数
    if m:
        line_end = text.find("\n", m.end())
        scope = text[m.end():line_end if line_end != -1 else len(text)]
    else:
        scope = text
    cnt = _CNT.search(scope)
    succ = int(cnt.group(1)) if cnt else None
    ev = int(cnt.group(2)) if cnt else None
    if succ is not None and rate is None and ev:
        rate = succ / ev
    m = _RET.search(text)
    ret = _f(m.group(1)) if m else None
    m = _LEN.search(text)
    elen = _f(m.group(1)) if m else None
    return {"success_rate": rate, "mean_return": ret, "mean_episode_len": elen,
            "n_evaluated": ev, "n_success": succ}


def build_eval_metrics(summary, *, env, n_episodes, seed, checkpoint,
                       train_manifest_digest=None, videos=None, raw_log="eval.log"):
    return {
        "contract_version": "1",
        "source": {"type": "lerobot-eval", "env": env,
                   "n_episodes": n_episodes, "seed": seed},
        "policy_ref": {"checkpoint_path": str(checkpoint),
                       "train_manifest_digest": train_manifest_digest},
        "metrics": {k: summary.get(k) for k in
                    ("success_rate", "mean_return", "mean_episode_len",
                     "n_evaluated", "n_success")},
        "artifacts": {"videos": list(videos or []), "raw_log": raw_log},
    }
