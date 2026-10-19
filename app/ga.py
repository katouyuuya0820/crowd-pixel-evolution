"""対話型GA：集団・見せる組の選び方・適応度・次の世代。

1回の選択 = 並べた k 枚から1枚を選ぶ = 選んだ1枚が残りの k-1 枚それぞれに勝った、として数える。
"""

from __future__ import annotations

import random

from . import pixel


def fitness(ind: dict) -> float:
    """平滑化した勝率。比較が少ない個体を極端に評価しない。"""
    return (ind["wins"] + 1) / (ind["comps"] + 2)


class Population:
    def __init__(self, size: int, rng: random.Random, gen: int = 0, members: list | None = None,
                 res: int = pixel.DEFAULT_RES, pal: list[str] = pixel.PALETTE):
        self.rng = rng
        self.res = res
        self.gen = gen
        self.size = size
        if members is not None:
            self.members = members
        else:
            self.members = [self._new_ind(pixel.random_genome(rng, res, pal), i, None) for i in range(size)]

    def _new_ind(self, genome: dict, idx: int, parent: str | None) -> dict:
        return {"id": f"g{self.gen}-{idx}", "genome": genome, "wins": 0, "comps": 0, "parent": parent}

    def get(self, ind_id: str) -> dict | None:
        return next((m for m in self.members if m["id"] == ind_id), None)

    def pick_set(self, k: int, avoid: frozenset[str] | None = None) -> list[dict]:
        """比較数の少ない個体を優先して k 枚を選ぶ。直前と全く同じ組は避ける。並びは毎回シャッフル。"""
        k = max(2, min(k, len(self.members)))
        for _ in range(5):
            chosen = sorted(self.members, key=lambda m: m["comps"] + self.rng.random() * 3)[:k]
            if avoid is None or frozenset(m["id"] for m in chosen) != avoid or k == len(self.members):
                break
        self.rng.shuffle(chosen)
        return chosen

    def record_choice(self, winner_id: str, shown_ids: list[str]) -> bool:
        w = self.get(winner_id)
        others = [self.get(i) for i in set(shown_ids) if i != winner_id]
        if w is None or not others or any(o is None for o in others):
            return False
        w["wins"] += len(others)
        w["comps"] += len(others)
        for o in others:
            o["comps"] += 1
        return True

    def ranked(self) -> list[dict]:
        return sorted(self.members, key=lambda m: (fitness(m), m["comps"]), reverse=True)

    def _tournament(self, k: int = 5) -> dict:
        cands = self.rng.sample(self.members, min(k, len(self.members)))
        return max(cands, key=fitness)

    def next_generation(self, elite: int = 2, strength: float = 1.0, cx_rate: float = 0.7,
                        model=None) -> "Population":
        ranked = self.ranked()
        nxt = Population.__new__(Population)
        nxt.rng, nxt.gen, nxt.size, nxt.res = self.rng, self.gen + 1, self.size, self.res
        members = []
        for i, m in enumerate(ranked[:elite]):
            members.append(nxt._new_ind(m["genome"], i, m["id"]))
        while len(members) < self.size:
            parent = self._tournament()
            child = parent["genome"]
            if self.rng.random() < cx_rate:  # もう1体の親の領域を貼り込む
                child = pixel.crossover(child, self._tournament()["genome"], self.rng)
            child = pixel.mutate(child, self.rng, strength, model)
            members.append(nxt._new_ind(child, len(members), parent["id"]))
        nxt.members = members
        return nxt
