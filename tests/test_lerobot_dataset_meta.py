import json
import types

from myapp.utils.lerobot_dataset_meta import read_cube_dataset_meta, apply_lerobot_meta


def test_read_ok(tmp_path):
    (tmp_path / ".cube_dataset_meta").write_text(
        json.dumps({"format": "lerobot", "version": "v3", "profile": {}}),
        encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path)["version"] == "v3"


def test_read_absent_bad_format_broken(tmp_path):
    assert read_cube_dataset_meta(tmp_path) is None
    (tmp_path / ".cube_dataset_meta").write_text('{"format":"other"}', encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path) is None
    (tmp_path / ".cube_dataset_meta").write_text("{broken", encoding="utf-8")
    assert read_cube_dataset_meta(tmp_path) is None


def test_apply_mutates_obj(tmp_path):
    (tmp_path / ".cube_dataset_meta").write_text(json.dumps(
        {"format": "lerobot", "version": "v3",
         "profile": {"total_episodes": 20, "total_frames": 4000,
                     "action_dim": 2, "fps": 20}}), encoding="utf-8")
    obj = types.SimpleNamespace(file_type="parquet", describe="demo")
    assert apply_lerobot_meta(obj, tmp_path) is True
    assert obj.file_type == "lerobot"
    assert obj.describe.startswith("[lerobot v3 ep=20 frames=4000]")
    assert apply_lerobot_meta(obj, tmp_path) is True  # 幂等：不重复加标签
    assert obj.describe.count("[lerobot") == 1


def test_apply_no_meta_untouched(tmp_path):
    obj = types.SimpleNamespace(file_type="parquet", describe="d")
    assert apply_lerobot_meta(obj, tmp_path) is False
    assert obj.file_type == "parquet" and obj.describe == "d"
