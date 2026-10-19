"""ドット絵（限定パレット）の遺伝子と遺伝的操作。

遺伝子は画像そのもの： {"w": int, "h": int, "pal": [色, ...], "px": "0312..."}
px は画素ごとのパレット番号（1文字＝1画素、行順）。はじめは完全な乱数（砂嵐）。
描画はブラウザ側（static/pixel.js）。
"""

from __future__ import annotations

import math
import random
from collections import Counter

DEFAULT_RES = 16
# パレット（0 番は必ず白：重要でないピクセルを白に寄せるため）
PALETTES = {
    # ファミコン風の8色（白・黒・赤・肌・茶・青・黄・緑）
    "color8": ["#fcfcfc", "#000000", "#d82800", "#fc9838", "#7c3c00", "#2038ec", "#f8d878", "#00a800"],
    # 2ビットのグレースケール（白・明るい灰・暗い灰・黒）
    "gray4": ["#ffffff", "#aaaaaa", "#555555", "#000000"],
    # 1ビットの白黒
    "mono2": ["#ffffff", "#000000"],
}
DEFAULT_PALETTE = "color8"
PALETTE = PALETTES[DEFAULT_PALETTE]
DIGITS = "0123456789abcdef"


def _ncolors(g: dict) -> int:
    return len(g["pal"])


def encode(w: int, h: int, px: list[int], pal: list[str] = PALETTE) -> dict:
    return {"w": w, "h": h, "pal": pal, "px": "".join(DIGITS[i] for i in px)}


def decode(g: dict) -> tuple[int, int, list[int]]:
    return g["w"], g["h"], [DIGITS.index(c) for c in g["px"]]


def random_genome(rng: random.Random, res: int = DEFAULT_RES, pal: list[str] = PALETTE) -> dict:
    """砂嵐：全画素をランダムな色に。"""
    return encode(res, res, [rng.randrange(len(pal)) for _ in range(res * res)], pal)


def _rand_rect(rng: random.Random, w: int, h: int, lo: float, hi: float) -> tuple[int, int, int, int]:
    rw = max(1, round(w * rng.uniform(lo, hi)))
    rh = max(1, round(h * rng.uniform(lo, hi)))
    x0, y0 = rng.randrange(0, w - rw + 1), rng.randrange(0, h - rh + 1)
    return x0, y0, x0 + rw, y0 + rh


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """a の画像に、b の長方形の領域を貼り込む（位置はそのまま）。"""
    w, h, pa = decode(a)
    _, _, pb = decode(b)
    x0, y0, x1, y1 = _rand_rect(rng, w, h, 0.25, 0.75)
    for y in range(y0, y1):
        pa[y * w + x0:y * w + x1] = pb[y * w + x0:y * w + x1]
    return encode(w, h, pa, a["pal"])


def _point(px: list[int], n_colors: int, rng: random.Random, rate: float, model=None) -> None:
    """ランダムな画素の色を変える。model があれば、その画素で選ばれやすい色の確率で選ぶ。"""
    for _ in range(max(1, round(len(px) * rate))):
        i = rng.randrange(len(px))
        if model is not None:
            px[i] = model.sample(i, rng)
        else:
            px[i] = (px[i] + rng.randrange(1, n_colors)) % n_colors


def _repair(px: list[int], model, rng: random.Random, tries: int) -> None:
    """ランダムな画素で、モデルから引いた色の方が出やすければその色に直す（良い画素は壊さない）。"""
    dist = model.distribution()
    for _ in range(tries):
        i = rng.randrange(len(px))
        c = model.sample(i, rng)
        if dist[i][c] > dist[i][px[i]]:
            px[i] = c


def _majority(px: list[int], w: int, h: int, rng: random.Random) -> None:
    """長方形の領域の画素を、周り 3×3 で一番多い色に合わせる（砂嵐が落ち着いて塊になる）。"""
    x0, y0, x1, y1 = _rand_rect(rng, w, h, 0.15, 0.5)
    src = px[:]
    for y in range(y0, y1):
        for x in range(x0, x1):
            cnt = Counter(src[yy * w + xx]
                          for yy in range(max(0, y - 1), min(h, y + 2))
                          for xx in range(max(0, x - 1), min(w, x + 2)))
            top = cnt.most_common(1)[0]
            if top[1] >= 4:  # はっきり多い時だけ合わせる（細い線を消しすぎない）
                px[y * w + x] = top[0]


def _fill(px: list[int], w: int, h: int, n_colors: int, rng: random.Random, model=None) -> None:
    """小さな長方形を1色で塗る。model があれば、全体で選ばれやすい色ほど選ばれやすい。"""
    x0, y0, x1, y1 = _rand_rect(rng, w, h, 0.05, 0.25)
    c = model.sample_global(rng) if model is not None else rng.randrange(n_colors)
    for y in range(y0, y1):
        for x in range(x0, x1):
            px[y * w + x] = c


def _stroke(px: list[int], w: int, h: int, n_colors: int, rng: random.Random, model=None) -> None:
    """筆で短い線を引く（白なら消す）。太さ 1〜2 画素、長さ 3〜8 歩、少しずつ曲がる。"""
    c = model.sample_global(rng) if model is not None else rng.randrange(n_colors)
    x, y = rng.uniform(0, w - 1), rng.uniform(0, h - 1)
    ang = rng.uniform(0, 6.2832)
    thick = rng.choice((1, 2))
    for _ in range(rng.randint(3, 8)):
        for dy in range(thick):
            for dx in range(thick):
                xi, yi = round(x) + dx, round(y) + dy
                if 0 <= xi < w and 0 <= yi < h:
                    px[yi * w + xi] = c
        ang += rng.gauss(0, 0.5)
        x += math.cos(ang)
        y += math.sin(ang)


# 突然変異の強さ（シミュレーションで決めた値。README 参照）
POINT_RATE = 0.005
REPAIR_TRIES = 5
MAJORITY_P = 0.15
FILL_P = 0.3
STROKE_P = 0.3  # 筆の線


def mutate(g: dict, rng: random.Random, strength: float = 1.0, model=None) -> dict:
    """親を壊さずに突然変異した子を返す。必ずどこかは変わる。
    model（ColorModel）に集計があれば、変える色をその確率で選び、出やすい色への修正も入れる。"""
    w, h, px = decode(g)
    before = px[:]
    n = _ncolors(g)
    if model is not None and (model.events == 0 or (model.w, model.h, model.n) != (w, h, n)):
        model = None
    _point(px, n, rng, POINT_RATE * strength, model)
    if model is not None:
        _repair(px, model, rng, round(REPAIR_TRIES * strength))
    if rng.random() < MAJORITY_P * strength:
        _majority(px, w, h, rng)
    if rng.random() < FILL_P * strength:
        _fill(px, w, h, n, rng, model)
    if rng.random() < STROKE_P * strength:
        _stroke(px, w, h, n, rng, model)
    if px == before:  # 引いた色が元と同じだった等
        _point(px, n, rng, 0)
    return encode(w, h, px, g["pal"])


def is_valid(g: dict) -> bool:
    try:
        w, h, px = decode(g)
    except (KeyError, ValueError):
        return False
    return w > 0 and h > 0 and len(px) == w * h and all(0 <= i < _ncolors(g) for i in px)
