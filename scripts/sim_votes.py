"""動作確認用：N人分の自動投票。各人は並んだ中から見本（ハート / 数字の3）に一番近い画像を選ぶ
（bias の確率でそうし、残りはランダム）。何回の選択で見本に近づくかを見るためのもの。

    uv run python scripts/sim_votes.py --clients 8 --votes 300
"""

import argparse
import random
import threading
import time

import httpx

# 16×16 のハート（カラー8色：0 白 / 1 黒 / 2 赤 / 6 黄）
HEART = [
    "0000000000000000",
    "0011100000111000",
    "0122210001222100",
    "1226221012222210",
    "1262222122222210",
    "1222222222222210",
    "1222222222222210",
    "0122222222222100",
    "0012222222221000",
    "0001222222210000",
    "0000122222100000",
    "0000012221000000",
    "0000001210000000",
    "0000000100000000",
    "0000000000000000",
    "0000000000000000",
]
# 16×16 の数字「3」（グレー4階調：0 白 / 3 黒）
DIGIT3 = [
    "0000000000000000",
    "0000333333330000",
    "0003333333333000",
    "0033300000033300",
    "0000000000033300",
    "0000000000033300",
    "0000000000333000",
    "0000003333330000",
    "0000003333330000",
    "0000000000333000",
    "0000000000033300",
    "0000000000033300",
    "0033300000033300",
    "0003333333333000",
    "0000333333330000",
    "0000000000000000",
]
TARGETS = {"heart": "".join(HEART), "3": "".join(DIGIT3)}
TARGET = TARGETS["heart"]


def match(genome: dict) -> float:
    """見本と同じ色の画素の割合（16×16 の時だけ意味がある）。"""
    px = genome["px"]
    tgt = TARGET.replace("3", "1") if len(genome["pal"]) == 2 else TARGET  # 白黒では黒が 1 番
    return sum(a == b for a, b in zip(px, tgt)) / len(tgt)


def worker(base: str, cid: str, n: int, delay: float, bias: float) -> None:
    rng = random.Random(cid)
    with httpx.Client(base_url=base, timeout=10) as c:
        for _ in range(n):
            s = c.get("/api/set", params={"client_id": cid}).json()
            items = s["items"]
            pick = max(items, key=lambda it: match(it["genome"])) if rng.random() < bias else rng.choice(items)
            c.post("/api/vote", json={"client_id": cid, "gen": s["gen"], "winner": pick["id"],
                                      "shown": [it["id"] for it in items]})
            time.sleep(delay * rng.uniform(0.5, 1.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--clients", type=int, default=8)
    ap.add_argument("--votes", type=int, default=100, help="1人あたりの選択数")
    ap.add_argument("--delay", type=float, default=0.02, help="1回ごとの待ち（秒）")
    ap.add_argument("--bias", type=float, default=0.8)
    ap.add_argument("--target", choices=list(TARGETS), default="heart", help="heart はカラー8色、3 はグレー4階調・白黒で")
    a = ap.parse_args()
    global TARGET
    TARGET = TARGETS[a.target]
    ts = [threading.Thread(target=worker, args=(a.base, f"sim-{i}", a.votes, a.delay, a.bias)) for i in range(a.clients)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    h = httpx.get(a.base + "/api/history").json()
    for e in h["history"][:: max(1, len(h["history"]) // 15)] + h["history"][-1:]:
        print(f"第{e['gen']:3d}世代  累計{e['total_votes']:5d}  ベストの見本との一致率 {match(e['top'][0]['genome']):.0%}")


if __name__ == "__main__":
    main()
