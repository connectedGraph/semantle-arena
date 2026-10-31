"""真人 Agent 对战冒烟：让模型真的跑一局，验证 SSE 全链路。

与 smoke.py 的区别：smoke.py 不调模型，这里会真实调用 LLM，
所以慢（几十秒到几分钟），且依赖网关可用。

用法
----
    ./.venv/bin/python tests/agent_race.py
    ./.venv/bin/python tests/agent_race.py --target 钢琴 --steps 12
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time

import httpx

BASE = os.environ.get("ARENA_BASE", "http://127.0.0.1:8010")
NO_PROXY = {"trust_env": False}


def run(target: str | None, steps: int, human_words: list[str]) -> None:
    with httpx.Client(base_url=BASE, timeout=60, **NO_PROXY) as c:
        r = c.post("/api/race", json={
            "mode": "versus",
            "target_word": target,
            "max_steps": steps,
            "min_len": 2,
            "max_len": 2,
        })
        r.raise_for_status()
        race = r.json()
        rid = race["race_id"]
        print(f"对局 {rid}  字数 {race['target_length']}  步数上限 {race['max_steps']}")

        events: list[dict] = []
        done = threading.Event()
        end: dict = {}

        def listen() -> None:
            with c.stream("GET", f"/api/race/{rid}/events") as s:
                for line in s.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    ev = json.loads(line[6:])
                    events.append(ev)
                    t = ev.get("type")
                    if t == "tool_result":
                        rows = ev.get("rows") or []
                        brief = ", ".join(
                            f"{x['word']}:{x['similarity_pct']:.1f}" for x in rows[:5]
                        )
                        print(f"  [第 {len(events)} 事件] 工具 {ev['name']} → {brief}")
                    elif t == "assistant":
                        print(f"  Agent: {ev['text'][:90]}")
                    elif t == "race_end":
                        end.update(ev)
                        done.set()
                        break

        th = threading.Thread(target=listen, daemon=True)
        th.start()

        c.post(f"/api/race/{rid}/start").raise_for_status()

        # 人类正常猜几个词，验证并发不打架
        for w in human_words:
            time.sleep(0.4)
            g = c.post(f"/api/race/{rid}/guess", json={"word": w}).json()["guess"]
            print(f"  我猜 {w} → {g['similarity_pct']:.2f}%  rank={g['rank']}")

        # 等 Agent 跑完；它跑完不等于结算——人类没猜中也没放弃时对局仍在进行。
        def agent_finished() -> bool:
            snap = c.get(f"/api/race/{rid}").json()
            return snap["agent_done"]

        t0 = time.time()
        while time.time() - t0 < 240 and not agent_finished():
            time.sleep(1)

        # 人类放弃，触发结算。
        # 注意：Agent 跑完后可能已经结算（比如它猜中了，或人类已放弃），此时队列里
        # 已经没有待消费的 race_end；事件流在收到它那一刻就会关闭。这里两种情况都接受。
        if not done.is_set():
            c.post(f"/api/race/{rid}/giveup")
            if not done.wait(timeout=30):
                print("!! 放弃后 30s 内仍未收到 race_end")

        print()
        print("=" * 60)
        if end:
            print(f"答案    : {end.get('target')}")
            print(f"结果    : {end.get('winner')}")
            print(f"人类    : 猜中用 {end.get('human_words')} 词（共交 {end.get('human_guesses')}），"
                  f"命中={end.get('human_solved')}")
            print(f"Agent   : 猜中用 {end.get('agent_words')} 词（共交 {end.get('agent_guesses')}），"
                  f"命中={end.get('agent_solved')}")
        else:
            snap = c.get(f"/api/race/{rid}").json()
            print(f"（未收到 race_end，用快照判断）finished={snap['finished']}")
            print(f"结果    : {snap.get('winner')}")
            print(f"人类    : 猜中用 {snap.get('human_words')} 词（共交 {snap.get('human_guesses')}）")
            print(f"Agent   : 猜中用 {snap.get('agent_words')} 词（共交 {snap.get('agent_guesses')}）")
        kinds = {}
        for e in events:
            kinds[e["type"]] = kinds.get(e["type"], 0) + 1
        print(f"事件计数: {kinds}")

        # 断言
        ok = True
        if "race_end" not in kinds and not c.get(f"/api/race/{rid}").json()["finished"]:
            print("✗ 对局没有结算")
            ok = False
        if any(e["type"] == "error" for e in events):
            errs = [e for e in events if e["type"] == "error"]
            print(f"✗ 出现错误事件: {errs}")
            ok = False
        if end.get("agent_guesses", 0) == 0:
            print("✗ Agent 一次都没猜")
            ok = False
        print("✓ 全链路通过" if ok else "✗ 存在问题")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="钢琴")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--human", default="电脑,音乐,医生")
    args = ap.parse_args()
    run(args.target, args.steps, args.human.split(","))
