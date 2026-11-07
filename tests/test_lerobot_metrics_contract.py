import lerobot_metrics_contract as mc

TEXT = ("Success rate: 82.00% (41/50)\n"
        "mean return: 14.6\nmean episode length: 96.3\n")


def test_parse_summary():
    s = mc.parse_eval_summary(TEXT)
    assert abs(s["success_rate"] - 0.82) < 1e-9
    assert s["n_success"] == 41 and s["n_evaluated"] == 50
    assert s["mean_return"] == 14.6 and s["mean_episode_len"] == 96.3


def test_parse_empty_safe():
    s = mc.parse_eval_summary("nothing here")
    assert s == {"success_rate": None, "mean_return": None,
                 "mean_episode_len": None, "n_evaluated": None, "n_success": None}


def test_contract_shape():
    c = mc.build_eval_metrics(mc.parse_eval_summary(TEXT), env="pusht",
                              n_episodes=50, seed=100000, checkpoint="/ck/last",
                              train_manifest_digest="abc123", videos=["v0.mp4"])
    assert c["contract_version"] == "1"
    assert c["source"] == {"type": "lerobot-eval", "env": "pusht",
                           "n_episodes": 50, "seed": 100000}
    assert c["policy_ref"]["checkpoint_path"] == "/ck/last"
    assert c["policy_ref"]["train_manifest_digest"] == "abc123"
    assert c["metrics"]["success_rate"] == 0.82
    assert c["artifacts"]["videos"] == ["v0.mp4"] and c["artifacts"]["raw_log"] == "eval.log"


def test_gap_recorded():
    s = mc.parse_eval_summary("Success rate: 80.00% (40/50)\n")
    s["n_evaluated"] = 45  # 上游崩溃缺口
    c = mc.build_eval_metrics(s, env="pusht", n_episodes=50, seed=1, checkpoint="/ck")
    assert c["metrics"]["n_evaluated"] == 45
    assert c["policy_ref"]["train_manifest_digest"] is None
