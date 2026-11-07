"""lerobot-import 纯函数命令层（spec §3，单测对象；禁止 import myapp.*）。"""

SUPPORTED_FORMATS = ("v2.1", "v3")
BASE_DIR = "/data/k8s/kubeflow/global/dataset"


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
    dst = "%s/%s/%s" % (str(base_dir).rstrip("/"), target_name, target_version)
    if source_type == "hub_repo_id":
        return {"kind": "hub", "src": str(source), "dst": dst}
    return {"kind": "link" if link_mode else "copy", "src": str(source), "dst": dst}
