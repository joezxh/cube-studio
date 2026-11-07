# 标注平台集成（社区 LabelStudio）（S1）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 LabelStudio CE 的 K8s 部署配置，实现数据集→LS 推送与 LS 导出→数据集回存的双向桥接，并启用平台「标注平台」菜单入口。

**Architecture:** 部署物（deployment/service + 注释化 ml-backend 样例）落 `install/kubernetes/labelstudio/`，与既有 istio 路由（`/labelstudio/` → `labelstudio.kubeflow.svc.cluster.local:8080`）、hostPath 目录（`/data/k8s/kubeflow/labelstudio/`）严格对齐。myapp 侧桥接逻辑全部下沉到零 Flask 依赖的 `myapp/utils/labelstudio_bridge.py`（LS task 转换/幂等去重/导出解析为纯函数，LS REST 调用为独立可 mock 函数），`view_dataset.py` 只做薄 handler。执行顺序依赖 S4 的 `load_dataframe`（先实施 S4 计划）。

**Tech Stack:** LabelStudio CE（heartexlabs/label-studio）/ requests（经 kubernetes 客户端传递依赖已存在，本计划恢复显式声明）/ pandas / pytest + monkeypatch

**Spec:** `docs/superpowers/specs/2026-11-07-labelstudio-integration-design.md`

## Global Constraints

- v1 仅支持 `text_classification` / `image_classification` 两类任务模板（spec §3）；数据集格式白名单 csv/jsonl（spec §5）。
- 非目标不变：SSO 免登、审核流、自研 UI、多模态（spec §3，部署文档中书面声明）。
- `ls_token` 优先取请求参数，缺省回落 `conf.get('LABELSTUDIO_TOKEN','')`；两者皆空 → `status:1` 拒绝（spec §4.2/§5）。
- 幂等键：`meta.dataset + meta.row_idx`，重复推送跳过（spec §4.2）。
- LS 项目按 name 查询复用，不重复创建（spec §5）。
- 导出标注取舍：无标注保留原数据 `label` 为空；多标注取首个（spec §6）。
- 回存文件名冲突：`labelstudio_{pid}.jsonl` 已存在时改用 `labelstudio_{pid}_{YYYYmmddHHMMSS}.jsonl`（spec §5「版本号自增校验」的落地形式）。
- 图片任务 v1 仅传引用 URL/路径，不上传文件本体（spec §4.2）。
- 桥接 util 模块**禁止 import 任何 `myapp.*`**（同 S4 计划约束：本地无法 boot Flask app，TDD 覆盖纯函数与 REST 客户端，API handler 薄）。
- 测试命令在仓库根：`python -m pytest tests/test_labelstudio_bridge.py -v`；HTTP 一律 monkeypatch 假 `requests`，不依赖真实 LS 实例（spec §6）。
- 每个 Task 结束 commit，`feat:` / `docs:` / `build:` 前缀。

---

### Task 1: K8s 部署配置

**Files:**
- Create: `install/kubernetes/labelstudio/deployment.yaml`
- Create: `install/kubernetes/labelstudio/service.yaml`
- Create: `install/kubernetes/labelstudio/ml-backend.yaml`（整文件注释化的样例）
- Create: `install/kubernetes/labelstudio/README.md`

**Interfaces:**
- Consumes: 既有资产——istio 路由 destination `labelstudio.kubeflow.svc.cluster.local:8080`（install/kubernetes/virtual.yaml）、hostPath 目录 `/data/k8s/kubeflow/labelstudio/`（install/kubernetes/init_node.sh 已创建）。
- Produces: `kubectl apply -f install/kubernetes/labelstudio/` 可部署的 LS 服务，命名空间/服务名与 virtual.yaml 完全对齐。

- [ ] **Step 1: 创建 deployment.yaml**

```yaml
# LabelStudio CE 部署（与 virtual.yaml 的 /labelstudio/ 路由对齐）
# 镜像 tag 记录：heartexlabs/label-studio:latest（上线前固定为具体版本号并回填注释）
apiVersion: apps/v1
kind: Deployment
metadata:
  name: labelstudio
  namespace: kubeflow
  labels:
    app: labelstudio
spec:
  replicas: 1
  selector:
    matchLabels:
      app: labelstudio
  template:
    metadata:
      labels:
        app: labelstudio
    spec:
      containers:
        - name: labelstudio
          image: heartexlabs/label-studio:latest
          ports:
            - containerPort: 8080
          env:
            # 子路径反代（istio /labelstudio/ -> 本服务），LS 以此生成静态资源前缀
            - name: LABEL_STUDIO_HOST
              value: /labelstudio
            # 数据目录（任务/标注/上传物持久化）
            - name: LABEL_STUDIO_DATA
              value: /label-studio/data
          volumeMounts:
            - name: labelstudio-data
              mountPath: /label-studio/data
      volumes:
        - name: labelstudio-data
          hostPath:
            # 与 init_node.sh 创建的目录一致
            path: /data/k8s/kubeflow/labelstudio/
            type: DirectoryOrCreate
```

- [ ] **Step 2: 创建 service.yaml**

```yaml
# 服务名/端口必须与 virtual.yaml 的 destination 保持一致
apiVersion: v1
kind: Service
metadata:
  name: labelstudio
  namespace: kubeflow
  labels:
    app: labelstudio
spec:
  ports:
    - name: http
      port: 8080
      targetPort: 8080
  selector:
    app: labelstudio
```

- [ ] **Step 3: 创建 ml-backend.yaml（注释化样例，对接 yolov8 ML-Backend 协议）**

```yaml
# ML-Backend 部署样例（自动化标注，协议实现见 job-template/job/yolov8/）。
# 默认不部署；启用时取消注释、填入模型服务镜像并 kubectl apply。
# apiVersion: apps/v1
# kind: Deployment
# metadata:
#   name: labelstudio-ml-backend
#   namespace: kubeflow
# spec:
#   replicas: 1
#   selector:
#     matchLabels:
#       app: labelstudio-ml-backend
#   template:
#     metadata:
#       labels:
#         app: labelstudio-ml-backend
#     spec:
#       containers:
#         - name: ml-backend
#           image: <yolov8-ml-backend 镜像>   # 由 job-template/job/yolov8 构建产物提供
#           ports:
#             - containerPort: 9090
# ---
# apiVersion: v1
# kind: Service
# metadata:
#   name: labelstudio-ml-backend
#   namespace: kubeflow
# spec:
#   ports:
#     - port: 9090
#       targetPort: 9090
#   selector:
#     app: labelstudio-ml-backend
```

- [ ] **Step 4: 创建 README.md**

内容必须包含以下六节（写入 `install/kubernetes/labelstudio/README.md`）：

```markdown
# LabelStudio 部署与集成说明

## 部署
1. 节点已由 init_node.sh 创建 /data/k8s/kubeflow/labelstudio/ 目录。
2. kubectl apply -f install/kubernetes/labelstudio/（dry-run 校验：kubectl apply --dry-run=client -f install/kubernetes/labelstudio/）
3. istio 路由 /labelstudio/ 已存在于 install/kubernetes/virtual.yaml，无需变更。

## 账号说明（v1 边界）
LS CE 无 SSO：首次访问 /labelstudio/ 需在 LS 内注册账号（平台 cookie 仅拦截入口，LS 内为独立账号）。

## v1 明确不承诺
SSO 免登 / 审核流（review stream）/ 标注质量打分 —— 均为 LS 企业版能力；v1 以「标注完成度统计 + 导出后人工复核」替代。

## token 管理
- 桥接 API 的 ls_token 请求参数优先，缺省读服务端配置 LABELSTUDIO_TOKEN。
- 生产环境建议将 LABELSTUDIO_TOKEN 通过 secret 注入，避免明文落配置。

## 图片数据集前提
v1 图片任务仅向 LS 传引用 URL/路径，不上传文件本体；要求 LS Pod 可经该 URL 访问到图片（内网可达性为部署前提）。

## 自动化标注
ML-Backend 协议实现见 job-template/job/yolov8/；启用方式见 ml-backend.yaml 注释。
```

- [ ] **Step 5: dry-run 校验**

Run: `kubectl apply --dry-run=client -f install/kubernetes/labelstudio/`
Expected: deployment/service 校验通过（本机无 kubectl/集群时，将「dry-run 待部署环境执行」记录到 PR 说明，不阻塞 commit）

- [ ] **Step 6: Commit**

```bash
git add install/kubernetes/labelstudio/
git commit -m "feat: LabelStudio CE 部署配置与说明（deployment/service/ml-backend 样例，S1）"
```

---

### Task 2: 桥接转换纯函数（TDD）

**Files:**
- Create: `myapp/utils/labelstudio_bridge.py`
- Test: `tests/test_labelstudio_bridge.py`（本 Task 先写转换部分测试）

**Interfaces:**
- Consumes: 无（pandas DataFrame 鸭子类型入参）。
- Produces（Task 3/4 依赖，签名逐字一致）:

```python
def rows_to_ls_tasks(df, task_type: str, text_col: str = '', image_col: str = '', dataset_name: str = '') -> list[dict]
    # text_classification: 每行 -> {"data": {"text": <text_col值str>, "meta": {"dataset": name, "row_idx": i}}}
    # image_classification: 每行 -> {"data": {"image": <image_col值str>, "meta": {...}}}
    # task_type 非法 -> raise ValueError('不支持的任务类型')

def dedupe_tasks(tasks: list[dict]) -> list[dict]
    # 以 (meta.dataset, meta.row_idx) 为键去重，保留首次出现

def ls_export_to_records(export_json: list[dict]) -> list[dict]
    # LS export JSON(task 数组) -> [{"text"/"image":..., "label": str, "meta": {...}}]
    # label 取首个 annotation 的首个 result 的 value.choices[0]（分类任务），
    #   无 annotation/无 result -> label = ""
```

- [ ] **Step 1: 写失败测试**

创建 `tests/test_labelstudio_bridge.py`：

```python
import pandas as pd
import pytest

from myapp.utils.labelstudio_bridge import (
    dedupe_tasks,
    ls_export_to_records,
    rows_to_ls_tasks,
)


def test_rows_to_text_tasks():
    df = pd.DataFrame({"text": ["a", "b"]})
    tasks = rows_to_ls_tasks(df, 'text_classification', text_col='text', dataset_name='ds')
    assert tasks[0]["data"] == {"text": "a", "meta": {"dataset": "ds", "row_idx": 0}}
    assert tasks[1]["data"]["meta"]["row_idx"] == 1


def test_rows_to_image_tasks():
    df = pd.DataFrame({"img": ["s3://a.jpg", "s3://b.jpg"]})
    tasks = rows_to_ls_tasks(df, 'image_classification', image_col='img', dataset_name='ds')
    assert tasks[0]["data"]["image"] == "s3://a.jpg"
    assert tasks[0]["data"]["meta"] == {"dataset": "ds", "row_idx": 0}


def test_invalid_task_type():
    df = pd.DataFrame({"text": ["a"]})
    with pytest.raises(ValueError, match="不支持的任务类型"):
        rows_to_ls_tasks(df, 'ner', text_col='text')


def test_dedupe_tasks():
    df = pd.DataFrame({"text": ["a", "a"]})
    tasks = rows_to_ls_tasks(df, 'text_classification', text_col='text', dataset_name='ds')
    twice = tasks + tasks
    assert len(dedupe_tasks(twice)) == 2


def test_export_to_records_first_annotation_wins():
    export = [{
        "data": {"text": "a", "meta": {"dataset": "ds", "row_idx": 0}},
        "annotations": [
            {"result": [{"value": {"choices": ["标签A"]}}]},
            {"result": [{"value": {"choices": ["标签B"]}}]},
        ],
    }]
    records = ls_export_to_records(export)
    assert records[0] == {"text": "a", "label": "标签A", "meta": {"dataset": "ds", "row_idx": 0}}


def test_export_unlabeled_keeps_empty_label():
    export = [{"data": {"text": "a", "meta": {"dataset": "ds", "row_idx": 0}}, "annotations": []}]
    records = ls_export_to_records(export)
    assert records[0]["label"] == ""


def test_export_no_annotations_key():
    export = [{"data": {"image": "s3://x.jpg", "meta": {"dataset": "ds", "row_idx": 1}}}]
    records = ls_export_to_records(export)
    assert records[0]["image"] == "s3://x.jpg"
    assert records[0]["label"] == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_labelstudio_bridge.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'myapp.utils.labelstudio_bridge'`

- [ ] **Step 3: 最小实现**

创建 `myapp/utils/labelstudio_bridge.py`：

```python
# LabelStudio 桥接层：task 转换/幂等去重/导出解析（纯函数 + REST 客户端）
# 注意：本模块禁止 import 任何 myapp.* 模块，保持可独立测试
import requests

VALID_TASK_TYPES = ('text_classification', 'image_classification')


def rows_to_ls_tasks(df, task_type, text_col='', image_col='', dataset_name=''):
    if task_type not in VALID_TASK_TYPES:
        raise ValueError('不支持的任务类型: %s' % task_type)
    value_col = text_col if task_type == 'text_classification' else image_col
    tasks = []
    for row_idx, record in enumerate(df.to_dict(orient='records')):
        value = record.get(value_col, '')
        tasks.append({
            'data': {
                task_type == 'text_classification' and 'text' or 'image': str(value if value is not None else ''),
                'meta': {'dataset': dataset_name, 'row_idx': row_idx},
            }
        })
    return tasks


def dedupe_tasks(tasks):
    seen, result = set(), []
    for task in tasks:
        meta = task.get('data', {}).get('meta', {})
        key = (meta.get('dataset'), meta.get('row_idx'))
        if key in seen:
            continue
        seen.add(key)
        result.append(task)
    return result


def _first_label(annotation):
    for item in annotation.get('result', []):
        choices = (item.get('value') or {}).get('choices') or []
        if choices:
            return str(choices[0])
    return None


def ls_export_to_records(export_json):
    records = []
    for task in export_json or []:
        data = dict(task.get('data') or {})
        meta = data.pop('meta', {})
        label = ''
        for annotation in task.get('annotations') or []:
            first = _first_label(annotation)
            if first is not None:
                label = first
                break  # 多标注取首个
        records.append({**data, 'label': label, 'meta': meta})
    return records
```

（`requests` 的 import 在 Task 3 使用，本 Task 先行引入。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_labelstudio_bridge.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/labelstudio_bridge.py tests/test_labelstudio_bridge.py
git commit -m "feat: LabelStudio 桥接转换纯函数（task 转换/幂等去重/导出解析，S1）"
```

---

### Task 3: LS REST 客户端函数（TDD，HTTP 全 mock）

**Files:**
- Modify: `myapp/utils/labelstudio_bridge.py`（追加 REST 客户端函数）
- Modify: `tests/test_labelstudio_bridge.py`（追加 mock 测试）

**Interfaces:**
- Consumes: Task 2 的 `dedupe_tasks`（push 前幂等）。
- Produces（Task 4 依赖，签名逐字一致）:

```python
def ls_headers(ls_token: str) -> dict                      # {'Authorization': 'Token <token>'}
def create_or_get_project(ls_url: str, ls_token: str, name: str, label_config: str) -> int
    # 按 name 查询已有项目则复用其 id；否则 POST /api/projects 创建并返回新 id
def push_tasks(ls_url: str, ls_token: str, project_id: int, tasks: list[dict]) -> dict
    # POST /api/projects/{id}/import 响应 JSON
def fetch_export(ls_url: str, ls_token: str, project_id: int) -> list[dict]
    # GET /api/projects/{id}/export?exportType=JSON -> list
    # 非 2xx / token 为空 -> raise LsApiError(message)
class LsApiError(Exception)                                # message 含 LS 响应摘要
```

- [ ] **Step 1: 追加失败测试（追加到 tests/test_labelstudio_bridge.py 末尾）**

```python
from myapp.utils import labelstudio_bridge as bridge
from myapp.utils.labelstudio_bridge import LsApiError


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


def test_ls_headers():
    assert bridge.ls_headers('tk') == {'Authorization': 'Token tk'}


def test_create_or_get_project_reuse(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(200, {"results": [{"id": 7}]})

    monkeypatch.setattr(bridge.requests, 'get', fake_get)
    pid = bridge.create_or_get_project('http://ls', 'tk', 'my-project', '<View/>')
    assert pid == 7
    assert 'name=my-project' in calls[0]


def test_create_or_get_project_create(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(200, {"results": []})

    def fake_post(url, headers=None, json=None, timeout=None):
        assert json == {'name': 'my-project', 'label_config': '<View/>'}
        return FakeResponse(201, {"id": 9})

    monkeypatch.setattr(bridge.requests, 'get', fake_get)
    monkeypatch.setattr(bridge.requests, 'post', fake_post)
    assert bridge.create_or_get_project('http://ls', 'tk', 'my-project', '<View/>') == 9


def test_push_tasks(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen['url'] = url
        seen['tasks'] = json
        return FakeResponse(200, {"task_ids": [1, 2]})

    monkeypatch.setattr(bridge.requests, 'post', fake_post)
    res = bridge.push_tasks('http://ls', 'tk', 3, [{'data': {}}])
    assert res == {"task_ids": [1, 2]}
    assert seen['url'].endswith('/api/projects/3/import')


def test_fetch_export(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert 'exportType=JSON' in url
        return FakeResponse(200, [{"data": {}}])

    monkeypatch.setattr(bridge.requests, 'get', fake_get)
    assert bridge.fetch_export('http://ls', 'tk', 3) == [{"data": {}}]


def test_token_missing_raises():
    with pytest.raises(LsApiError, match="LS token"):
        bridge.push_tasks('http://ls', '', 3, [])


def test_ls_500_raises_with_summary(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(500, {"detail": "boom"})

    monkeypatch.setattr(bridge.requests, 'post', fake_post)
    with pytest.raises(LsApiError, match="boom"):
        bridge.push_tasks('http://ls', 'tk', 3, [{'data': {}}])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_labelstudio_bridge.py -v`
Expected: 新增 7 个测试 FAIL（`AttributeError: ... has no attribute 'ls_headers'` 等），原 7 个仍 PASS

- [ ] **Step 3: 追加实现（追加到 labelstudio_bridge.py 末尾）**

```python
class LsApiError(Exception):
    """LS REST 调用失败，message 直接面向用户展示（含 LS 响应摘要）"""


def ls_headers(ls_token):
    return {'Authorization': 'Token %s' % ls_token}


def _require_token(ls_token):
    if not ls_token:
        raise LsApiError('LS token 缺失：请传入 ls_token 或配置 LABELSTUDIO_TOKEN')


def _ls_error(resp, action):
    return LsApiError('LS %s 失败(%s): %s' % (action, resp.status_code, str(resp.text)[:200]))


def create_or_get_project(ls_url, ls_token, name, label_config):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.get(base + '/api/projects/', params={'name': name},
                        headers=ls_headers(ls_token), timeout=30)
    if resp.status_code >= 400:
        raise _ls_error(resp, '查询项目')
    results = resp.json().get('results') or []
    if results:
        return results[0]['id']  # 已存在同名项目，复用
    resp = requests.post(base + '/api/projects/', json={'name': name, 'label_config': label_config},
                         headers=ls_headers(ls_token), timeout=30)
    if resp.status_code >= 400:
        raise _ls_error(resp, '创建项目')
    return resp.json()['id']


def push_tasks(ls_url, ls_token, project_id, tasks):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.post(base + '/api/projects/%s/import' % project_id,
                         json=dedupe_tasks(tasks),
                         headers=ls_headers(ls_token), timeout=120)
    if resp.status_code >= 400:
        raise _ls_error(resp, '导入任务')
    return resp.json()


def fetch_export(ls_url, ls_token, project_id):
    _require_token(ls_token)
    base = ls_url.rstrip('/')
    resp = requests.get(base + '/api/projects/%s/export' % project_id,
                        params={'exportType': 'JSON'},
                        headers=ls_headers(ls_token), timeout=300)
    if resp.status_code >= 400:
        raise _ls_error(resp, '导出标注')
    return resp.json()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_labelstudio_bridge.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add myapp/utils/labelstudio_bridge.py tests/test_labelstudio_bridge.py
git commit -m "feat: LS REST 客户端（项目复用/任务导入/导出拉取，HTTP 全 mock 测试，S1）"
```

---

### Task 4: myapp API（push / import）+ 菜单入口

**Files:**
- Modify: `myapp/views/view_dataset.py`（`Dataset_ModelView_Api` 类内新增两个 API；顶部 import）
- Modify: `myapp/views/home.py`（L181-187 `label_platform` 菜单项）
- Modify: `install/docker/requirements.txt`（新增 requests 显式声明）

**Interfaces:**
- Consumes:
  - S4 计划：`load_dataframe(path, segment, rows) -> (df, bad_rows, truncated)`、`resolve_dataset_path(dataset) -> str`、`DatasetReadError`。
  - Task 2/3：`rows_to_ls_tasks / ls_export_to_records / create_or_get_project / push_tasks / fetch_export / LsApiError`（签名见前）。
- Produces:
  - `POST /dataset_modelview/api/push_to_labelstudio/<dataset_id>`，body `{"ls_url","ls_token","task_type","text_col","image_col","label_config"}`；成功 `{"status":0,"message":"success","result":{"project_id":int,"pushed":int}}`。
  - `POST /dataset_modelview/api/import_from_labelstudio`，body `{"ls_url","ls_token","ls_project_id","dataset_name","dataset_version"}`；成功 `{"status":0,"message":"success","result":{"file":str,"record_count":int}}`。
  - 菜单「标注平台」→ `/labelstudio/` 外链。

- [ ] **Step 1: view_dataset.py 顶部补 import**

在 S4 已加的 `from myapp.utils.dataset_profile import profile_dataframe` 之后加入：

```python
from myapp.utils.labelstudio_bridge import (
    LsApiError,
    create_or_get_project,
    fetch_export,
    ls_export_to_records,
    rows_to_ls_tasks,
)
```

- [ ] **Step 2: 新增 push_to_labelstudio（`Dataset_ModelView_Api` 类内）**

```python
    @expose_api(description="推送数据集到标注平台", url="/push_to_labelstudio/<dataset_id>", methods=["POST"])
    def push_to_labelstudio(self, dataset_id):
        args = request.get_json(silent=True) or {}
        ls_token = args.get('ls_token') or conf.get('LABELSTUDIO_TOKEN', '')
        task_type = args.get('task_type', '')
        dataset = db.session.query(Dataset).filter_by(id=dataset_id).first()
        if not dataset:
            return jsonify({'status': 1, 'result': {}, 'message': '数据集不存在'})
        if task_type not in ('text_classification', 'image_classification'):
            return jsonify({'status': 1, 'result': {}, 'message': 'task_type 仅支持 text_classification/image_classification'})
        try:
            path = resolve_dataset_path(dataset)
            df, _bad, _truncated = load_dataframe(path)
            tasks = rows_to_ls_tasks(df, task_type,
                                     text_col=args.get('text_col', ''),
                                     image_col=args.get('image_col', ''),
                                     dataset_name=dataset.name or str(dataset.id))
            project_id = create_or_get_project(args.get('ls_url', ''), ls_token,
                                               'cube-studio-%s-%s' % (dataset.name, dataset.version or 'latest'),
                                               args.get('label_config', ''))
            res = push_tasks(args.get('ls_url', ''), ls_token, project_id, tasks)
            pushed = len(res.get('task_ids', [])) if isinstance(res, dict) else len(tasks)
            return jsonify({'status': 0, 'message': 'success',
                            'result': {'project_id': project_id, 'pushed': pushed}})
        except DatasetReadError as e:
            return jsonify({'status': 1, 'result': {}, 'message': str(e)})
        except (LsApiError, ValueError) as e:
            return jsonify({'status': 1, 'result': {}, 'message': str(e)})
```

确认文件已有 `conf`（view_dataset.py 模块级已有 `conf = app.config` 惯例；若无则在 import 区加 `from myapp import app` 并用 `app.config`，二选一保持该文件既有风格）。

- [ ] **Step 3: 新增 import_from_labelstudio（紧跟 push 方法之后）**

```python
    @expose_api(description="从标注平台回存标注结果为数据集", url="/import_from_labelstudio", methods=["POST"])
    def import_from_labelstudio(self):
        args = request.get_json(silent=True) or {}
        ls_token = args.get('ls_token') or conf.get('LABELSTUDIO_TOKEN', '')
        project_id = args.get('ls_project_id')
        dataset_name = args.get('dataset_name', '')
        dataset_version = args.get('dataset_version', '')
        if not project_id or not dataset_name or not dataset_version:
            return jsonify({'status': 1, 'result': {}, 'message': 'ls_project_id/dataset_name/dataset_version 均必填'})
        exists = db.session.query(Dataset).filter_by(name=dataset_name, version=dataset_version).first()
        if exists:
            return jsonify({'status': 1, 'result': {}, 'message': '同名同版本数据集已存在，请更换 dataset_version'})
        try:
            export = fetch_export(args.get('ls_url', ''), ls_token, int(project_id))
        except LsApiError as e:
            return jsonify({'status': 1, 'result': {}, 'message': str(e)})
        records = ls_export_to_records(export)
        if not records:
            return jsonify({'status': 1, 'result': {}, 'message': 'LS 项目无任务数据'})
        remote_dir = os.path.join('/data/k8s/kubeflow/global/', 'dataset/%s/%s/' % (dataset_name, dataset_version))
        os.makedirs(remote_dir, exist_ok=True)
        filename = 'labelstudio_%s.jsonl' % project_id
        file_path = os.path.join(remote_dir, filename)
        if os.path.exists(file_path):
            filename = 'labelstudio_%s_%s.jsonl' % (project_id, time.strftime('%Y%m%d%H%M%S'))
            file_path = os.path.join(remote_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        dataset = Dataset(name=dataset_name, label=dataset_name,
                          version=dataset_version, file_type='jsonl',
                          path=file_path,
                          describe='来自标注平台项目 %s 的回存' % project_id)
        db.session.add(dataset)
        db.session.commit()
        return jsonify({'status': 0, 'message': 'success',
                        'result': {'file': file_path, 'record_count': len(records)}})
```

确认文件顶部 import 已具备：`os / time / json`（该文件现有 import 已含 os/json；`time` 若缺则补 `import time`）。

- [ ] **Step 4: 启用「标注平台」菜单**

在 `myapp/views/home.py` 中定位 `label_platform` 菜单项（L181-187，`"title": __('标注平台')`），将其改为：

```python
                            {
                                "name": 'label_platform',
                                "title": __('标注平台'),
                                "icon": '<svg t="1658320508784" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="3263" width="200" height="200"><path d="M875.65 912h-380a36 36 0 0 1 0-72h380a36 36 0 1 1 0 72zM812.26 284.82L285.39 811.69l-88.11 15.1L212 738l526.72-526.72 73.54 73.54m90.51-11.31L750 120.77a16 16 0 0 0-22.62 0L152.5 695.68a34.11 34.11 0 0 0-9.5 18.56l-25.95 156.23a32 32 0 0 0 37 36.78l155.38-26.62a34.2 34.2 0 0 0 18.38-9.52l575-575a16 16 0 0 0 0-22.63z" p-id="3264"></path></svg>',
                                "menu_type": "out_link",
                                "url": "/labelstudio/"
                            },
```

变更点：删除 `"menu_type": "api"`、`"disable": True`、原 `"url": "/metadata_table_modelview/api/"`；icon svg 逐字保留。`out_link` 类型为项目既有用法（home.py `ALL_LINKS` 处先例）。

- [ ] **Step 5: requirements 恢复 requests 显式声明**

在 `install/docker/requirements.txt` 的 `kubernetes==28.1.0` 行之后加入：

```
requests==2.31.0            # LabelStudio 桥接 REST 客户端（kubernetes 客户端传递依赖，显式声明）
```

- [ ] **Step 6: 全量测试回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（含 S4/S1 已有测试）

- [ ] **Step 7: Commit**

```bash
git add myapp/views/view_dataset.py myapp/views/home.py install/docker/requirements.txt
git commit -m "feat: 数据集↔LabelStudio 推送/回存 API 与标注平台菜单入口（S1）"
```

---

### Task 5: 手工验收清单（部署环境执行，不阻塞合并）

**Files:**
- 无代码改动。

- [ ] **Step 1:** `kubectl apply -f install/kubernetes/labelstudio/` 后确认 Pod 就绪、`/labelstudio/` 路由可访问（未登录平台时被重定向登录）。
- [ ] **Step 2:** LS 内注册账号，创建 API token；通过 body 传 `ls_token` 调 `POST /dataset_modelview/api/push_to_labelstudio/<id>` 推送文本分类数据集，确认 LS 项目生成任务且文本/meta 正确。
- [ ] **Step 3:** 重复调用同一数据集 push，确认幂等（`pushed` 不因重复键增长；LS 内无重复任务）。
- [ ] **Step 4:** 在 LS 完成若干标注后调 `POST /dataset_modelview/api/import_from_labelstudio`，确认 jsonl 落盘、Dataset 登记、无标注任务 `label` 为空。
- [ ] **Step 5:** 异常分支：错 token → `status:1` 含 LS 响应摘要；`task_type: 'ner'` → 明确拒绝；同名同版本回存 → 明确拒绝。
- [ ] **Step 6:** 确认平台菜单出现「标注平台」且点击跳转 `/labelstudio/`。
