"""ピクセルごとの「どの色が選ばれやすいか」のモデル。

選択のたびに、各ピクセルで
  提示：並んだ画像のその位置の色（偶然選ばれる期待値 1/k を足す）
  選択：選ばれた画像のその位置の色（1 を足す）
を数える。手書き文字のように線の位置は少しずれるので、数える時にぼかしフィルターをかけ、
周りのピクセルにも同じ色として少し配る（上下左右 BLUR_ORTH、斜め BLUR_DIAG）。選ばれやすさ（lift）= (選択 + m) / (期待 + m)。1 なら偶然と同じ＝その色は関係ない。
これに
  ・どの色でも差が無いピクセル（重要でない）は、白を少しだけ出しやすく
  ・たまに完全にランダム
  ・全ピクセルを合計した色ごとの選ばれやすさ（例：お題に合わない色は選ばれにくい）を掛け、
    選ばれにくい色はだんだん出にくくする
を加えた確率で、突然変異の色を選ぶ。
"""

from __future__ import annotations

import random

PRIOR = 2.0  # m：数が少ないうちは lift を 1 に寄せる
SHARPEN = 2.0  # lift の差を強調する指数
WHITE = 0  # パレットの白の番号
WHITE_BIAS = 0.3  # 重要でないピクセルで白に足す重み（lift 1 に対して）
BLUR_ORTH = 0.5  # 集計のぼかし：上下左右に配る重み（真ん中は 1）
BLUR_DIAG = 0.25  # 集計のぼかし：斜めに配る重み
EPSILON = 0.1  # ランダムにする割合（その半分は全体の色の割合に沿う）
GLOBAL_PRIOR = 30.0  # 全体の選ばれやすさの m（大きいほど「だんだん」効く）
GLOBAL_POWER = 3.0  # 全体の選ばれやすさを効かせる強さ（試験で 1.5 より序盤が速かった）


class ColorModel:
    def __init__(self, w: int, h: int, n_colors: int, shown: list[float] | None = None,
                 chosen: list[float] | None = None, events: int = 0):
        self.w, self.h, self.n = w, h, n_colors
        size = w * h * n_colors
        self.shown = shown if shown is not None else [0.0] * size  # 偶然選ばれる期待値の合計
        self.chosen = chosen if chosen is not None else [0.0] * size
        self.events = events
        self._dist: list[list[float]] | None = None
        # ぼかしフィルター：ピクセルごとに (配る先, 重み)
        self._kernel = []
        for y in range(h):
            for x in range(w):
                ks = []
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < h and 0 <= xx < w:
                            wt = 1.0 if dx == dy == 0 else BLUR_ORTH if dx == 0 or dy == 0 else BLUR_DIAG
                            if wt > 0:
                                ks.append((yy * w + xx, wt))
                self._kernel.append(ks)

    # ---------- 集計 ----------
    def record(self, winner_px: list[int], shown_pxs: list[list[int]]) -> None:
        k = len(shown_pxs)
        n = self.n
        kernel = self._kernel
        for px in shown_pxs:
            for i, c in enumerate(px):
                for j, wt in kernel[i]:
                    self.shown[j * n + c] += wt / k
        for i, c in enumerate(winner_px):
            for j, wt in kernel[i]:
                self.chosen[j * n + c] += wt
        self.events += 1
        self._dist = None

    def global_lift(self) -> list[float]:
        """全ピクセルを合計した、色ごとの選ばれやすさ（1 = 偶然と同じ）。"""
        n = self.n
        out = []
        for c in range(n):
            ch = sum(self.chosen[c::n])
            sh = sum(self.shown[c::n])
            out.append((ch + GLOBAL_PRIOR) / (sh + GLOBAL_PRIOR))
        return out

    def global_probs(self) -> list[float]:
        g = [x ** GLOBAL_POWER for x in self.global_lift()]
        s = sum(g)
        return [x / s for x in g]

    def lift(self, i: int, c: int) -> float:
        j = i * self.n + c
        return (self.chosen[j] + PRIOR) / (self.shown[j] + PRIOR)

    # ---------- 確率 ----------
    def distribution(self) -> list[list[float]]:
        """各ピクセルの色の確率（キャッシュ）。"""
        if self._dist is not None:
            return self._dist
        w, h, n = self.w, self.h, self.n
        glob = [x ** GLOBAL_POWER for x in self.global_lift()]
        gprob = self.global_probs()
        dist = []
        for i in range(w * h):
            lifts = [self.lift(i, c) for c in range(n)]
            weights = [(l ** SHARPEN) * glob[c] for c, l in enumerate(lifts)]
            # 重要度：一番選ばれやすい色がどれだけ偶然（1）を上回るか。0 なら重要でない
            importance = min(1.0, max(0.0, max(lifts) - 1.0))
            weights[WHITE] += WHITE_BIAS * (1.0 - importance)
            s = sum(weights)
            dist.append([(1 - EPSILON) * v / s + EPSILON * (0.5 / n + 0.5 * gprob[c])
                         for c, v in enumerate(weights)])
        self._dist = dist
        return dist

    def sample(self, i: int, rng: random.Random) -> int:
        r, acc = rng.random(), 0.0
        probs = self.distribution()[i]
        for c, p in enumerate(probs):
            acc += p
            if r < acc:
                return c
        return self.n - 1

    def sample_global(self, rng: random.Random) -> int:
        """全体の色の割合に沿って1色を選ぶ（塗りつぶし用）。"""
        r, acc = rng.random(), 0.0
        for c, p in enumerate(self.global_probs()):
            acc += p
            if r < acc:
                return c
        return self.n - 1

    def best(self) -> list[int]:
        """各ピクセルで一番出やすい色（みんなの好み）。"""
        return [max(range(self.n), key=p.__getitem__) for p in self.distribution()]

    # ---------- 保存 ----------
    def to_json(self) -> dict:
        return {"w": self.w, "h": self.h, "n": self.n, "events": self.events,
                "shown": [round(v, 4) for v in self.shown], "chosen": self.chosen}

    @classmethod
    def from_json(cls, d: dict) -> "ColorModel":
        return cls(d["w"], d["h"], d["n"], d["shown"], d["chosen"], d.get("events", 0))
