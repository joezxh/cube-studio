import json

import lerobot_manifest_util as mu


def test_write_manifest_fields_and_digest(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    body = mu.write_manifest(tmp_path, op="lerobot-train",
                             args={"steps": 10}, parents=[{"path": "p", "digest": "d"}],
                             files=["a.txt"], stats={"k": 1})
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["op"] == "lerobot-train"
    assert m["parents"] == [{"path": "p", "digest": "d"}]
    assert m["files"][0]["path"] == "a.txt"
    assert m["files"][0]["digest"] == mu.sha256_file(tmp_path / "a.txt")
    assert m["self_digest"] == body["self_digest"]
    assert len(m["self_digest"]) == 64


def test_digest_stable_across_writes(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    b1 = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["a.txt"])
    b2 = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["a.txt"])
    assert b1["self_digest"] == b2["self_digest"]  # created_at 不得进入摘要


def test_missing_file_digest_none(tmp_path):
    body = mu.write_manifest(tmp_path, op="x", args={}, parents=[], files=["nope.txt"])
    assert body["files"][0]["digest"] is None


def test_digest_recomputable_from_disk(tmp_path):
    """契约：从落盘 manifest.json 重算 self_digest 必须等于存储值（血缘可复核）。"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    mu.write_manifest(tmp_path, op="x", args={"a": 1}, parents=[], files=["a.txt"],
                      stats={"s": 2}, extra={"e": 3})
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    import hashlib
    recomputed = hashlib.sha256(mu._canonical(m).encode("utf-8")).hexdigest()
    assert recomputed == m["self_digest"]


def test_manifest_json_skipped_from_files(tmp_path):
    """契约：files 包含 manifest.json 时自动跳过，保证两次写摘要一致。"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    b1 = mu.write_manifest(tmp_path, op="x", args={}, parents=[],
                           files=["a.txt", "manifest.json"])
    b2 = mu.write_manifest(tmp_path, op="x", args={}, parents=[],
                           files=["a.txt", "manifest.json"])
    assert b1["self_digest"] == b2["self_digest"]
    assert [f["path"] for f in b1["files"]] == ["a.txt"]
