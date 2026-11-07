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


# ---- LS REST 客户端（HTTP 全 mock，不依赖真实 LS 实例） ----
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
