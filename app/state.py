"""ゲームの状態・票の数・履歴の保存（data/<セッション>/）。"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

from . import pixel
from .ga import Population, fitness
from .model import ColorModel

DATA_DIR = Path(os.environ.get("HIEC_DATA") or Path(__file__).resolve().parent.parent / "data")
ACTIVE_SEC = 60  # この秒数以内に操作があったクライアントを「参加中」と数える
HISTORY_TOP = 4  # リザルト用に世代ごとに残す上位の数


class Game:
    def __init__(self, data_dir: Path = DATA_DIR, seed: int | None = None):
        self.data_dir = data_dir
        self.rng = random.Random(seed)
        if not self._resume():
            self.reset()

    # ---------- セッション ----------
    def reset(self, size: int = 18, threshold: int | None = None, topic: str | None = None,
              res: int = pixel.DEFAULT_RES, k: int = 9, palette: str = pixel.DEFAULT_PALETTE) -> None:
        self.session = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.topic = topic if topic is not None else getattr(self, "topic", "")
        self.size = max(4, min(int(size), 40))
        self.k = max(2, min(int(k), self.size))  # 1回に並べる枚数
        # 既定：1世代で各個体が平均3回ほど並ぶ選択数（試験では 6 回より速く進んだ）
        self.threshold = int(threshold) if threshold else max(1, -(-self.size * 3 // self.k))
        self.res = max(4, min(int(res), 128))
        self.palette = palette if palette in pixel.PALETTES else pixel.DEFAULT_PALETTE
        pal = pixel.PALETTES[self.palette]
        self.pop = Population(self.size, self.rng, res=self.res, pal=pal)
        self.model = ColorModel(self.res, self.res, len(pal))
        self.total_votes = 0
        self.gen_votes = 0
        self.client_votes: dict[str, int] = {}
        self.client_seen: dict[str, float] = {}
        self.client_last_set: dict[str, frozenset[str]] = {}
        self.history: list[dict] = []
        self._save()

    def _session_dir(self) -> Path:
        d = self.data_dir / self.session
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resume(self) -> bool:
        if not self.data_dir.exists():
            return False
        sessions = sorted(p for p in self.data_dir.iterdir() if (p / "current.json").exists())
        if not sessions:
            return False
        try:
            cur = json.loads((sessions[-1] / "current.json").read_text(encoding="utf-8"))
            self.session = sessions[-1].name
            self.topic = cur["topic"]
            self.size = cur["size"]
            self.threshold = cur["threshold"]
            self.total_votes = cur["total_votes"]
            self.gen_votes = cur["gen_votes"]
            self.client_votes = cur.get("client_votes", {})
            self.res = cur.get("res", pixel.DEFAULT_RES)
            self.k = cur.get("k", 9)
            self.palette = cur.get("palette", pixel.DEFAULT_PALETTE)
            if not all(pixel.is_valid(m["genome"]) for m in cur["members"]):
                return False  # 古い形式の遺伝子なら新しく始める
            self.model = (ColorModel.from_json(cur["model"]) if "model" in cur
                          else ColorModel(self.res, self.res, len(pixel.PALETTES[self.palette])))
            self.pop = Population(self.size, self.rng, gen=cur["gen"], members=cur["members"], res=self.res)
            self.history = []
            for f in sorted(sessions[-1].glob("gen_*.json")):
                self.history.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, KeyError, ValueError):
            return False
        self.client_seen = {}
        self.client_last_set = {}
        return True

    def _save(self) -> None:
        cur = {
            "topic": self.topic,
            "size": self.size,
            "threshold": self.threshold,
            "res": self.res,
            "k": self.k,
            "palette": self.palette,
            "total_votes": self.total_votes,
            "gen_votes": self.gen_votes,
            "gen": self.pop.gen,
            "client_votes": self.client_votes,
            "members": self.pop.members,
            "model": self.model.to_json(),
        }
        path = self._session_dir() / "current.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    # ---------- 投票 ----------
    def touch(self, client_id: str) -> None:
        self.client_seen[client_id] = time.time()

    def participants(self) -> int:
        now = time.time()
        return sum(1 for t in self.client_seen.values() if now - t < ACTIVE_SEC)

    def set_for(self, client_id: str) -> dict:
        """このクライアントに並べる k 枚。"""
        self.touch(client_id)
        chosen = self.pop.pick_set(self.k, self.client_last_set.get(client_id))
        self.client_last_set[client_id] = frozenset(m["id"] for m in chosen)
        return {
            "gen": self.pop.gen,
            "topic": self.topic,
            "items": [{"id": m["id"], "genome": m["genome"]} for m in chosen],
            "my_votes": self.client_votes.get(client_id, 0),
        }

    def vote(self, client_id: str, gen: int, winner: str, shown: list[str]) -> dict:
        """選択を記録する。古い世代の選択は捨てる。戻り値の advanced は世代が進んだか。"""
        self.touch(client_id)
        if gen != self.pop.gen or not self.pop.record_choice(winner, shown):
            return {"accepted": False, "advanced": False}
        shown_px = [pixel.decode(self.pop.get(i)["genome"])[2] for i in dict.fromkeys(shown)]
        self.model.record(pixel.decode(self.pop.get(winner)["genome"])[2], shown_px)
        self.total_votes += 1
        self.gen_votes += 1
        self.client_votes[client_id] = self.client_votes.get(client_id, 0) + 1
        advanced = False
        if self.gen_votes >= self.threshold:
            self.advance()
            advanced = True
        else:
            self._save()
        return {"accepted": True, "advanced": advanced}

    def advance(self) -> None:
        """世代の結果を履歴に残し、次の世代へ。"""
        ranked = self.pop.ranked()
        entry = {
            "gen": self.pop.gen,
            "topic": self.topic,
            "votes": self.gen_votes,
            "total_votes": self.total_votes,
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "top": [self._ind_view(m, with_genome=True) for m in ranked[:HISTORY_TOP]],
        }
        self.history.append(entry)
        full = dict(entry, members=self.pop.members)
        (self._session_dir() / f"gen_{self.pop.gen:03d}.json").write_text(
            json.dumps(full, ensure_ascii=False), encoding="utf-8"
        )
        self.pop = self.pop.next_generation(model=self.model)
        self.gen_votes = 0
        self.client_last_set.clear()
        self._save()

    # ---------- 設定 ----------
    def set_topic(self, topic: str) -> None:
        self.topic = topic.strip()[:100]
        self._save()

    def set_threshold(self, threshold: int) -> None:
        self.threshold = max(1, min(int(threshold), 10000))
        self._save()

    # ---------- 表示用 ----------
    @staticmethod
    def _ind_view(m: dict, with_genome: bool) -> dict:
        v = {"id": m["id"], "wins": m["wins"], "comps": m["comps"],
             "fitness": round(fitness(m), 4), "parent": m["parent"]}
        if with_genome:
            v["genome"] = m["genome"]
        return v

    def summary(self) -> dict:
        return {
            "session": self.session,
            "topic": self.topic,
            "gen": self.pop.gen,
            "total_votes": self.total_votes,
            "gen_votes": self.gen_votes,
            "threshold": self.threshold,
            "size": self.size,
            "res": self.res,
            "k": self.k,
            "palette": self.palette,
            "participants": self.participants(),
        }

    def admin_state(self, with_genome: bool = True) -> dict:
        s = self.summary()
        s["population"] = [self._ind_view(m, with_genome) for m in self.pop.ranked()]
        pal = pixel.PALETTES[self.palette]
        s["model_best"] = pixel.encode(self.res, self.res, self.model.best(), pal)
        s["model_events"] = self.model.events
        s["model_colors"] = [{"color": col, "lift": round(l, 3)}
                             for col, l in zip(pal, self.model.global_lift())]
        s["client_votes"] = self.client_votes
        return s
