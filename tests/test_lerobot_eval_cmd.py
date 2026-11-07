import lerobot_eval_cmd as ec


def test_build_eval_cmd_pairs():
    cmd = ec.build_eval_cmd(checkpoint="/ckpt/p", env_type="pusht",
                            n_episodes=5, output_dir="/e")
    assert cmd[0] == "lerobot-eval"
    assert cmd[1] == "--policy.path" and cmd[2] == "/ckpt/p"
    assert cmd[cmd.index("--env.type") + 1] == "pusht"
    assert cmd[cmd.index("--eval.n_episodes") + 1] == "5"
    assert cmd[cmd.index("--seed") + 1] == "100000"
    assert cmd[cmd.index("--eval.video.n_episodes") + 1] == "3"
    assert all(str(c).startswith("--") for c in cmd[1::2])


def test_zero_video_skips_flag():
    cmd = ec.build_eval_cmd(checkpoint="/c", env_type="aloha",
                            video_n_episodes=0, output_dir="/e")
    assert "--eval.video.n_episodes" not in cmd


def test_dims_mismatch_detected():
    cfg = {"shape_metadata": {"a": {"type": "action", "shape": [14], "names": None}}}
    ok, reason = ec.check_action_dims(cfg, "pusht")
    assert not ok and "14" in reason and "2" in reason


def test_dims_match_or_skip():
    cfg = {"features": {"action": {"dtype": "float32", "shape": [2]}}}
    assert ec.check_action_dims(cfg, "pusht")[0]
    assert ec.check_action_dims({}, "pusht")[0]      # 维度不可得 → 跳过
    assert ec.check_action_dims(
        {"shape_metadata": {"a": {"shape": [99]}}}, "custom_env")[0]  # 未预设 env → 跳过
