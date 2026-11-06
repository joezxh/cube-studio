"""gov-manifest 共享血缘库（spec §3.1）。

所有 gov-* 算子的产出目录经 write_manifest 落 manifest.json：
  dataset / created_at / producer{op,image,git_commit,args}
  parents[{path,digest}] / files[{path,sha256,rows,label_dist}] / stats / sealed
image 与 git_commit 取环境变量 GOV_IMAGE / GOV_GIT_COMMIT（镜像构建期注入）。
"""
import datetime
import hashlib
import json
import os
import pathlib
import stat

_MANIFEST = "manifest.json"


def sha256_file(path):
    """文件内容 SHA256（64 位小写 hex）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonl_stats(path):
    """JSONL 文件统计：行数、sha256、行内 label 字段分布（无则空）。"""
    rows, labels = 0, {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        lbl = obj.get("label") if isinstance(obj, dict) else None
        if lbl is not None:
            labels[str(lbl)] = labels.get(str(lbl), 0) + 1
    return {"rows": rows, "sha256": sha256_file(path), "label_dist": labels}


def _canon(m):
    """除 self_digest 外的规范化 JSON 字节串（签名对象）。"""
    return json.dumps({k: v for k, v in m.items() if k != "self_digest"},
                      sort_keys=True, ensure_ascii=False).encode("utf-8")


def _digest_of(m):
    return hashlib.sha256(_canon(m)).hexdigest()


def write_manifest(out_dir, *, op, args, parents=(), files=(), stats=None, extra=None):
    """写 out_dir/manifest.json 并返回 dict。files 为目录内相对路径。"""
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    m = {
        "dataset": str(out_dir).replace("\\", "/"),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "producer": {"op": op,
                     "image": os.environ.get("GOV_IMAGE", "unknown"),
                     "git_commit": os.environ.get("GOV_GIT_COMMIT", "unknown"),
                     "args": args},
        "parents": list(parents),
        "files": [{"path": f, **jsonl_stats(d / f)} for f in files],
        "stats": stats or {},
        "sealed": False,
    }
    m.update(extra or {})
    m["self_digest"] = _digest_of(m)
    (d / _MANIFEST).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


def read_manifest(dir_):
    p = pathlib.Path(dir_) / _MANIFEST
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def verify_manifest(dir_):
    """返回 (ok, problems)。校验 manifest 自签名、文件摘要、上游血缘引用。"""
    m = read_manifest(dir_)
    if m is None:
        return False, [f"{dir_}: manifest.json 缺失"]
    problems = []
    if _digest_of(m) != m.get("self_digest"):
        problems.append(f"{dir_}: manifest 自身被篡改")
    d = pathlib.Path(dir_)
    for f in m.get("files", []):
        p = d / f["path"]
        if not p.exists():
            problems.append(f"{f['path']}: 文件缺失")
        elif sha256_file(p) != f["sha256"]:
            problems.append(f"{f['path']}: 内容漂移(sha256 不一致)")
    for pr in m.get("parents", []):
        pm = read_manifest(pathlib.Path(pr["path"]).parent)
        if pm is None or pm.get("self_digest") != pr["digest"]:
            problems.append(f"parent {pr['path']}: 上游血缘断裂")
    return (not problems), problems


def seal(dir_):
    """封存：sealed=true，数据文件与 manifest 置只读，重算 self_digest。"""
    m = read_manifest(dir_)
    if m is None:
        raise FileNotFoundError(f"{dir_}: manifest.json 缺失")
    d = pathlib.Path(dir_)
    m["sealed"] = True
    for f in m.get("files", []):
        p = d / f["path"]
        if p.exists():
            p.chmod(stat.S_IREAD)
    m.pop("self_digest", None)
    m["self_digest"] = _digest_of(m)
    mp = d / _MANIFEST
    if mp.exists():
        mp.chmod(stat.S_IWRITE)
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.chmod(stat.S_IREAD)
    return m
