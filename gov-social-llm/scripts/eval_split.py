"""评测集切分脚本（计划 Task 8 split-eval 步骤引用）。

将脱敏后的评测集按 --ratio 随机切分为 dev/blind 两份（互斥、可复现 seed）；
--redteam-out 若给出则原样透传红队集占位（红队集通常由安全同学独立维护）。
仅标准库，跨平台；盲测集的 manifest 封存由下游 gov-manifest --cmd seal 完成。
"""
import argparse
import json
import pathlib
import random


def _load(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _dump(rows, path):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def split(rows, ratio, seed):
    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    n_dev = int(round(len(rows) * ratio))
    dev_i = set(idx[:n_dev])
    dev = [r for i, r in enumerate(rows) if i in dev_i]
    blind = [r for i, r in enumerate(rows) if i not in dev_i]
    return dev, blind


def main(argv=None):
    p = argparse.ArgumentParser(prog="eval_split")
    p.add_argument("--input", required=True)
    p.add_argument("--dev-out", required=True)
    p.add_argument("--blind-out", required=True)
    p.add_argument("--redteam-out", default=None)
    p.add_argument("--ratio", type=float, default=0.7)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args(argv)

    rows = _load(a.input)
    dev, blind = split(rows, a.ratio, a.seed)
    _dump(dev, a.dev_out)
    _dump(blind, a.blind_out)
    if a.redteam_out:
        _dump([], a.redteam_out)
    print(json.dumps({"total": len(rows), "dev": len(dev), "blind": len(blind)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
