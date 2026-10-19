import random

import pytest

from app import pixel
from app.ga import Population
from app.state import Game


def test_pixel_genome_ops_keep_shape():
    rng = random.Random(0)
    g = pixel.random_genome(rng, 16)
    other = pixel.random_genome(rng, 16)
    assert pixel.is_valid(g) and g["w"] == g["h"] == 16
    for _ in range(300):
        child = pixel.mutate(pixel.crossover(g, other, rng), rng)
        assert pixel.is_valid(child) and (child["w"], child["h"]) == (16, 16)
        assert child != g  # 必ずどこかは変わる
        g = child


def test_start_is_noise():
    _, _, px = pixel.decode(pixel.random_genome(random.Random(1), 16))
    counts = [px.count(c) for c in range(len(pixel.PALETTE))]
    assert min(counts) > 10  # 8色がまんべんなく出る砂嵐


def test_crossover_copies_a_rectangle():
    rng = random.Random(2)
    a = pixel.encode(8, 8, [0] * 64)
    b = pixel.encode(8, 8, [1] * 64)
    _, _, px = pixel.decode(pixel.crossover(a, b, rng))
    assert 0 < px.count(1) < 64


def test_sets_are_balanced():
    pop = Population(18, random.Random(3))
    for _ in range(60):
        shown = pop.pick_set(9)
        assert len({m["id"] for m in shown}) == 9
        pop.record_choice(shown[0]["id"], [m["id"] for m in shown])
    appear = [m["comps"] for m in pop.members]
    assert max(appear) - min(appear) <= 20


def test_choice_counts_as_wins_over_all_shown():
    pop = Population(6, random.Random(4))
    ids = [m["id"] for m in pop.members[:4]]
    assert pop.record_choice(ids[0], ids)
    assert pop.get(ids[0])["wins"] == 3 and pop.get(ids[0])["comps"] == 3
    assert all(pop.get(i)["comps"] == 1 and pop.get(i)["wins"] == 0 for i in ids[1:])
    assert not pop.record_choice("nope", ids)


def test_advance_by_threshold_and_stale_votes(tmp_path):
    game = Game(tmp_path, seed=5)
    game.reset(size=8, threshold=5, k=4)
    for _ in range(5):
        s = game.set_for("c1")
        assert len(s["items"]) == 4
        res = game.vote("c1", s["gen"], s["items"][0]["id"], [it["id"] for it in s["items"]])
        assert res["accepted"]
    assert game.pop.gen == 1 and res["advanced"]
    assert len(game.history) == 1 and game.history[0]["votes"] == 5
    stale = game.vote("c1", 0, s["items"][0]["id"], [it["id"] for it in s["items"]])
    assert not stale["accepted"] and game.total_votes == 5


def test_resume_from_disk(tmp_path):
    game = Game(tmp_path, seed=6)
    game.reset(size=8, threshold=3, k=4)
    game.set_topic("ハート")
    for _ in range(4):
        s = game.set_for("c1")
        game.vote("c1", s["gen"], s["items"][0]["id"], [it["id"] for it in s["items"]])
    again = Game(tmp_path, seed=7)
    assert again.topic == "ハート" and again.k == 4
    assert again.pop.gen == game.pop.gen == 1
    assert again.total_votes == 4 and len(again.history) == 1


def test_model_learns_preferred_color_and_white_for_unimportant():
    from app.model import ColorModel
    m = ColorModel(3, 3, 4)
    rng = random.Random(8)
    for _ in range(300):
        shown = [[rng.randrange(4) for _ in range(9)] for _ in range(6)]
        # 真ん中 (4) が 2（赤）の画像を選ぶ。ほかのピクセルは関係ない
        winner = next((p for p in shown if p[4] == 2), shown[0])
        m.record(winner, shown)
    d = m.distribution()
    assert max(range(4), key=d[4].__getitem__) == 2
    corner = d[0]  # 重要でないピクセルは、関係ない色(1, 3)より白(0)が少しだけ出やすい
    # （赤(2)は真ん中で好まれた分、全体の選ばれやすさで上がるので比べない）
    assert corner[0] > max(corner[1], corner[3]) and corner[0] < 0.6
    assert m.best()[4] == 2


def test_mutation_with_model_stays_valid(tmp_path):
    game = Game(tmp_path, seed=9)
    game.reset(size=8, threshold=3, k=4)
    for _ in range(20):
        s = game.set_for("c1")
        game.vote("c1", s["gen"], s["items"][0]["id"], [it["id"] for it in s["items"]])
    assert game.model.events == 20 and game.pop.gen > 0
    assert all(pixel.is_valid(m["genome"]) for m in game.pop.members)


def test_globally_unchosen_color_fades():
    from app.model import ColorModel
    m = ColorModel(4, 4, 4)
    rng = random.Random(10)
    before = m.distribution()[5][3]
    for _ in range(200):
        shown = [[rng.randrange(4) for _ in range(16)] for _ in range(6)]
        # 色3（例：緑）が一番少ない画像を選ぶ
        winner = min(shown, key=lambda p: p.count(3))
        m.record(winner, shown)
    assert m.global_lift()[3] < 0.8 < min(m.global_lift()[:3])
    assert m.distribution()[5][3] < before


@pytest.mark.parametrize("palette, n", [("gray4", 4), ("mono2", 2)])
def test_gray_modes(tmp_path, palette, n):
    game = Game(tmp_path, seed=11)
    game.reset(size=8, threshold=3, k=4, palette=palette, res=16)
    assert game.summary()["palette"] == palette
    for _ in range(10):
        s = game.set_for("c1")
        assert all(set(it["genome"]["px"]) <= set("0123"[:n]) for it in s["items"])
        game.vote("c1", s["gen"], s["items"][0]["id"], [it["id"] for it in s["items"]])
    assert game.model.n == n and len(game.admin_state()["model_colors"]) == n
    again = Game(tmp_path, seed=12)
    assert again.palette == palette and again.model.n == n
