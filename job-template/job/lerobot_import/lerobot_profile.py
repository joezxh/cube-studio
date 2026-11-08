"""lerobot-import 画像纯函数（spec §3.2 步骤3；仅依赖 info.json dict，无 parquet 硬依赖）。"""


def build_profile(info, task_counts=None):
    feats = (info or {}).get("features", {}) or {}

    def dim_of(name):
        shape = (feats.get(name) or {}).get("shape") or []
        return int(shape[0]) if shape else None

    video_keys = sorted(k for k, v in feats.items()
                        if str(v.get("dtype", "")) in ("video", "image"))
    frames = int(info.get("total_frames", 0))
    fps = float(info.get("fps", 0) or 0)
    return {
        "format_version": info.get("codebase_version"),
        "total_episodes": int(info.get("total_episodes", 0)),
        "total_frames": frames,
        "fps": fps,
        "video_keys": video_keys,
        "action_dim": dim_of("action"),
        "state_dim": dim_of("observation.state"),
        "task_distribution": task_counts or None,
        "video_total_sec": round(frames / fps, 2) if fps else None,
    }
