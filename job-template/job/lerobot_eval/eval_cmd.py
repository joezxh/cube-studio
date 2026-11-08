"""lerobot-eval 命令组装与启动前动作维度校验（spec §5.3；代替静态兼容矩阵）。"""

ENV_ACTION_DIM = {"pusht": 2, "aloha": 14}


def build_eval_cmd(*, checkpoint, output_dir, env_type, n_episodes=50,
                   batch_size=10, seed=100000, video_n_episodes=3):
    cmd = ["lerobot-eval", "--policy.path", str(checkpoint),
           "--env.type", str(env_type),
           "--eval.n_episodes", str(n_episodes),
           "--eval.batch_size", str(batch_size),
           "--seed", str(seed), "--eval.output_dir", str(output_dir)]
    if int(video_n_episodes) > 0:
        cmd += ["--eval.video.n_episodes", str(video_n_episodes)]
    return cmd


def extract_action_dim(policy_config):
    cfg = policy_config or {}
    for entry in (cfg.get("shape_metadata") or {}).values():
        shape = (entry or {}).get("shape")
        if shape:
            return int(shape[0])
    feats = cfg.get("features") or {}
    shape = (feats.get("action") or {}).get("shape")
    if shape:
        return int(shape[0])
    out_dim = (cfg.get("output_features") or {}).get("action")
    if isinstance(out_dim, (list, tuple)) and out_dim:
        return int(out_dim[0])
    return None


def check_action_dims(policy_config, env_type):
    env_dim = ENV_ACTION_DIM.get(env_type)
    if env_dim is None:
        return True, "env %r not preset, skip dim check" % env_type
    p_dim = extract_action_dim(policy_config)
    if p_dim is None:
        return True, "action shape not found, skip dim check"
    if p_dim != env_dim:
        return False, ("action dim mismatch: policy=%d env=%s=%d"
                       % (p_dim, env_type, env_dim))
    return True, "ok"
