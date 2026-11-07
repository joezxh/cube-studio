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
