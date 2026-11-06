"""gov-distill-gen 蒸馏生成算子测试（spec §2.2 / 计划 Task 3）。HTTP 全部 monkeypatch，不依赖网络。"""
import json

import pytest

import gen


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._p


@pytest.fixture
def prompt_dict(tmp_path):
    f = tmp_path / "distill-T1-v1.md"
    f.write_text("# x\n## system\nSYS\n## fewshot\nFS\n## input\n{{state}}", encoding="utf-8")
    return gen.load_prompt(tmp_path, "T1", "v1")


def test_load_build(prompt_dict):
    assert prompt_dict["system"] == "SYS"
    msgs = gen.build_messages(prompt_dict, "案情ABC")
    assert msgs[-1]["content"].endswith("案情ABC")


def test_gen_batch_writes_all_candidates(tmp_path, prompt_dict, monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(kw["json"])
        return FakeResp({"choices": [{"message": {"content": '{"label":"矛盾纠纷/邻里纠纷"}'}}]})

    monkeypatch.setattr(gen.requests, "post", fake_post)
    seeds = [{"seed_id": f"s{i}", "task": "T1", "state": "x"} for i in range(2)]
    out = tmp_path / "raw.jsonl"
    n = gen.gen_batch(seeds, prompt_dict, "http://t/v1/chat/completions", "m",
                      2, 0.7, 0.95, 512, out)
    assert n == 4 and len(out.read_text(encoding="utf-8").splitlines()) == 4


def test_resume_skips_done(tmp_path, prompt_dict, monkeypatch):
    monkeypatch.setattr(gen.requests, "post",
                        lambda url, **kw: FakeResp({"choices": [{"message": {"content": "y"}}]}))
    out = tmp_path / "raw.jsonl"
    out.write_text(json.dumps({"seed_id": "s0", "candidate_id": 0}) + "\n", encoding="utf-8")
    seeds = [{"seed_id": "s0", "task": "T1", "state": "x"}]
    assert gen.gen_batch(seeds, prompt_dict, "http://t/v1", "m", 1, 0.7, 0.95, 512, out) == 0


def test_retry_then_fail(monkeypatch):
    state = {"n": 0}

    def flaky(url, **kw):
        state["n"] += 1
        return FakeResp({}, status=500)

    monkeypatch.setattr(gen.requests, "post", flaky)
    with pytest.raises(RuntimeError):
        gen.call_teacher("http://t/v1", "m", [{"role": "user", "content": "x"}],
                         temperature=0.7, top_p=0.95, max_tokens=8, retries=2)
    assert state["n"] == 3   # 1+2 次重试
