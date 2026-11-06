# gov-manifest — 数据血缘共享库与 CLI

方案 A「薄算子」体系中**唯一被其他算子 `import` 的共享库**（spec §3.1）。每个算子的产出目录都经
`write_manifest` 落一份 `manifest.json`，记录生产者的镜像/commit/参数、上游血缘引用与数据文件摘要，
使蒸馏链路的每一步数据可溯源、可校验、可封存。

## 目录结构

```
ops/gov-manifest/
├── lib/gov_manifest/__init__.py   # 共享库（其他算子经此 import）
├── start.py                       # CLI 入口：--cmd generate|verify|seal
├── Dockerfile                     # python:3.10-slim（纯 CPU）
├── requirements.txt               # 空（纯标准库）
└── README.md
```

`conftest.py` 已把 `lib/` 注入 `sys.path`，本地测试与算子源码均可 `from gov_manifest import ...`。

## 库 API（Task 3–7 消费的确切签名）

| 函数 | 说明 |
|------|------|
| `sha256_file(path) -> str` | 64 位小写 hex |
| `jsonl_stats(path) -> dict` | `{"rows","sha256","label_dist"}`，行内无 `label` 则分布为空 |
| `write_manifest(out_dir, *, op, args, parents=(), files=(), stats=None, extra=None) -> dict` | 写 `out_dir/manifest.json` |
| `read_manifest(dir_) -> dict \| None` | 读取 |
| `verify_manifest(dir_) -> (ok, problems)` | 校验自签名 / 文件摘要漂移 / 上游血缘断裂 |
| `seal(dir_) -> dict` | 置 `sealed=true`、重算 `self_digest`、数据文件与 manifest 置只读 |

`manifest.json` schema：

```json
{
  "dataset": "/mnt/gov/distill/T1/v1",
  "created_at": "…Z",
  "producer": {"op": "gov-distill-gen", "image": "<GOV_IMAGE|unknown>",
               "git_commit": "<GOV_GIT_COMMIT|unknown>", "args": {"…": "…"}},
  "parents": [{"path": "…/manifest.json", "digest": "<上游 self_digest>"}],
  "files":   [{"path": "raw.jsonl", "rows": 123, "sha256": "…", "label_dist": {"…": 0}}],
  "stats":   {},
  "sealed":  false,
  "self_digest": "sha256(规范化 JSON，除 self_digest 外)"
}
```

`image` / `git_commit` 从环境变量 `GOV_IMAGE` / `GOV_GIT_COMMIT` 读取（镜像构建期注入），缺省 `"unknown"`。

## CLI

```bash
python start.py --cmd generate --dir /mnt/gov/distill/T1/v1 \
    --files train.jsonl --op gov-distill-gen \
    --args '{"--temperature":0.7}' \
    --parents '[{"path":"/mnt/gov/seeds/T1/v1/manifest.json","digest":"…"}]'
python start.py --cmd verify --dir /mnt/gov/distill/T1/v1   # 失败 exit 2 并打印 problems
python start.py --cmd seal   --dir /mnt/gov/eval/blind/v1
```

> 采用扁平 `--cmd` flag 而非位置子命令，使 Pipeline JSON 的 `args` 可全部以 `--` 键表达，
> 与 `scripts/validate_pipelines.py` 规则 3 保持一致。

## 平台算子登记

镜像 build 后在 cube-studio「镜像管理」登记，并在「模板自定义」注册为算子 `gov-manifest`；
参数类型对照 spec §2.2。`volume_mount` 统一 `gov-nfs(pvc):/mnt`，数据根 `DATA_ROOT=/mnt/gov`。
