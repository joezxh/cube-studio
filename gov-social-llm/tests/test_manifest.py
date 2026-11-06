"""gov-manifest 血缘库测试（spec §3.1）。"""
import hashlib
import json
import pathlib

import pytest
from gov_manifest import (jsonl_stats, read_manifest, seal, sha256_file,
                          verify_manifest, write_manifest)


def _mk_jsonl(p: pathlib.Path, rows=3):
    p.write_text("\n".join(json.dumps({"label": f"L{i%2}", "x": i}) for i in range(rows)), encoding="utf-8")


def test_sha256(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("abc", encoding="utf-8")
    assert sha256_file(f) == hashlib.sha256(b"abc").hexdigest()


def test_stats(tmp_path):
    f = tmp_path / "d.jsonl"
    _mk_jsonl(f, 3)
    s = jsonl_stats(f)
    assert s["rows"] == 3 and s["label_dist"] == {"L0": 2, "L1": 1}


def test_write_read_verify(tmp_path):
    d = tmp_path / "distill/T1/v1"
    d.mkdir(parents=True)
    _mk_jsonl(d / "train.jsonl")
    m = write_manifest(d, op="gov-test", args={"--x": 1}, files=["train.jsonl"],
                       stats={"rows": 3})
    assert m["sealed"] is False and read_manifest(d)["producer"]["op"] == "gov-test"
    ok, problems = verify_manifest(d)
    assert ok, problems
    (d / "train.jsonl").write_text("tampered", encoding="utf-8")
    ok, problems = verify_manifest(d)
    assert not ok and any("train.jsonl" in p for p in problems)


def test_parent_lineage_and_seal(tmp_path):
    parent = tmp_path / "seeds/T1/v1"
    parent.mkdir(parents=True)
    _mk_jsonl(parent / "s.jsonl", 2)
    write_manifest(parent, op="gov-x", args={}, files=["s.jsonl"])
    child = tmp_path / "distill/T1/v1"
    child.mkdir(parents=True)
    _mk_jsonl(child / "c.jsonl")
    pref = {"path": str(parent / "manifest.json"),
            "digest": read_manifest(parent)["self_digest"]}
    write_manifest(child, op="gov-y", args={}, files=["c.jsonl"], parents=[pref])
    ok, problems = verify_manifest(child)
    assert ok, problems
    seal(parent)
    assert read_manifest(parent)["sealed"] is True
    assert (parent / "s.jsonl").exists()  # 文件仍存在，仅只读


def test_sealed_detect_in_verify(tmp_path):
    d = tmp_path / "ds"
    d.mkdir()
    _mk_jsonl(d / "a.jsonl")
    write_manifest(d, op="o", args={}, files=["a.jsonl"])
    seal(d)
    ok, problems = verify_manifest(d)  # seal 后 self_digest 已更新，仍应通过
    assert ok, problems
