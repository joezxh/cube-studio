# 标注平台集成（社区 LabelStudio）（S1）设计文档

> 日期：2026-11-07 ｜ 来源：docs/企业版功能.md L44-45「数据标注」全部方括号项，经确认按「集成社区 LabelStudio」路线落地
> 状态：待评审

## 1. 背景与现状

开源版**无自研标注平台**（gov-social-llm spec 亦书面确认），但已存在三类可复用资产：

| 资产 | 位置 | 状态 |
|---|---|---|
| istio 路由 `/labelstudio/` → `labelstudio.kubeflow.svc.cluster.local:8080`（带 `myapp_username` cookie 校验） | install/kubernetes/virtual.yaml | ✅ 已有 |
| 标注数据目录 `/data/k8s/kubeflow/labelstudio/` | install/kubernetes/init_node.sh | ✅ 已有 |
| 用户信息接口 `GET /userinfo/api/current/userinfo`（返回 username/roles/org 等） | myapp/views/view_user_role.py | ✅ 已有 |
| 自动化标注 ML-Backend 协议实现（labelstudio_setup/download/…） | job-template/job/yolov8/ | ✅ 已有 |
| labelstudio 的 deployment/service/pvc | — | ❌ 缺失 |
| 数据集↔标注任务的导入导出 | — | ❌ 缺失 |

## 2. 目标（v1）

1. 补齐 label-studio-ce 的 K8s 部署配置，与既有 istio 路由对齐。
2. 平台主菜单增加「数据标注」入口。
3. **数据集 → LabelStudio 任务推送**：将表格/文本/图片数据集转换为 LS import 任务。
4. **LabelStudio 导出 → 数据集回存**：拉取 LS 标注结果，登记为新版本数据集。
5. 自动化标注继续经 ML-Backend（已开源，仅需在文档中串接说明）。

## 3. 非目标（v1 明确不承诺）

- **SSO 免登**：LS CE 不支持，v1 为「平台跳转 + LS 独立账号」（账号说明文档化）。
- **审核流/标注质量打分**：LS 企业版功能，CE 无 review stream；v1 以「标注完成度统计 + 导出后人工复核」替代，不承诺项写入部署文档。
- 自研标注 UI、多模态全覆盖（v1 仅文本分类 + 图片分类两类任务模板）。
- 8 国语言：LS 自带界面多语言设置，文档说明即可。

## 4. 架构设计

### 4.1 部署配置（新增）

`install/kubernetes/labelstudio/`：

- `deployment.yaml`：镜像 `heartexlabs/label-studio:latest`（tag 在文件头注释记录，遵循项目惯例），端口 8080，挂 hostPath `/data/k8s/kubeflow/labelstudio/`（与 init_node.sh 目录对齐），环境变量 `LABEL_STUDIO_HOST=/labelstudio`。
- `service.yaml`：`labelstudio.kubeflow.svc.cluster.local:8080`（与 virtual.yaml destination 一致）。
- 可选 `ml-backend.yaml`：ML-Backend 部署样例（对接 yolov8 镜像），注释化提供。

### 4.2 平台侧集成（myapp）

**菜单入口**：`myapp/views/home.py` 菜单树「数据」分组下新增「数据标注」→ 链接 `/labelstudio/`（外链型菜单，沿用现有 menu 构造方式）。

**数据集 → LS 推送**（`view_dataset.py` 新增 API）：

```
POST /dataset_modelview/api/push_to_labelstudio/<dataset_id>
body: { "ls_url": "", "ls_token": "", "task_type": "text_classification" | "image_classification", "text_col": "", "image_col": "", "label_config": "" }
```

- 读取层复用 S4 的 `dataset_reader.load_dataframe`（若 S4 未合入则先实现最小 csv/jsonl 读取，plan 阶段定依赖顺序）。
- 转换规则：
  - text_classification：每行 → `{"text": <text_col>, "meta": {"dataset": name, "row_idx": i}}`。
  - image_classification：每行 → `{"image": <可访问 URL/path>, "meta": {...}}`（v1 传引用路径，不上传文件本体）。
- 经 LS REST API（`POST /api/projects/{id}/import` + `POST /api/projects` 建项目）推送；`ls_token` 优先取请求参数，缺省回落 `conf.get('LABELSTUDIO_TOKEN','')`。
- 幂等：以 `meta.dataset+row_idx` 为唯一键，重复推送跳过。

**LS → 数据集回存**（`view_dataset.py` 新增 API）：

```
POST /dataset_modelview/api/import_from_labelstudio
body: { "ls_url": "", "ls_token": "", "ls_project_id": 1, "dataset_name": "", "dataset_version": "" }
```

- `GET /api/projects/{id}/export?exportType=JSON` 拉取标注结果 → 转换为 jsonl（含原数据 + 标注字段 `label`）→ 写入 `dataset/{name}/{version}/labelstudio_{project_id}.jsonl` → 登记 `Dataset` 记录（复用现有 add 逻辑）。

### 4.3 数据流

```
平台数据集 --push(REST)--> LS 项目任务 --人工/ML-Backend 标注--> LS 导出
                                                              ↓
平台新数据集版本 <--import(REST) + 登记 Dataset<-- JSON 标注结果
```

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| LS 不可达 / token 无效 | `status:1` + message（含 LS 响应摘要），不落脏数据 |
| 数据集格式不支持推送 | v1 白名单（csv/jsonl）外直接拒绝并提示 |
| LS 项目已存在同名 | 复用该项目（按 name 查询），不重复建 |
| 回存目录已存在同名文件 | 版本号自增校验（复用 Dataset version 惯例） |

## 6. 测试方案（TDD）

- `tests/test_labelstudio_bridge.py`：
  1. 行→LS task 转换纯函数（text/image 两类、meta 注入、幂等键）单测。
  2. LS 导出 JSON → jsonl 转换单测（含空标注、多标注结果取舍规则：取首个标注）。
  3. push/import API 用 monkeypatch 假 `requests`（遵循项目测试惯例，HTTP 全 mock）：成功、LS 500、token 缺失三分支。
- 部署 yaml：`kubectl apply --dry-run=client` 文档化校验步骤。
- 跨平台：不依赖真实 LS 实例。

## 7. 风险与依赖

| 风险 | 处置 |
|---|---|
| LS CE 无 SSO/审核流（企业版宣传项无法全对齐） | §3 已明确 v1 承诺边界，写入部署文档 |
| LS token 管理明文风险 | 支持请求参数优先 + config 兜底，文档提示使用 secret 注入 |
| 图片数据集本体外发 | v1 仅传引用 URL，不上传文件；内网可访问性作为部署前提写入文档 |
| 与 S4 的读取层依赖 | plan 阶段排定顺序：S4 先行或本 spec 内置最小读取 |
