import pytest

import lerobot_train_cmd as tc


def test_basic_act_pairwise_flags():
    cmd = tc.build_train_cmd(policy_type="act", dataset_ref="demo:v1",
                             output_dir="/mnt/train/j1")
    assert cmd[0] == "lerobot-train"
    assert cmd[1] == "--policy.type" and cmd[2] == "act"
    # 每个 flag 后必须紧跟一个 value：奇偶位校验
    assert all(str(c).startswith("--") for c in cmd[1::2])
    assert all(not str(c).startswith("--") for c in cmd[2::2])
    assert cmd[cmd.index("--dataset.root") + 1] == \
        "/data/k8s/kubeflow/global/dataset/demo/v1"
    assert cmd[cmd.index("--dataset.repo_id") + 1] == "local/demo_v1"
    assert cmd[cmd.index("--output_dir") + 1] == "/mnt/train/j1"
    assert cmd[cmd.index("--batch_size") + 1] == "8"
    assert cmd[cmd.index("--steps") + 1] == "10000"
    assert cmd[cmd.index("--wandb.enable") + 1] == "false"
    assert cmd[cmd.index("--resume") + 1] == "false"


def test_policy_exclusive():
    with pytest.raises(ValueError):
        tc.build_train_cmd(dataset_ref="d:v1", output_dir="/o")
    with pytest.raises(ValueError):
        tc.build_train_cmd(policy_type="act", policy_path="/ckpt",
                           dataset_ref="d:v1", output_dir="/o")


def test_policy_path_skips_type():
    cmd = tc.build_train_cmd(policy_path="lerobot/smolvla_base",
                             dataset_ref="d:v1", output_dir="/o")
    assert "--policy.path" in cmd and "--policy.type" not in cmd


def test_optional_and_extra_args():
    cmd = tc.build_train_cmd(policy_type="smolvla", dataset_ref="d:v1", output_dir="/o",
                             lr="1e-4", resume=True, wandb_enable=True,
                             extra_args="--policy.chunk_size 50 --env.type pusht")
    assert cmd[cmd.index("--optimizer.lr") + 1] == "1e-4"
    assert cmd[cmd.index("--resume") + 1] == "true"
    assert cmd[cmd.index("--wandb.enable") + 1] == "true"
    assert cmd[-4:] == ["--policy.chunk_size", "50", "--env.type", "pusht"]


def test_extra_args_rejected():
    for bad in ("rm -rf /", "ls;whoami", "--ok $(x)", "echo hi"):
        with pytest.raises(ValueError):
            tc.build_train_cmd(policy_type="act", dataset_ref="d:v1",
                               output_dir="/o", extra_args=bad)


def test_metachar_in_flag_and_unsafe_names_rejected():
    # flag 位元字符同样拒绝（train_cmd.sh 可被 bash 重放的注入面）
    with pytest.raises(ValueError):
        tc.build_train_cmd(policy_type="act", dataset_ref="d:v1",
                           output_dir="/o", extra_args="--a;rm=1 x")
    # dataset name/version 与 policy_path 字符集白名单
    with pytest.raises(ValueError):
        tc.build_train_cmd(policy_type="act", dataset_ref="na;me:v1", output_dir="/o")
    with pytest.raises(ValueError):
        tc.build_train_cmd(policy_path="../../etc/x", dataset_ref="d:v1", output_dir="/o")
    # hub repo id 形态合法
    cmd = tc.build_train_cmd(policy_path="lerobot/smolvla_base",
                             dataset_ref="d:v1", output_dir="/o")
    assert cmd[cmd.index("--policy.path") + 1] == "lerobot/smolvla_base"
