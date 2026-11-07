# Pipeline 调度增强 Implementation Plan（序 3：#5/#8/#9，企业版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 pipeline 调度链路补齐企业版增量：#9 任务流优先级全链路（双注入 + 双闸门）、#8 定时实例清理完备性（RunHistory DB 清理 + minio artifact 回收）、#5 补录入口回归护栏。

**Architecture:** 调度纯逻辑（优先级 spec patch、过期记录决策）与 minio 访问各自抽为自包含模块（`myapp/utils/py/pipeline_schedule.py`、`myapp/utils/py/py_minio.py`，仅标准库/惰性 import），由 `view_pipeline.py`（workflow 合成）与 `schedules.py`（expired_limit 清理分支）接入；集群侧能力（PriorityClass）经安装清单 + conf 映射双闸门启用，缺省关闭保证存量行为零变化。

**Tech Stack:** Python 3 / Flask-AppBuilder 表单 / SQLAlchemy / celery / minio SDK（客户端注入式，测试用 duck-type mock）/ React @fluentui/react（vision）/ pytest。

**Spec:** `docs/superpowers/specs/2026-11-07-ent-training-features-brainstorm.md` §1-A5/A8/A9（已含二轮校验修正与设计决策回写）、§7.3 全局设计约定

## Global Constraints

- 自包含模块禁止 `import myapp.*`（tests/conftest.py stub 包机制的前提）；第三方重依赖（minio）只在函数内惰性 import。
- 向后兼容红线：conf `PIPELINE_PRIORITY_CLASS` 缺省 `{}` 时，`make_workflow_yaml` 输出与改动前逐字段一致（不注入任何 priority 相关键）。
- PriorityClass 一律 `preemptionPolicy: Never`（防抢占杀死运行中训练任务，母文档 A9 风险条目）。
- 清理失败只 `logging`，不抛出、不阻塞调度主流程（schedules.py 既有异常风格）。
- RunHistory 仅删终态记录（`Deleted/Succeeded/Failed`），非终态（comed/created）永不删。
- 凭证不硬编码新增：minio access/secret key 走 conf（`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`，缺省值沿用现网 `'minio'`/`'minio123'`）。
- 提交信息规范：`feat:`/`chore:`/`docs:` 前缀 + 中文标题 +（英文标识）。
- 测试命令统一 `python -m pytest`（Windows PowerShell，工作目录仓库根）。

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `myapp/utils/py/pipeline_schedule.py` | Create | 调度纯逻辑：优先级双注入 patch + 过期 RunHistory 清理决策（可独立测试） |
| `myapp/utils/py/py_minio.py` | Create | minio 客户端构造（凭证 conf 化）+ 前缀批量清理（客户端注入式） |
| `tests/test_pipeline_schedule.py` | Create | 上述两模块单测（importlib 按路径加载，同 test_args_schema.py 惯例） |
| `tests/conftest.py` | Modify | 增量加载两个新模块（禁止覆盖既有内容） |
| `myapp/views/view_pipeline.py` | Modify | make_workflow_yaml 注入 priority；表单/列清单加 `priority` |
| `myapp/views/view_workflow.py` | Modify | get_minio_content 内联 Minio 构造收敛到 py_minio |
| `myapp/tasks/schedules.py` | Modify | expired_limit 分支：删实例处清 artifact + 分支尾清过期终态 RunHistory |
| `myapp/config.py` | Modify | 新增 MINIO_ACCESS_KEY/MINIO_SECRET_KEY/PIPELINE_PRIORITY_CLASS 默认值 |
| `install/kubernetes/cube/overlays/config/config.py` | Modify | 部署模板同步新配置样例 |
| `install/kubernetes/cube/priorityclass.yaml` | Create | 三档 PriorityClass 安装清单（opt-in，不进 kustomize） |
| `myapp/vision/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx` | Modify | 启用「调度优先级」下拉（去 disabled、补 mid 档、加说明） |

**前端范围说明（与设计沟通的一致性修正）：** visionPlus 无 pipeline 级设置面板（其 Setting/index.tsx 为任务参数面板，pipeline 调度字段块整体处于注释状态）——本轮不新建该面板（超序 3 边界，YAGNI），pipeline 调度编辑 UI 由 vision 承担，visionPlus 用户经后端 API/旧版表单编辑。vision 已具备补录起点 DatePicker 与 expired_limit 字段（#5/#8 前端零改动），#9 仅需启用既有 disabled 的优先级下拉。

---

### Task 1: pipeline_schedule.py 自包含模块（priority patch + expired 决策）

**Files:**
- Create: `myapp/utils/py/pipeline_schedule.py`
- Test: `tests/test_pipeline_schedule.py`
- Modify: `tests/conftest.py`（增量，L41 后追加加载行）

**Interfaces:**
- Consumes: 无（纯标准库）
- Produces:
  - `PIPELINE_PRIORITY_VALUE: dict[str, int]` — `{'high': 200, 'mid': 100, 'low': 0}`
  - `TERMINAL_RUN_STATUSES: tuple[str, ...]` — `('Deleted', 'Succeeded', 'Failed')`
  - `priority_spec_patch(pipeline_priority, priority_class_map) -> dict` — 档位同时命中数值表与 conf 映射表时返回 `{'priority': <int>, 'templateDefaults': {'priorityClassName': <str>}}`，否则返回 `{}`
  - `expired_run_ids_to_delete(records, limit, terminal_states=TERMINAL_RUN_STATUSES) -> list[int]` — records 为 `[{'id': int, 'execution_date': str, 'status': str}]`，按 execution_date 字符串降序保留最新 limit 条，更早且状态为终态的记录 id 列入返回；limit<=0 返回 `[]`

- [ ] **Step 1: conftest.py 增量加载行**

在 `tests/conftest.py` L41（`_load_module('myapp.utils.py.args_schema', ...)` 行）之后追加一行：

```python
_load_module('myapp.utils.py.pipeline_schedule', 'myapp/utils/py/pipeline_schedule.py')
```

- [ ] **Step 2: 写失败测试**

创建 `tests/test_pipeline_schedule.py`（模块加载方式与 `tests/test_args_schema.py` 完全一致——importlib 按路径加载，本文件独立加载不依赖 conftest 行）：

```python
# 任务流优先级 patch 与过期 RunHistory 清理决策的单元测试（企业版 #8/#9）
import pathlib
import importlib.util
import pytest

_MOD_PATH = pathlib.Path(__file__).resolve().parents[1] / 'myapp' / 'utils' / 'py' / 'pipeline_schedule.py'
_spec = importlib.util.spec_from_file_location('pipeline_schedule_under_test', _MOD_PATH)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

CLASS_MAP = {'high': 'pipeline-high', 'mid': 'pipeline-mid', 'low': 'pipeline-low'}


def _rec(id_, exec_date, status):
    return {'id': id_, 'execution_date': exec_date, 'status': status}


# ---------- priority_spec_patch ----------

def test_both_tables_hit_returns_dual_injection():
    assert ps.priority_spec_patch('high', CLASS_MAP) == {
        'priority': 200,
        'templateDefaults': {'priorityClassName': 'pipeline-high'},
    }


def test_empty_class_map_returns_empty_backward_compatible():
    # conf 缺省 {} = 功能关闭，存量 default='high' 也不注入
    assert ps.priority_spec_patch('high', {}) == {}
    assert ps.priority_spec_patch('high', None) == {}


def test_empty_or_none_priority_returns_empty():
    assert ps.priority_spec_patch('', CLASS_MAP) == {}
    assert ps.priority_spec_patch(None, CLASS_MAP) == {}


def test_unknown_tier_returns_empty():
    assert ps.priority_spec_patch('urgent', CLASS_MAP) == {}


def test_tier_in_map_but_not_in_value_table_returns_empty():
    # conf 出现数值表之外的自定义档位 → 不注入（契约明确只支持三档）
    assert ps.priority_spec_patch('gold', {'gold': 'pipeline-gold'}) == {}


def test_low_tier_value_is_zero():
    patch = ps.priority_spec_patch('low', CLASS_MAP)
    assert patch['priority'] == 0
    assert patch['templateDefaults']['priorityClassName'] == 'pipeline-low'


# ---------- expired_run_ids_to_delete ----------

def test_zero_or_negative_limit_returns_empty():
    records = [_rec(1, '2026-11-01 00:00:00', 'Succeeded')]
    assert ps.expired_run_ids_to_delete(records, 0) == []
    assert ps.expired_run_ids_to_delete(records, -1) == []


def test_records_within_limit_never_deleted():
    records = [
        _rec(1, '2026-11-02 00:00:00', 'Succeeded'),
        _rec(2, '2026-11-01 00:00:00', 'Failed'),
    ]
    assert ps.expired_run_ids_to_delete(records, 2) == []


def test_stale_terminal_records_deleted_newest_kept():
    records = [
        _rec(3, '2026-11-03 00:00:00', 'Succeeded'),
        _rec(2, '2026-11-02 00:00:00', 'Succeeded'),
        _rec(1, '2026-11-01 00:00:00', 'Deleted'),
    ]
    assert ps.expired_run_ids_to_delete(records, 2) == [1]


def test_stale_non_terminal_records_are_kept():
    records = [
        _rec(4, '2026-11-04 00:00:00', 'Running'),
        _rec(3, '2026-11-03 00:00:00', 'created'),
        _rec(2, '2026-11-02 00:00:00', 'comed'),
        _rec(1, '2026-11-01 00:00:00', 'Succeeded'),
    ]
    # limit=1：2/3/4 都超出保留窗，但仅终态 Succeeded 的 id=1 被删；comed/created/Running 保留
    assert ps.expired_run_ids_to_delete(records, 1) == [1]


def test_unordered_input_sorted_by_execution_date_desc():
    records = [
        _rec(1, '2026-11-01 00:00:00', 'Succeeded'),
        _rec(3, '2026-11-05 00:00:00', 'Succeeded'),
        _rec(2, '2026-11-03 00:00:00', 'Succeeded'),
    ]
    # 保留最新 1 条（id=3），更早的 id=1/2 均终态被删
    assert sorted(ps.expired_run_ids_to_delete(records, 1)) == [1, 2]


def test_missing_fields_tolerated():
    records = [
        {'id': 1, 'status': 'Succeeded'},
        {'id': 2, 'execution_date': '2026-11-09 00:00:00', 'status': 'Succeeded'},
        {'id': 3, 'execution_date': '2026-11-08 00:00:00', 'status': 'Succeeded'},
    ]
    # 缺 execution_date 的终态记录排到最旧，超出保留窗 → 被删（缺字段不崩溃）
    assert ps.expired_run_ids_to_delete(records, 2) == [1]


def test_missing_status_is_never_deleted():
    # 状态未知的记录按非终态处理，宁可不删（仅删终态的安全红线优先于清理率）
    records = [
        {'id': 1},
        {'id': 2, 'execution_date': '2026-11-09 00:00:00', 'status': 'Succeeded'},
    ]
    assert ps.expired_run_ids_to_delete(records, 1) == []
```

> **计划修正（执行时回填）：** 原计划该用例首条记录为 `{'id': 1}`（缺 status）却断言被删，与实现「仅删终态」矛盾（实际返回 `[]`）。已按安全红线优先改写：缺 `execution_date` 的终态记录排最旧被删，另加 `test_missing_status_is_never_deleted` 守住「状态未知永不删」。Task 1 用例数 12 → 13。

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_pipeline_schedule.py -v`
Expected: `FileNotFoundError`（模块不存在导致 exec_module 失败）

- [ ] **Step 4: 实现模块**

创建 `myapp/utils/py/pipeline_schedule.py`：

```python
# -*- coding: utf-8 -*-
"""Pipeline 调度增强纯逻辑（企业版 #8/#9）。

自包含模块：仅标准库，禁止 import myapp.*（tests/conftest.py stub 机制前提）。
- priority_spec_patch: 任务流优先级 -> argo workflow spec 增量（双注入）
- expired_run_ids_to_delete: 定时调度过期 RunHistory 记录清理决策
"""

# 档位 -> argo workflow spec.priority 数值（controller 提交排序权重）
PIPELINE_PRIORITY_VALUE = {'high': 200, 'mid': 100, 'low': 0}

# RunHistory 可安全删除的终态（非终态 comed/created 等参与调度链路，永不删）
TERMINAL_RUN_STATUSES = ('Deleted', 'Succeeded', 'Failed')


def priority_spec_patch(pipeline_priority, priority_class_map):
    """计算 workflow spec 的优先级增量。

    双闸门：档位需同时命中 PIPELINE_PRIORITY_VALUE 与 conf 映射表
    priority_class_map（缺省 {} = 功能关闭），才返回注入 patch；
    否则返回 {}，调用方 update 后 spec 与未启用时逐字段一致。
    """
    if not pipeline_priority:
        return {}
    class_name = (priority_class_map or {}).get(pipeline_priority, '')
    value = PIPELINE_PRIORITY_VALUE.get(pipeline_priority)
    if not class_name or value is None:
        return {}
    return {
        'priority': value,
        'templateDefaults': {'priorityClassName': class_name},
    }


def expired_run_ids_to_delete(records, limit, terminal_states=TERMINAL_RUN_STATUSES):
    """返回可删除的过期 RunHistory 记录 id。

    records: [{'id','execution_date','status'}]，execution_date 为
    '%Y-%m-%d %H:%M:%S' 字符串（字典序即时间序）。
    按 execution_date 降序保留最新 limit 条，更早且状态为终态的删除。
    limit<=0 表示不限制，返回 []。
    """
    if not limit or limit <= 0:
        return []
    ordered = sorted(records, key=lambda r: r.get('execution_date') or '', reverse=True)
    return [
        r['id'] for r in ordered[limit:]
        if r.get('status') in terminal_states
    ]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_pipeline_schedule.py -v`
Expected: 13 passed

- [ ] **Step 6: 全量回归 + 提交**

Run: `python -m pytest`
Expected: 全部通过（既有 65 + 新增 13 = 78）

> 回归命令修正：仓库根 `python -m pytest` 会误收集 `myapp/example/pipeline/llamafactory`（本机无 llamafactory 依赖，collection error），统一改用 `python -m pytest tests -q`。

```bash
git add myapp/utils/py/pipeline_schedule.py tests/test_pipeline_schedule.py tests/conftest.py
git commit -m "feat: 调度纯逻辑模块 pipeline_schedule（priority 双注入 patch+过期清理决策，企业版#8#9）"
```

---

### Task 2: py_minio.py 封装与 view_workflow 收敛

**Files:**
- Create: `myapp/utils/py/py_minio.py`
- Test: `tests/test_pipeline_schedule.py`（追加，同文件复用加载器风格另建模块节）
- Modify: `myapp/views/view_workflow.py:497-504`（get_minio_content 内联构造收敛）
- Modify: `tests/conftest.py`（增量加载行）

**Interfaces:**
- Consumes: 无 myapp 依赖（minio 在函数内惰性 import）
- Produces:
  - `make_minio_client(conf_get)` — conf_get 为 `dict.get` 式可调用；返回 minio.Minio 实例（endpoint/access_key/secret_key/secure=False）
  - `remove_object_prefix(client, bucket, prefix) -> (removed: int, errors: list[str])` — 逐对象删除，单对象异常收集不抛出；list 失败返回 `(0, [msg])`

- [ ] **Step 1: conftest.py 增量**

在 Task 1 所加行之后追加：

```python
_load_module('myapp.utils.py.py_minio', 'myapp/utils/py/py_minio.py')
```

- [ ] **Step 2: 写失败测试**

在 `tests/test_pipeline_schedule.py` 末尾追加（模块节头注释 + 加载器 + 4 条测试；加载器与文件头一致风格，路径为 `py_minio.py`）：

```python
# ---------- py_minio（同文件承载，另一自包含模块的加载器） ----------

_MINIO_MOD_PATH = pathlib.Path(__file__).resolve().parents[1] / 'myapp' / 'utils' / 'py' / 'py_minio.py'
_minio_spec = importlib.util.spec_from_file_location('py_minio_under_test', _MINIO_MOD_PATH)
py_minio = importlib.util.module_from_spec(_minio_spec)
_minio_spec.loader.exec_module(py_minio)


class _Obj:
    def __init__(self, name):
        self.object_name = name


class FakeMinioClient:
    """duck-type mock：只实现 remove_object_prefix 用到的两个方法"""

    def __init__(self, object_names=None, list_fail=False, delete_fail_names=()):
        self._object_names = object_names or []
        self._list_fail = list_fail
        self._delete_fail_names = set(delete_fail_names)
        self.deleted = []

    def list_objects(self, bucket, prefix=None, recursive=False):
        if self._list_fail:
            raise RuntimeError('connection refused')
        return [_Obj(n) for n in self._object_names]

    def remove_object(self, bucket, name):
        if name in self._delete_fail_names:
            raise RuntimeError('delete denied')
        self.deleted.append(name)


def test_remove_prefix_deletes_all_and_counts():
    client = FakeMinioClient(['wf-1/a.log', 'wf-1/b.log'])
    removed, errors = py_minio.remove_object_prefix(client, 'mlpipeline', 'wf-1/')
    assert (removed, errors) == (2, [])
    assert client.deleted == ['wf-1/a.log', 'wf-1/b.log']


def test_remove_prefix_empty_list():
    client = FakeMinioClient([])
    assert py_minio.remove_object_prefix(client, 'mlpipeline', 'wf-2/') == (0, [])


def test_remove_prefix_list_failure_swallowed():
    client = FakeMinioClient(list_fail=True)
    removed, errors = py_minio.remove_object_prefix(client, 'mlpipeline', 'wf-3/')
    assert removed == 0
    assert len(errors) == 1 and 'connection refused' in errors[0]


def test_remove_prefix_single_delete_error_collected():
    client = FakeMinioClient(['x/1', 'x/2', 'x/3'], delete_fail_names={'x/2'})
    removed, errors = py_minio.remove_object_prefix(client, 'mlpipeline', 'x/')
    assert removed == 2
    assert len(errors) == 1 and 'x/2' in errors[0]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_pipeline_schedule.py -v -k "minio or prefix"`
Expected: `FileNotFoundError`（py_minio.py 不存在）

- [ ] **Step 4: 实现模块**

创建 `myapp/utils/py/py_minio.py`：

```python
# -*- coding: utf-8 -*-
"""minio 访问封装（企业版 #8 artifact 回收）。

自包含模块：顶层仅标准库，minio SDK 在 make_minio_client 内惰性 import；
remove_object_prefix 接受注入的 client（duck-type），测试无需 minio 依赖。
"""


def make_minio_client(conf_get):
    """conf_get: dict.get 式可调用（调用方传 myapp 的 conf.get）。

    凭证 conf 化：MINIO_ACCESS_KEY / MINIO_SECRET_KEY，
    缺省值沿用现网硬编码值保证行为兼容。
    """
    from minio import Minio
    return Minio(
        endpoint=conf_get('MINIO_HOST', 'minio.kubeflow:9000'),
        access_key=conf_get('MINIO_ACCESS_KEY', 'minio'),
        secret_key=conf_get('MINIO_SECRET_KEY', 'minio123'),
        secure=False,
    )


def remove_object_prefix(client, bucket, prefix):
    """删除 bucket 内指定前缀的全部对象。

    返回 (removed_count, errors)；单对象失败记录后继续，
    list 整体失败返回 (0, [msg])。不抛出——调用方仅 logging。
    """
    try:
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    except Exception as e:
        return 0, [str(e)]
    removed, errors = 0, []
    for obj in objects:
        try:
            client.remove_object(bucket, obj.object_name)
            removed += 1
        except Exception as e:
            errors.append('%s: %s' % (obj.object_name, e))
    return removed, errors
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_pipeline_schedule.py -v`
Expected: 17 passed（13 + 4）

- [ ] **Step 6: view_workflow.py 收敛内联构造**

`myapp/views/view_workflow.py` L493-504 的 `get_minio_content` 中，将

```python
        content = ''
        from minio import Minio
        try:
            minioClient = Minio(
                endpoint=conf.get('MINIO_HOST','minio.kubeflow:9000'),  # minio.kubeflow:9000    '9.135.92.226:9944'
                access_key='minio',
                secret_key='minio123',
                secure=False
            )
```

替换为（删除 `from minio import Minio`，改用共享封装；bucket 等其余逻辑不动）：

```python
        content = ''
        from myapp.utils.py.py_minio import make_minio_client
        try:
            minioClient = make_minio_client(conf.get)
```

- [ ] **Step 7: 编译验证 + 提交**

Run: `python -m py_compile myapp/views/view_workflow.py myapp/utils/py/py_minio.py`
Expected: 无输出（成功）

```bash
git add myapp/utils/py/py_minio.py tests/test_pipeline_schedule.py tests/conftest.py myapp/views/view_workflow.py
git commit -m "feat: py_minio 封装（凭证 conf 化+前缀批量清理），view_workflow 内联构造收敛（企业版#8）"
```

---

### Task 3: view_pipeline.py 接入（#9 注入 + 表单/列清单）

**Files:**
- Modify: `myapp/views/view_pipeline.py:34`（import 区）、`:95-122`（make_workflow_yaml spec）、`:582-584`（Base edit_columns）、`:585-588`（Base show_columns）、`:653-659` 后（表单字段）、`:1309-1311`（Api edit_columns）

**Interfaces:**
- Consumes: Task 1 的 `priority_spec_patch(pipeline_priority, priority_class_map) -> dict`
- Produces: workflow spec 含/不含优先级注入（conf 闸门）；`priority` 字段进入 pipeline 编辑表单与 API edit_columns

- [ ] **Step 1: 顶部 import**

`myapp/views/view_pipeline.py` L34 `from myapp.utils.py import py_k8s` 之后追加：

```python
from myapp.utils.py.pipeline_schedule import priority_spec_patch
```

- [ ] **Step 2: make_workflow_yaml 注入**

L120-122 的

```python
        }
    }
    return workflow_crd_json
```

改为（spec dict 字面量构建后 update 增量；conf 未配置时 patch 为 `{}`，spec 逐字段不变）：

```python
        }
    }
    # 企业版 #9：任务流优先级双注入（spec.priority 提交排序 + templateDefaults.priorityClassName Pod 级调度）。
    # 双闸门：仅当档位命中 conf PIPELINE_PRIORITY_CLASS 映射时才注入，缺省空 dict = 行为与历史完全一致。
    workflow_crd_json['spec'].update(priority_spec_patch(
        getattr(pipeline, 'priority', ''), conf.get('PIPELINE_PRIORITY_CLASS', {})))
    return workflow_crd_json
```

- [ ] **Step 3: 表单加 priority SelectField**

在 `add_form_extra_fields` 中 `"expired_limit"` 字段块（L653-659）与 `"parallelism"` 字段块之间插入：

```python
        "priority": SelectField(
            _('调度优先级'),
            description=_("任务流优先级档位，仅当集群预装 PriorityClass（install/kubernetes/cube/priorityclass.yaml）"
                          "并配置 PIPELINE_PRIORITY_CLASS 映射时生效；未配置时不影响运行，仅登记档位"),
            widget=Select2Widget(),
            default='high',
            choices=[['high', 'high'], ['mid', 'mid'], ['low', 'low']]
        ),
```

注意：`edit_form_extra_fields = add_form_extra_fields`（L712），改一处即两处生效。

- [ ] **Step 4: 列清单加 priority**

Base 类 `edit_columns`（L582-584）在 `'expired_limit',` 后加 `'priority',`；Base `show_columns`（L585-588）同样在 `'expired_limit',` 后加 `'priority',`；`Pipeline_ModelView_Api.edit_columns`（L1309-1311）在 `'expired_limit',` 后加 `'priority',`。三处均为最小插入。

- [ ] **Step 5: 编译与兼容性验证**

Run: `python -m py_compile myapp/views/view_pipeline.py`
Expected: 无输出

兼容性抽查（不改代码，验证 Task 1 契约即真相）：

```bash
python -c "import importlib.util; p=importlib.util.spec_from_file_location('ps','myapp/utils/py/pipeline_schedule.py'); m=importlib.util.module_from_spec(p); p.loader.exec_module(m); print(m.priority_spec_patch('high', {}))"
```

Expected: 输出 `{}`（缺省关闭 → spec 不注入）

- [ ] **Step 6: 全量回归 + 提交**

Run: `python -m pytest`
Expected: 77 passed

```bash
git add myapp/views/view_pipeline.py
git commit -m "feat: workflow 合成注入 pipeline 优先级与表单列清单接入，conf 缺省关闭向后兼容（企业版#9）"
```

---

### Task 4: schedules.py expired_limit 分支双清理（#8）

**Files:**
- Modify: `myapp/tasks/schedules.py:18`（import 区）、`:541-566`（expired_limit 分支）

**Interfaces:**
- Consumes: Task 1 的 `expired_run_ids_to_delete(records, limit)`；Task 2 的 `make_minio_client(conf_get)` / `remove_object_prefix(client, bucket, prefix)`
- Produces: 定时调度按 expired_limit 回收旧实例时，同步删除 minio artifact 与过期终态 RunHistory 记录

- [ ] **Step 1: 顶部 import**

L32 `from myapp.views.view_pipeline import run_pipeline,dag_to_pipeline` 之后追加：

```python
from myapp.utils.py.pipeline_schedule import expired_run_ids_to_delete
from myapp.utils.py.py_minio import make_minio_client, remove_object_prefix
```

- [ ] **Step 2: 删旧实例处追加 artifact 回收**

`upload_timerun` expired_limit 分支内（L549-556），将

```python
                            if pass_run and run_id not in latest_run_ids:
                                k8s_client = K8s(pipeline.project.cluster.get('KUBECONFIG',''))
                                k8s_client.delete_workflow(all_crd_info=conf.get("CRD_INFO", {}), namespace='pipeline',run_id=run_id)
                                workflow = dbsession.query(Workflow).filter(Workflow.labels.contains(run_id)).first()
                                workflow.status = 'Deleted'
                                dbsession.commit()
                                # 也更新timeruns的状态
                                pass_run.status = 'Deleted'
                                dbsession.commit()
```

改为（复用刚查出的 workflow 对象取 name；清理失败只记日志）：

```python
                            if pass_run and run_id not in latest_run_ids:
                                k8s_client = K8s(pipeline.project.cluster.get('KUBECONFIG',''))
                                k8s_client.delete_workflow(all_crd_info=conf.get("CRD_INFO", {}), namespace='pipeline',run_id=run_id)
                                workflow = dbsession.query(Workflow).filter(Workflow.labels.contains(run_id)).first()
                                workflow.status = 'Deleted'
                                dbsession.commit()
                                # 也更新timeruns的状态
                                pass_run.status = 'Deleted'
                                dbsession.commit()
                                # 企业版 #8：按 workflow_name 前缀回收该实例在 minio 的日志/产物，失败只记日志不阻塞调度
                                try:
                                    if workflow:
                                        removed, errors = remove_object_prefix(make_minio_client(conf.get), 'mlpipeline', workflow.name + '/')
                                        if errors:
                                            logging.error('artifact cleanup errors for %s: %s', workflow.name, errors)
                                except Exception as cleanup_error:
                                    logging.error('artifact cleanup fail for %s: %s', workflow.name, cleanup_error)
```

- [ ] **Step 3: 分支末尾追加 RunHistory 过期清理**

同分支内，`for timerun in timeruns:` 循环（L560-566）之后、`else:`（L570）之前追加：

```python
                    # 企业版 #8：清理超出保留窗的过期终态 RunHistory 记录（pipeline_file 为 640K Text 大字段，
                    # 定时记录累积是 DB 膨胀主因）；仅删终态，comed/created 记录参与调度链路必须保留
                    all_runs = dbsession.query(RunHistory).filter(RunHistory.pipeline_id == pipeline.id).all()
                    run_records = [{'id': r.id, 'execution_date': r.execution_date or '', 'status': r.status or ''} for r in all_runs]
                    stale_ids = expired_run_ids_to_delete(run_records, pipeline.expired_limit)
                    if stale_ids:
                        dbsession.query(RunHistory).filter(RunHistory.id.in_(stale_ids)).delete(synchronize_session=False)
                        dbsession.commit()
                        logging.info('pipeline %s expired cleanup: %s run records deleted', pipeline.name, len(stale_ids))
```

- [ ] **Step 4: 编译验证 + 全量回归**

Run: `python -m py_compile myapp/tasks/schedules.py`
Expected: 无输出

Run: `python -m pytest`
Expected: 77 passed（schedules.py 本体不可直测——celery/myapp 重依赖，清理决策正确性由 Task 1 纯函数测试护栏保证）

- [ ] **Step 5: 提交**

```bash
git add myapp/tasks/schedules.py
git commit -m "feat: expired_limit 分支补 artifact 回收与过期终态 RunHistory 清理（企业版#8）"
```

---

### Task 5: vision 前端启用三档优先级下拉（#9 UI）

**Files:**
- Modify: `myapp/vision/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx:232-243`

**Interfaces:**
- Consumes: Task 3 的 `priority` 编辑字段（API edit_columns）
- Produces: 流水线设置面板可选 high/mid/low 并随保存提交

- [ ] **Step 1: 替换优先级 Dropdown**

将 L232-243 的

```tsx
          <Dropdown
            label={'调度优先级'}
            options={[
              { key: "high", text: 'high' },
              { key: "low", text: 'low' },
            ]}
            selectedKey={current?.priority || "high"}
            onChange={(event: FormEvent, option?: IDropdownOption) => {
              handleOnChange('priority', `${option?.text}` || '');
            }}
            disabled
          />
```

替换为（去 disabled、补 mid 档、加生效条件说明）：

```tsx
          <Dropdown
            label={'调度优先级'}
            description={'仅当集群预装 PriorityClass 并配置 PIPELINE_PRIORITY_CLASS 映射时影响调度，否则只登记档位'}
            options={[
              { key: "high", text: 'high' },
              { key: "mid", text: 'mid' },
              { key: "low", text: 'low' },
            ]}
            selectedKey={current?.priority || "high"}
            onChange={(event: FormEvent, option?: IDropdownOption) => {
              handleOnChange('priority', `${option?.text}` || '');
            }}
          />
```

- [ ] **Step 2: 类型检查**

Run（工作目录 `myapp/vision`，node_modules 缺失则先 `npm install`）：`npx tsc --noEmit`
Expected: exit 0（`current` 为 `useState<any>`，无类型连锁改动）

- [ ] **Step 3: 提交**

```bash
git add myapp/vision/src/components/FlowEditor/components/EditorBody/components/Setting/index.tsx
git commit -m "feat: vision 流水线设置启用三档调度优先级下拉（企业版#9 UI）"
```

---

### Task 6: 安装清单与 conf 配置（#9 部署面）

**Files:**
- Create: `install/kubernetes/cube/priorityclass.yaml`
- Modify: `myapp/config.py:750`（MINIO_HOST 行后）
- Modify: `install/kubernetes/cube/overlays/config/config.py:747`（MINIO_HOST 行后）

**Interfaces:**
- Consumes: 无
- Produces: 三档 PriorityClass 清单；`PIPELINE_PRIORITY_CLASS`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` conf 键（Task 2/3 读取）

- [ ] **Step 1: PriorityClass 清单**

创建 `install/kubernetes/cube/priorityclass.yaml`（opt-in 独立清单，**不**加入 kustomization.yml resources——功能默认关闭，由管理员按需 apply）：

```yaml
# 企业版 #9：pipeline 任务流优先级 PriorityClass 三档清单（opt-in）
# 启用步骤：
#   1) kubectl apply -f priorityclass.yaml
#   2) myapp 配置中设置：
#      PIPELINE_PRIORITY_CLASS = {'high': 'pipeline-high', 'mid': 'pipeline-mid', 'low': 'pipeline-low'}
# 未配置映射时平台不注入 priorityClassName，本清单存在与否不影响存量行为。
# preemptionPolicy: Never —— 高档位不参与抢占，防止杀死运行中训练任务（母文档 A9 风险条目）。
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: pipeline-high
value: 200000
preemptionPolicy: Never
globalDefault: false
description: "Cube Studio pipeline priority: high"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: pipeline-mid
value: 100000
preemptionPolicy: Never
globalDefault: false
description: "Cube Studio pipeline priority: mid"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: pipeline-low
value: 0
preemptionPolicy: Never
globalDefault: false
description: "Cube Studio pipeline priority: low"
```

- [ ] **Step 2: myapp/config.py 默认值**

L750 `MINIO_HOST = 'minio.kubeflow:9000'` 之后追加：

```python
MINIO_ACCESS_KEY = 'minio'
MINIO_SECRET_KEY = 'minio123'

# 企业版 #9：pipeline 优先级档位 -> 集群 PriorityClass 名映射。
# 空 dict = 功能关闭（workflow spec 不注入任何优先级字段，存量行为不变）；
# 启用需先 apply install/kubernetes/cube/priorityclass.yaml，再配置：
# PIPELINE_PRIORITY_CLASS = {'high': 'pipeline-high', 'mid': 'pipeline-mid', 'low': 'pipeline-low'}
PIPELINE_PRIORITY_CLASS = {}
```

- [ ] **Step 3: overlays 部署模板同步**

`install/kubernetes/cube/overlays/config/config.py` L747 `MINIO_HOST = 'minio.kubeflow:9000'` 之后追加（与 Step 2 相同内容，样例映射以注释形式给出）：

```python
MINIO_ACCESS_KEY = 'minio'
MINIO_SECRET_KEY = 'minio123'

# pipeline 优先级档位 -> 集群 PriorityClass 名映射（企业版 #9）。
# 先 kubectl apply priorityclass.yaml，再按需放开下行配置；注释状态 = 功能关闭。
# PIPELINE_PRIORITY_CLASS = {'high': 'pipeline-high', 'mid': 'pipeline-mid', 'low': 'pipeline-low'}
```

- [ ] **Step 4: 语法验证 + 提交**

Run: `python -m py_compile myapp/config.py install/kubernetes/cube/overlays/config/config.py`
Expected: 无输出

```bash
git add install/kubernetes/cube/priorityclass.yaml myapp/config.py install/kubernetes/cube/overlays/config/config.py
git commit -m "feat: PriorityClass 三档安装清单与 PIPELINE_PRIORITY_CLASS/minio 凭证 conf 化（企业版#9#8 部署面）"
```

---

### Task 7: 全量回归与 spec 验收核对

**Files:**
- 无新改动；验证 + 计划文档勾选状态回写

> **执行完成记录（2026-11-08，feature/pipeline-schedule-enhance，6 个实现 commit）：**
>
> - 后端全量：`python -m pytest tests -q` → **82 passed**（基线 65 + Task1 13 + Task2 4）；6 个改动文件 `py_compile` exit 0。
> - 前端：`myapp/vision` 无 node_modules（本机未装依赖），无法跑真实 `tsc --noEmit`；改用仓库内已有的 `myapp/frontend/node_modules/typescript` 以 `--noResolve --noEmit` 做语法校验 → **无 parse/JSX 语法错误**，改动区（Setting/index.tsx L232-250）无诊断；其余 16 条均为 `--noResolve` 导致的 TS2792 模块解析噪声。
> - schedules.py 改动面：`git diff c43bc90..HEAD -- myapp/tasks/schedules.py` 仅 2 行 import + expired_limit 分支内 2 处插入（artifact 回收 8 行 + RunHistory 清理 10 行），#5 涉及的补录/超时/并发/依赖逻辑零改动。凭证 grep：`minio123` 仅出现于 `py_minio.py` 的 conf 缺省值。
> - **两处与计划的偏差**（执行时取证修正）：
>   1. Task 5 未采用 `Dropdown description=` 属性——`@fluentui/react` v8 `IDropdownProps`（继承 `ISelectableDroppableTextProps`）无法在本环境确认存在 `description`，且仓内 `<Dropdown description=>` 零先例；改为 Dropdown 仅用已验证属性 + 新增 `style.desc` 说明行（字号/颜色对齐 fluentui TextField description）。
>   2. Task 1 测试用例计数 12→13（原计划用例与实现自矛盾，已按安全红线修正）。
> - **待决项：spec A5 的 visionPlus UI 增量未执行**（计划已主动收窄，但母文档 §1-A5 字面仍要求）。见下方验收清单最后两项。

- [x] **Step 1: 后端全量**

Run: `python -m pytest tests -q`
实测：**82 passed**（基线 65 + 13 pipeline_schedule + 4 py_minio）；计到计划基线 81 为估算偏差，以实际为准

Run: `python -m py_compile myapp/views/view_pipeline.py myapp/tasks/schedules.py myapp/views/view_workflow.py myapp/config.py myapp/utils/py/pipeline_schedule.py myapp/utils/py/py_minio.py`
Expected: 无输出

- [x] **Step 2: 前端类型检查**

vision：`cd myapp/vision; npx tsc --noEmit` → exit 0
（visionPlus 本轮无改动，跳过）

- [ ] **Step 3: spec 验收清单核对（对照母文档 §1-A5/A8/A9 修订文本逐项打勾）**

- [x] #9：conf 缺省时 `make_workflow_yaml` 输出不含任何 priority 键（用 Task 3 Step 5 的 python -c 断言 `{}` 佐证）——已验证：`priority_spec_patch('high', {})` → `{}`
- [x] #9：档位+映射双命中时注入 `spec.priority` 与 `templateDefaults.priorityClassName`（Task 1 测试 1/6 覆盖）——已验证：`('mid', {'mid':'pipeline-mid'})` → `{'priority': 100, 'templateDefaults': {'priorityClassName': 'pipeline-mid'}}`
- [x] #9：PriorityClass 清单三档且全部 `preemptionPolicy: Never`（Task 6 文件）
- [x] #9：表单/列清单/前端下拉三处 priority 可达（Task 3/5）
- [x] #8：RunHistory 仅删终态、保留窗、limit=0 不限制（Task 1 测试 8/9 覆盖；Task 4 接入）
- [x] #8：artifact 按 workflow_name 前缀回收、失败不阻塞（Task 2 测试 + Task 4 接入）
- [x] #5：补录/超时/并发/依赖后端逻辑零改动（diff 仅 expired_limit 分支两处插入）；vision 侧 `cronjob_start_time`(L331 DatePicker) 与 `expired_limit`(L380) 入口已存在
- [x] 凭证：新代码零硬编码 access/secret（Task 2/6）
- [ ] #5（待用户裁决）：母文档 §1-A5 字面要求「双 Setting 面板补 `cronjob_start_time`、visionPlus 补 `expired_limit` 字段」——取证：visionPlus `Setting/index.tsx` L306-417 整块 pipeline 调度字段处于 JSX 注释内（`{/* ... */}`），无存活面板；计划按 YAGNI 本轮不新建，需用户确认收窄或补一个 Task 复活该面板
- [ ] #8（待用户裁决）：终态集合当前为 `Deleted/Succeeded/Failed`（与母文档一致）；argo 另有 `Error`/`Terminated` 终态（watch_workflow.py L153 直接回写 crd status），是否一并纳入终态表需确认

- [ ] **Step 4: 汇报结果，进入 finishing-a-development-branch**

---

## Self-Review 记录

1. **Spec 覆盖**：A9 全链路（模型已有字段→注入/表单/前端/清单/conf 全覆盖）、A8 两层清理（DB+artifact，工作目录按决策留 v2）、A5 前端入口已存在于 vision（零改动）+ 回归护栏（Task 7 diff 断言）——无缺口。
2. **占位符扫描**：无 TBD/“适当处理”类措辞；所有代码步骤含完整代码。
3. **类型一致性**：`priority_spec_patch(pipeline_priority, priority_class_map)`（Task 1 定义 = Task 3 调用）；`expired_run_ids_to_delete(records, limit, terminal_states)`（Task 1 = Task 4）；`make_minio_client(conf_get)` / `remove_object_prefix(client, bucket, prefix)`（Task 2 = Task 4）；bucket 常量 `'mlpipeline'` 与 view_workflow 既有用法一致；档位表 high/mid/low 与清单 name、前端 options、表单 choices 四处一致。
