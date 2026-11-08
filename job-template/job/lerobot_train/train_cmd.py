"""lerobot-train 命令组装纯函数（spec §4；本地数据集默认 --dataset.repo_id + --dataset.root，
spec §4.3 实测锁定项，如需改形态只改本函数拼装两处）。"""
import re
import shlex

BASE_DIR = "/data/k8s/kubeflow/global/dataset"
_META_CHARS = set(";|&$<>`\n'\"")
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")  # policy_path 允许 /（hub repo id 与容器内绝对路径），逐字符集已排除 shell 元字符


def _check_safe_part(value, what):
    if not _SAFE_PART.match(str(value)) or str(value) == "." or ".." in str(value):
        raise ValueError("unsafe %s: %r" % (what, value))


def _check_safe_path(value, what):
    v = str(value)
    if not _SAFE_PATH.match(v) or ".." in v:
        raise ValueError("unsafe %s: %r" % (what, value))


def parse_dataset_ref(ref):
    parts = str(ref).split(":")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError("dataset_ref must be name:version, got %r" % (ref,))
    return parts[0].strip(), parts[1].strip()


def _validate_extra(extra_args):
    tokens = shlex.split(str(extra_args)) if extra_args else []
    if len(tokens) % 2 != 0:
        raise ValueError("extra_args must be flag-value pairs")
    for i, tok in enumerate(tokens):
        if _META_CHARS & set(tok):
            raise ValueError("shell metacharacters forbidden in token: %r" % (tok,))
        if i % 2 == 0 and not tok.startswith("--"):
            raise ValueError("extra flag must start with --: %r" % (tok,))
    return tokens


def build_train_cmd(*, dataset_ref, output_dir, policy_type=None, policy_path=None,
                    batch_size=8, steps=10000, save_freq=5000, log_freq=200,
                    lr=None, resume=False, wandb_enable=False,
                    extra_args="", base_dir=BASE_DIR):
    if bool(policy_type) == bool(policy_path):
        raise ValueError("exactly one of policy_type/policy_path required")
    name, version = parse_dataset_ref(dataset_ref)
    _check_safe_part(name, "dataset name")
    _check_safe_part(version, "dataset version")
    cmd = ["lerobot-train"]
    if policy_type:
        cmd += ["--policy.type", str(policy_type)]
    else:
        _check_safe_path(policy_path, "policy_path")
        cmd += ["--policy.path", str(policy_path)]
    cmd += ["--dataset.repo_id", "local/%s_%s" % (name, version),
            "--dataset.root", "%s/%s/%s" % (str(base_dir).rstrip("/"), name, version),
            "--output_dir", str(output_dir),
            "--batch_size", str(batch_size), "--steps", str(steps),
            "--save_freq", str(save_freq), "--log_freq", str(log_freq),
            "--resume", "true" if resume else "false",
            "--wandb.enable", "true" if wandb_enable else "false"]
    if lr:
        cmd += ["--optimizer.lr", str(lr)]
    cmd += _validate_extra(extra_args)
    return cmd
