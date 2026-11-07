"""lerobot-import 入口（spec §3；DRYRUN 只产 import_plan.json；算子不写 DB）。"""
import argparse
import json
import os
import pathlib
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lerobot_shared"))

import import_cmd  # noqa: E402
import lerobot_profile as profile_mod  # noqa: E402
from manifest_util import write_manifest  # noqa: E402


def _bool(s):
    return str(s).lower() in ("true", "1", "yes")


def _task_counts(dst):
    """v3 任务分布在 meta/tasks.parquet；pyarrow/pandas 缺失或文件不存在时返回 None。"""
    p = pathlib.Path(dst) / "meta" / "tasks.parquet"
    if not p.is_file():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        if "task_index" not in df.columns:
            return None
        return {str(k): int(v) for k, v in df["task_index"].value_counts().items()}
    except Exception:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(prog="lerobot-import")
    p.add_argument("--source_type", required=True, choices=["local_path", "hub_repo_id"])
    p.add_argument("--source", required=True)
    p.add_argument("--target_name", required=True)
    p.add_argument("--target_version", default="v1")
    p.add_argument("--hub_endpoint", default="")
    p.add_argument("--link_mode", nargs="?", const="true", default="false")
    p.add_argument("--base_dir", default=import_cmd.BASE_DIR)
    a = p.parse_args(argv)
    dry = os.environ.get("ROBOT_DRYRUN") == "1"

    plan = import_cmd.resolve_paths(a.source_type, a.source, a.target_name,
                                    a.target_version, a.base_dir, _bool(a.link_mode))
    dst = pathlib.Path(plan["dst"])

    if dry:
        # DRYRUN 不触碰共享数据集目录 dst（避免凭空建正式数据集目录/覆写真实 manifest）；
        # 产物落同辈 .dryrun 侧目录。
        dry_dir = dst.parent / (dst.name + ".dryrun")
        dry_dir.mkdir(parents=True, exist_ok=True)
        (dry_dir / "import_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        write_manifest(dry_dir, op="lerobot-import", args=vars(a), parents=[],
                       files=["import_plan.json"], stats={"dry_run": True})
        print(json.dumps({"dry_run": True, "plan": plan}))
        return 0

    if plan["kind"] == "hub":
        if dst.exists() and any(dst.iterdir()):
            print("target %s not empty, overwrite refused" % dst, file=sys.stderr)
            return 2
        dst.parent.mkdir(parents=True, exist_ok=True)
        if a.hub_endpoint:
            os.environ["HF_ENDPOINT"] = a.hub_endpoint
        last_err = None
        for _ in range(3):  # spec §3.5：Hub 拉取失败重试 3 次后退出
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id=plan["src"], repo_type="dataset",
                                  local_dir=str(dst), allow_patterns=None)
                last_err = None
                break
            except Exception as e:
                last_err = e
        if last_err is not None:
            print("hub download failed after 3 attempts: %s" % last_err, file=sys.stderr)
            return 3
        info_file = dst / "meta" / "info.json"
        if not info_file.is_file():
            print("hub dataset missing meta/info.json", file=sys.stderr)
            return 3
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            import_cmd.validate_info(info)
        except (ValueError, json.JSONDecodeError) as e:
            print(str(e), file=sys.stderr)
            return 3
    else:
        src = pathlib.Path(plan["src"])
        info_file = src / "meta" / "info.json"
        if not info_file.is_file():
            print("missing meta/info.json in %s" % src, file=sys.stderr)
            return 3
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            import_cmd.validate_info(info)
        except (ValueError, json.JSONDecodeError) as e:
            print(str(e), file=sys.stderr)
            return 3
        if dst.exists() and any(dst.iterdir()):
            print("target %s not empty, overwrite refused" % dst, file=sys.stderr)
            return 2
        dst.parent.mkdir(parents=True, exist_ok=True)
        if plan["kind"] == "link":
            # 免拷贝：dst 建成真实目录，仅将源子项逐个符号链接进来；
            # 派生产物(profile/meta/manifest)落 dst 本身而非经符号链接写穿源目录。
            dst.mkdir(parents=True, exist_ok=True)
            for entry in src.iterdir():
                os.symlink(str(entry.resolve()), str(dst / entry.name))
        else:
            shutil.copytree(str(src), str(dst))

    info = json.loads((dst / "meta" / "info.json").read_text(encoding="utf-8"))
    prof = profile_mod.build_profile(info, _task_counts(dst))
    (dst / "lerobot_profile.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = {"format": "lerobot", "version": prof["format_version"],
            "source": plan["src"], "profile": prof}
    (dst / ".cube_dataset_meta").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest(dst, op="lerobot-import",
                   args={k: v for k, v in vars(a).items() if v not in (None, "", False)},
                   parents=[], files=["meta/info.json", ".cube_dataset_meta",
                                      "lerobot_profile.json"],
                   stats={"dry_run": False, "total_frames": prof["total_frames"],
                          "total_episodes": prof["total_episodes"]},
                   extra={"dataset_dir": str(dst)})
    print(json.dumps({"dst": str(dst), "profile": prof}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
