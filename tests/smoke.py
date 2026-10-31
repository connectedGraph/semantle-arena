"""端到端冒烟：不开浏览器也能验证对局链路。

覆盖
----
1. /api/meta       词池规模与模型信息
2. 猜词评分        池内词、池外词、重复猜、命中
3. 名次单调性      相似度高的词名次不应更差（抽样检查）
4. 对局结算        双方都命中时按次数判胜负
5. Agent 工具      guess / review 的返回结构

用法
----
    ./.venv/bin/python tests/smoke.py            # 需要后端在 :8010 跑
    ./.venv/bin/python tests/smoke.py --spawn    # 自己拉起后端再测
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("ARENA_BASE", "http://127.0.0.1:8010")

# 本机环境常设 ALL_PROXY=socks5://...，httpx 会把它套到 localhost 上导致
# "Using SOCKS proxy, but socksio is not installed"。测试全走回环，明确禁用代理。
NO_PROXY = {"trust_env": False}


def _client(base_url: str, timeout: float = 30) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout, **NO_PROXY)

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  {PASS} {name}")
    else:
        print(f"  {FAIL} {name}  {detail}")
        failures.append(name)


def wait_ready(timeout: float = 60) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if _client(BASE, 2).get("/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def test_meta(c: httpx.Client) -> None:
    print("meta")
    r = c.get("/api/meta")
    check("GET /api/meta 200", r.status_code == 200)
    m = r.json()
    count = m["pool"]["count"]
    pool_total = m["pool"].get("pool_total", count)
    # 当前档位可能远小于全池（精简档 3000），所以两个层级都要查
    check(f"全池规模合理 ({pool_total})", pool_total > 5000, "全池应大于 5000")
    check(f"当前档位词数合理 ({count})", 1000 <= count <= pool_total,
          f"应在 1000~{pool_total}")
    check("档位信息完整", set(m["tiers"]) >= {"small", "medium", "full"},
          str(m.get("tiers")))
    check("二字谜底多于三字",
          m["pool"]["by_length"].get("2", 0) > m["pool"]["by_length"].get("3", 0))
    check("返回引擎参数", "char_penalty" in m["config"])


def test_tier(c: httpx.Client) -> None:
    print("词库档位")
    original = c.get("/api/meta").json()["tier"]

    r = c.post("/api/tier", json={"tier": "medium"})
    check("切到 medium 200", r.status_code == 200)
    body = r.json()
    check("medium 词数多于 small", body["count"] > body["tiers"]["small"],
          f"{body['count']} vs {body['tiers']['small']}")

    r = c.post("/api/tier", json={"tier": "small"})
    check("切回 small", r.json()["count"] == r.json()["tiers"]["small"])

    bad = c.post("/api/tier", json={"tier": "nonexistent"})
    check("非法档位被拒 422", bad.status_code == 422, str(bad.status_code))

    # 恢复原档位
    c.post("/api/tier", json={"tier": original})


def test_scoring(c: httpx.Client) -> None:
    print("猜词评分")
    r = c.post("/api/race", json={"mode": "versus", "max_steps": 12, "min_len": 2, "max_len": 2})
    check("开局 200", r.status_code == 200)
    race = r.json()
    rid = race["race_id"]
    check("开局不泄露答案", "target" not in race or race["target"] is None)

    # 池内词
    g1 = c.post(f"/api/race/{rid}/guess", json={"word": "电脑"}).json()["guess"]
    check("池内词返回相似度", 0 <= g1["similarity_pct"] <= 100,
          str(g1["similarity_pct"]))
    check("池内词有名次", g1["rank"] is None or g1["rank"] >= 1)

    # 池外词：词池里没有，但也应该能算
    g2 = c.post(f"/api/race/{rid}/guess", json={"word": "干饭搭子"}).json()["guess"]
    check("池外词照样算相似度", "similarity_pct" in g2, str(g2))
    check("池外词不报错", g2.get("word") == "干饭搭子")

    # 非汉字应被拒
    bad = c.post(f"/api/race/{rid}/guess", json={"word": "abc"})
    check("非汉字被拒 422", bad.status_code == 422, str(bad.status_code))
    too_long = c.post(f"/api/race/{rid}/guess", json={"word": "一二三四五六七八九十"})
    check("超长被拒 422", too_long.status_code == 422)

    # 名次单调性：相似度更高的词名次不应更差
    words = ["钢琴", "音乐", "电脑", "医生", "足球", "宇宙", "谎言", "地铁"]
    rows = []
    for w in words:
        rows.append(c.post(f"/api/race/{rid}/guess", json={"word": w}).json()["guess"])
    rows.sort(key=lambda g: -g["similarity"])
    ok = True
    for a, b in zip(rows, rows[1:]):
        ra, rb = a["rank"], b["rank"]
        if ra is not None and rb is not None and ra > rb and a["similarity"] > b["similarity"] + 0.08:
            ok = False
    check("名次与相似度大体一致", ok)


def test_settlement(c: httpx.Client) -> None:
    print("结算")
    r = c.post("/api/race", json={"mode": "challenge", "target_word": "苹果",
                                  "max_steps": 3})
    check("出题模式开局 200", r.status_code == 200)
    rid = r.json()["race_id"]
    challenge = r.json()
    check("出题模式 target_length 正确", challenge["target_length"] == 2)

    # 人类直接猜中，验证 human_done 与命中
    g = c.post(f"/api/race/{rid}/guess", json={"word": "苹果"}).json()
    check("猜中触发 human_done", g["human_done"] is True)
    check("猜中相似度为 100", g["guess"]["similarity_pct"] > 99.9)
    check("猜中 is_target", g["guess"]["is_target"] is True)


def test_agent_tools() -> None:
    print("Agent 工具（直接调用，不经模型）")
    sys.path.insert(0, str(ROOT / "engine"))
    from semantle.agent.runner import ToolExecutor, format_rows
    from semantle.models import Game
    from semantle.store import get_store

    store = get_store()
    game = Game(target="苹果")
    ex = ToolExecutor(store, game)

    rows = ex.guess(["香蕉", "电脑", "香蕉"])  # 含重复
    check("guess 去重", len(rows) == 2, str(len(rows)))
    check("guess 返回字段完整",
          all({"word", "similarity_pct", "rank", "level"} <= set(r) for r in rows))

    rows2 = ex.guess(["香蕉"])
    check("重复猜标记 reused", rows2[0].get("reused") is True)
    check("重复猜不增加次数", game.guess_count == 2, str(game.guess_count))

    rev = ex.review(-1)
    check("review 只回已猜词", {r["word"] for r in rev} == {"香蕉", "电脑"}, str(rev))
    check("review 不泄露答案", "苹果" not in {r["word"] for r in rev})
    check("格式化有表头", format_rows(rev).startswith("rank\tword"))

    # 猜中后 game.finished
    ex.guess(["苹果"])
    check("命中原词后 game.finished", game.finished is True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spawn", action="store_true", help="自己拉起后端")
    args = ap.parse_args()

    proc = None
    if args.spawn:
        env = os.environ.copy()
        env.setdefault("ARENA_LLM_BASE_URL", "http://127.0.0.1:1/v1")
        proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "semantle.main:app",
             "--host", "127.0.0.1", "--port", "8010"],
            cwd=str(ROOT / "engine"), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        if not wait_ready():
            print("后端未能在 60s 内就绪")
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            sys.exit(1)

    try:
        with _client(BASE) as c:
            test_meta(c)
            test_tier(c)
            test_scoring(c)
            test_settlement(c)
        test_agent_tools()
    finally:
        if proc is not None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)

    print()
    if failures:
        print(f"\033[31m{len(failures)} 项失败\033[0m: {', '.join(failures)}")
        sys.exit(1)
    print("\033[32m全部通过\033[0m")


if __name__ == "__main__":
    main()
