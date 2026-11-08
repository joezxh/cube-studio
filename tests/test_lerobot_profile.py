import lerobot_profile as pr

INFO = {
    "codebase_version": "v3", "total_episodes": 20, "total_frames": 4000, "fps": 20,
    "features": {
        "action": {"dtype": "float32", "shape": [2]},
        "observation.state": {"dtype": "float32", "shape": [4]},
        "observation.images.image": {"dtype": "video", "shape": [480, 640, 3]},
    },
}


def test_build_profile_core():
    p = pr.build_profile(INFO, {"push a": 12, "push b": 8})
    assert p["format_version"] == "v3"
    assert p["total_episodes"] == 20 and p["total_frames"] == 4000
    assert p["fps"] == 20.0
    assert p["video_keys"] == ["observation.images.image"]
    assert p["action_dim"] == 2 and p["state_dim"] == 4
    assert p["task_distribution"] == {"push a": 12, "push b": 8}
    assert p["video_total_sec"] == 200.0


def test_no_tasks_and_zero_fps_safe():
    p = pr.build_profile({"codebase_version": "v2.1", "total_frames": 10, "fps": 0,
                          "total_episodes": 1, "features": {}}, None)
    assert p["task_distribution"] is None
    assert p["video_total_sec"] is None
    assert p["action_dim"] is None
