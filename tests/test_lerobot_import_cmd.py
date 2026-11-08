import pytest

import lerobot_import_cmd as ic


def test_validate_info_ok_versions():
    assert ic.validate_info({"codebase_version": "v3"}) == "v3"
    assert ic.validate_info({"codebase_version": "v2.1"}) == "v2.1"


def test_validate_info_reject_unknown():
    with pytest.raises(ValueError, match="codebase_version"):
        ic.validate_info({"codebase_version": "v1"})
    with pytest.raises(ValueError):
        ic.validate_info({})


def test_parse_dataset_ref():
    assert ic.parse_dataset_ref("pusht_demo:v1") == ("pusht_demo", "v1")
    for bad in ("noColon", ":v1", "n:", ""):
        with pytest.raises(ValueError):
            ic.parse_dataset_ref(bad)


def test_resolve_paths_kinds():
    p = ic.resolve_paths("hub_repo_id", "lerobot/pusht", "n", "v1")
    assert p == {"kind": "hub", "src": "lerobot/pusht",
                 "dst": "/data/k8s/kubeflow/global/dataset/n/v1"}
    assert ic.resolve_paths("local_path", "/mnt/x", "n", "v1")["kind"] == "copy"
    assert ic.resolve_paths("local_path", "/mnt/x", "n", "v1", link_mode=True)["kind"] == "link"
    with pytest.raises(ValueError):
        ic.resolve_paths("ftp", "x", "n", "v1")


def test_resolve_paths_rejects_unsafe_target():
    # I-7：target_name/version 拒路径穿越/分隔符（与 train_cmd 口径对称）
    for bad_name in ("../evil", "a/b", "a\\b", ".", "..", "n;rm", ""):
        with pytest.raises(ValueError, match="target_name"):
            ic.resolve_paths("local_path", "/mnt/x", bad_name, "v1")
    for bad_ver in ("../v", "v/1", "..", ""):
        with pytest.raises(ValueError, match="target_version"):
            ic.resolve_paths("local_path", "/mnt/x", "n", bad_ver)
    # 安全形态仍正常
    assert ic.resolve_paths("local_path", "/mnt/x", "pusht_demo", "v2.1")["dst"].endswith(
        "/dataset/pusht_demo/v2.1")
