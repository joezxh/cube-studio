"""gov-distill-gen 核心逻辑（spec §2.2 / 计划 Task 3）。

从种子案情出发，按 prompt 模板构建消息，批量调用教师模型 OpenAI 兼容接口，
多候选采样生成蒸馏原始数据 raw.jsonl。HTTP 层可被 monkeypatch（本地测试不依赖网络）。
"""
import concurrent.futures
import datetime
import json
import pathlib
import threading

import requests

_SECTION_MAP = {"system": "system", "fewshot": "fewshot", "input": "tail"}


def load_prompt(docs_dir, task, version):
    """按 `## system/## fewshot/## input` 分节解析 distill-{task}-{version}.md。"""
    path = pathlib.Path(docs_dir) / f"distill-{task}-{version}.md"
    text = path.read_text(encoding="utf-8")
    sections = {"system": "", "fewshot": "", "tail": ""}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            current = _SECTION_MAP.get(heading)
            continue
        if current is not None:
            sections[current] += line + "\n"
    return {"task": task, "version": version,
            "system": sections["system"].strip(),
            "fewshot": sections["fewshot"].strip(),
            "tail": sections["tail"].strip()}


def build_messages(prompt, state):
    """system + 可选 fewshot 轮次 + 末条携带 state 的 user 消息。"""
    msgs = [{"role": "system", "content": prompt["system"]}]
    if prompt.get("fewshot"):
        msgs.append({"role": "user", "content": prompt["fewshot"]})
        msgs.append({"role": "assistant", "content": "（示例见上）"})
    tail = prompt.get("tail", "{{state}}").replace("{{state}}", state)
    msgs.append({"role": "user", "content": tail})
    return msgs


def call_teacher(endpoint, model, messages, *, temperature, top_p, max_tokens,
                 timeout=60, retries=3):
    """调用教师 /v1/chat/completions；失败重试 retries 次（共 retries+1 请求），仍失败抛错。"""
    payload = {"model": model, "messages": messages,
               "temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}
    last_err = None
    for _ in range(retries + 1):
        try:
            resp = requests.post(endpoint, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 - 教师 5xx/网络异常统一重试
            last_err = e
    raise RuntimeError(f"teacher call failed after {retries + 1} attempts: {last_err}")


def _done_keys(out_path):
    done = set()
    p = pathlib.Path(out_path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                done.add((r.get("seed_id"), r.get("candidate_id")))
            except json.JSONDecodeError:
                continue
    return done


def gen_batch(seeds, prompt, endpoint, model, n_candidates, temperature, top_p,
              max_tokens, out_path, resume=True, concurrency=4):
    """并发生成，断点续跑跳过已完成 (seed_id,candidate_id)。返回本次新写入行数。"""
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = _done_keys(out_path) if resume else set()
    todo = [(s, cid) for s in seeds for cid in range(n_candidates)
            if (s.get("seed_id"), cid) not in done]

    lock = threading.Lock()
    mode = "a" if resume and out_path.exists() else "w"
    fh = open(out_path, mode, encoding="utf-8")
    written = 0

    def work(item):
        nonlocal written
        seed, cid = item
        messages = build_messages(prompt, seed.get("state", ""))
        output = call_teacher(endpoint, model, messages,
                              temperature=temperature, top_p=top_p, max_tokens=max_tokens)
        row = {"seed_id": seed.get("seed_id"),
               "task": seed.get("task", prompt.get("task")),
               "prompt_version": prompt.get("version"),
               "candidate_id": cid,
               "state": seed.get("state", ""),
               "messages": messages,
               "output": output,
               "meta": {"temperature": temperature, "top_p": top_p,
                        "max_tokens": max_tokens, "endpoint": endpoint,
                        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        with lock:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            written += 1

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(work, it) for it in todo]
            for fut in concurrent.futures.as_completed(futures):
                fut.result()   # 任一任务抛错则向上传播（start.py 记录失败种子）
    finally:
        fh.close()
    return written
