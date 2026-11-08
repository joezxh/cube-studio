"""lerobot 算子共享库：manifest 血缘写入（spec §2.2，唯一允许跨算子引用的模块）。"""
import hashlib
import json
import pathlib
import time


def sha256_file(path):
    p = pathlib.Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(body):
    """self_digest 的 canonical 序列化：剔除 self_digest/created_at，sort_keys、无 indent。"""
    return json.dumps({k: v for k, v in body.items()
                       if k not in ("self_digest", "created_at")},
                      ensure_ascii=False, sort_keys=True)


def write_manifest(out_dir, *, op, args, parents, files, stats=None, extra=None):
    """files 须为 out_dir 相对路径且不得包含 manifest.json（清单自动跳过并声明于文档）。"""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    body = {
        "op": op,
        "args": args,
        "parents": list(parents or []),
        "files": [{"path": f, "digest": sha256_file(out / f)}
                  for f in (files or [])
                  if pathlib.PurePath(str(f)).name != "manifest.json"],
        "stats": stats or {},
        "extra": extra or {},
    }
    body["self_digest"] = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    body["created_at"] = int(time.time())
    (out / "manifest.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return body
