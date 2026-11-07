# LeRobot 具身智能/VLA 训练示例 pipeline

三节点链路演示 LeRobot 数据集接入 → 策略训练 → 仿真评测的端到端编排，对应算子模板
`lerobot-import` / `lerobot-train` / `lerobot-eval`（Task 11 注册）。

## 导入方法

1. 进入平台「pipeline」页面，新建/导入 pipeline，选择导入本目录的
   [`lerobot-demo.json`](lerobot-demo.json)。开源版无页面导入端点时，可将本 JSON 作为一个条目并入
   `myapp/init/init-pipeline.json` 后执行 `python myapp/cli.py init`（`create_pipeline`），
   或在 pipeline 页面按本 JSON 逐节点手工重建。
2. 导入依赖三模板已在 `init-job-template.json` 中登记（`images/lerobot/register_templates.py`
   幂等写入）。**存量库升级注意**：若三模板早于 workdir 修复前已存在，注册脚本幂等守卫不回填
   `job_template_workdir`，需删除旧模板记录后重跑 `python images/lerobot/register_templates.py`
   并重新初始化，否则容器内相对 command `python3 start.py` 因缺工作目录启动失败（见 commit 2423a6f / plans Task 11 修复项）。
3. 按实际环境调整各节点 `args`（数据源路径、`{{creator}}` 由平台运行时替换）。

## 参数链路

- 节点 1 `lerobot-import`：`--source /mnt/{{creator}}/raw/pusht_v3 --target_name pusht_demo --target_version v1`
  接入本地 LeRobotDataset 并生成画像，登记后数据集引用为 `pusht_demo:v1`。
- 节点 2 `lerobot-train`：`--dataset_ref pusht_demo:v1 --steps 10000 --output /mnt/{{creator}}/lerobot/train`，
  ACT 策略短训，产物落 lerobot 原生目录 `{output}/checkpoints/{step}/pretrained_model`。
- 节点 3 `lerobot-eval`：`--checkpoint /mnt/{{creator}}/lerobot/train/checkpoints/10000/pretrained_model`
  引用节点 2 末端 checkpoint，仿真评测输出契约指标与视频；血缘自动上溯命中节点 2 的 `manifest.json`。

> **挂载前置**：import 算子将数据集规范化写入 `BASE_DIR=/data/k8s/kubeflow/global/dataset/{name}/{version}`，
> train 算子同路径读 `.cube_dataset_meta` 并拼 `--dataset.root`。三节点已额外声明
> `/data/k8s/kubeflow/global(hostpath):/data/k8s/kubeflow/global` 挂载，使跨节点的数据集目录可见；
> 若移除该挂载，import→train 交接会断链（train 因 `--dataset.root` 不存在而回退 Hub 下载失败）。

## 手工验收清单（GPU 环境，交付后执行一次 · spec §8）

- [ ] `lerobot/pusht` Hub 数据集导入 → 画像正确；Data Explorer 可打开 `data/*.parquet`
- [ ] ACT×pusht 短训（`steps=200`）→ `metrics.json` 有 loss、checkpoints 产出
- [ ] ACT checkpoint × pusht 评测（`n_episodes=5`）→ `eval_metrics.json` 契约字段齐、视频落盘
- [ ] 错配测试（ALOHA checkpoint × pusht）→ 启动前报错、不拉起训练/评测进程
- [ ] `ROBOT_DRYRUN=1` 三算子均只产 `*_cmd.sh` 不执行
- [ ] 示例 pipeline 端到端跑通并通过 `scripts/validate_pipelines.py`

### `--dataset.repo_id + --dataset.root` 离线读数据实镜验证

本示例默认已锁定本地数据集传参形态为 `--dataset.repo_id local/{name}_{version}` +
`--dataset.root {base_dir}/{name}/{version}`（由 `lerobot_train_cmd.py` 单测锁定）。真机验收时须
确认该形态在 lerobot 0.6.2 实镜中可离线读取数据集；若失败，按 spec §4.3 只改
`lerobot_train_cmd.py` 一处并重跑：

```bash
python -m pytest tests/test_lerobot_train_cmd.py -v
```
