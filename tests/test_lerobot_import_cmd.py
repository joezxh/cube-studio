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
