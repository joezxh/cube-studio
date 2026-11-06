"""gov-manifest CLI（spec §3.1 / 计划 Task 2 Step 5）。

子能力经 `--cmd {generate,verify,seal}` 选择，路径统一 `--dir`。
采用扁平 flag（而非位置子命令）以便在 Pipeline JSON 的 args 中全部以 `--` 键表达，
与 scripts/validate_pipelines.py 规则 3 一致。

用法示例：
  python start.py --cmd generate --dir /mnt/gov/distill/T1/v1 \
      --files train.jsonl --op gov-distill-gen --args '{"--temperature":0.7}'
  python start.py --cmd verify --dir /mnt/gov/distill/T1/v1
  python start.py --cmd seal   --dir /mnt/gov/eval/blind/v1

退出码：0 成功；2 校验失败（verify 检出问题时，problems 打到 stderr）。
"""
import argparse
import json
import os
import sys

# gov_manifest 位于本文件同级的 lib/ 子目录（镜像内 /app/start.py 与 /app/lib/gov_manifest）。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from gov_manifest import seal, verify_manifest, write_manifest  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(prog="gov-manifest", description="数据血缘 manifest 生成/校验/封存")
    p.add_argument("--cmd", required=True, choices=["generate", "verify", "seal"])
    p.add_argument("--dir", required=True, help="产出/数据集目录")
    p.add_argument("--files", nargs="*", default=[], help="generate：目录内相对数据文件路径")
    p.add_argument("--op", default="gov-manifest", help="generate：生产算子名")
    p.add_argument("--args", default="{}", help="generate：producer.args 的 JSON")
    p.add_argument("--parents", default="[]", help="generate：parents 列表 [{path,digest}]")
    a = p.parse_args(argv)

    if a.cmd == "generate":
        m = write_manifest(a.dir, op=a.op, args=json.loads(a.args),
                           parents=json.loads(a.parents), files=a.files)
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "verify":
        ok, problems = verify_manifest(a.dir)
        for pr in problems:
            print(pr, file=sys.stderr)
        return 0 if ok else 2
    # seal
    m = seal(a.dir)
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
