"""LeRobotDataset 目录元信息识别（spec §3.3；纯标准库，禁止 import myapp.*）。"""
import json
import pathlib

META_FILENAME = ".cube_dataset_meta"


def read_cube_dataset_meta(dataset_dir):
    try:
        p = pathlib.Path(str(dataset_dir)) / META_FILENAME
        if not p.is_file():
            return None
    except (OSError, ValueError):  # 多行 path、非法字符等：零影响降级
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return meta if isinstance(meta, dict) and meta.get("format") == "lerobot" else None


def apply_lerobot_meta(obj, dataset_dir):
    meta = read_cube_dataset_meta(dataset_dir)
    if not meta:
        return False
    prof = meta.get("profile") or {}
    tag = "[lerobot %s ep=%s frames=%s]" % (
        meta.get("version", "?"), prof.get("total_episodes", "?"),
        prof.get("total_frames", "?"))
    obj.file_type = "lerobot"
    desc = getattr(obj, "describe", "") or ""
    if not desc.startswith("[lerobot"):
        obj.describe = "%s %s" % (tag, desc)
    return True
