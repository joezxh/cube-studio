"""lerobot-train stdout → metrics.json 纯函数解析（spec §4.2；上游日志漂移只改这里）。"""
import re

_STEP = re.compile(r"step[:=\s]+(\d+)", re.I)
_LOSS = re.compile(r"loss[:=\s]+([-+0-9.eE]+)", re.I)
_TIME = re.compile(r"(?:elapsed|total_time|wall)[^\d]*([0-9]+(?:\.[0-9]+)?)", re.I)


def parse_train_metrics(text):
    steps = _STEP.findall(text or "")
    losses = _LOSS.findall(text or "")
    times = _TIME.findall(text or "")
    return {"steps_run": int(steps[-1]) if steps else None,
            "final_train_loss": float(losses[-1]) if losses else None,
            "wall_time_sec": float(times[-1]) if times else None}
