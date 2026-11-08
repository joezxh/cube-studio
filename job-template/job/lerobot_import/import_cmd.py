"""lerobot-import 纯函数命令层（spec §3，单测对象；禁止 import myapp.*）。"""
import re

SUPPORTED_FORMATS = ("v2.1", "v3")
BASE_DIR = "/data/k8s/kubeflow/global/dataset"
# 与 train_cmd 对称：dst 在跨用户全局数据集中心落盘，target_name/version 必须为安全单段
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")


def _check_safe_part(value, what):
    if not _SAFE_PART.match(str(value)) or str(value) == "." or ".." in str(value):
        raise ValueError("unsafe %s: %r" % (what, value))


def validate_info(info):
    v = str((info or {}).get("codebase_version", ""))
    if v not in SUPPORTED_FORMATS:
        raise ValueError(
            "unsupported codebase_version: %r, expect one of %s" % (v, SUPPORTED_FORMATS))
    return v


def parse_dataset_ref(ref):
    parts = str(ref).split(":")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError("dataset_ref must be name:version, got %r" % (ref,))
    return parts[0].strip(), parts[1].strip()


def resolve_paths(source_type, source, target_name, target_version,
                  base_dir=BASE_DIR, link_mode=False):
    if source_type not in ("local_path", "hub_repo_id"):
        raise ValueError("source_type must be local_path/hub_repo_id, got %r" % (source_type,))
    _check_safe_part(target_name, "target_name")
    _check_safe_part(target_version, "target_version")
    dst = "%s/%s/%s" % (str(base_dir).rstrip("/"), target_name, target_version)
    if source_type == "hub_repo_id":
        return {"kind": "hub", "src": str(source), "dst": dst}
    return {"kind": "link" if link_mode else "copy", "src": str(source), "dst": dst}
