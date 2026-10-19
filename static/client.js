// 学生の画面：並んだ画像から1枚をクリックで確定。矢印キーで枠を動かし Enter / Space でも確定
const $ = (id) => document.getElementById(id);

function getClientId() {
  let id = null;
  try { id = localStorage.getItem("hiec_client_id"); } catch (e) {}
  if (!id) {
    id = "c-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
    try { localStorage.setItem("hiec_client_id", id); } catch (e) {}
  }
  return id;
}
const clientId = getClientId();
const HINT = "";
let set = null;
let busy = false;
let cursor = -1; // キーボードで選んでいる位置（-1 = まだ使っていない）
let canvases = [];

function setSummary(s) {
  $("total").textContent = s.total_votes;
  $("gen").textContent = s.gen;
  $("topic").textContent = s.topic;
}

function cols(n) { return Math.ceil(Math.sqrt(n)); }

function drawCursor() {
  canvases.forEach((c, i) => c.classList.toggle("cur", i === cursor));
}

async function loadSet() {
  const r = await fetch(`/api/set?client_id=${encodeURIComponent(clientId)}`);
  set = await r.json();
  $("gen").textContent = set.gen;
  $("topic").textContent = set.topic;
  const grid = $("grid");
  grid.style.gridTemplateColumns = `repeat(${cols(set.items.length)}, 1fr)`;
  grid.innerHTML = "";
  canvases = set.items.map((item, i) => {
    const c = document.createElement("canvas");
    Pixel.render(item.genome, c);
    c.addEventListener("click", () => choose(i));
    grid.append(c);
    return c;
  });
  if (cursor >= canvases.length) cursor = canvases.length - 1;
  drawCursor();
  grid.classList.remove("busy");
  $("msg").textContent = HINT;
  busy = false;
}

async function choose(i) {
  if (busy || !set) return;
  busy = true;
  $("grid").classList.add("busy");
  try {
    await fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: clientId, gen: set.gen,
        winner: set.items[i].id, shown: set.items.map((it) => it.id),
      }),
    });
  } catch (e) {
    $("msg").textContent = "送信できませんでした";
  }
  loadSet().catch(retryLater);
}

function retryLater() {
  $("msg").textContent = "サーバーに接続できません。再接続しています…";
  setTimeout(() => loadSet().catch(retryLater), 2000);
}

document.addEventListener("keydown", (e) => {
  if (!canvases.length) return;
  const n = canvases.length, c = cols(n);
  const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -c, ArrowDown: c };
  if (e.key in moves) {
    e.preventDefault();
    if (cursor < 0) cursor = 0;
    else {
      const next = cursor + moves[e.key];
      if (next >= 0 && next < n) cursor = next;
    }
    drawCursor();
  } else if ((e.key === "Enter" || e.key === " ") && cursor >= 0 && !e.repeat) {
    e.preventDefault();
    choose(cursor);
  }
});

// WebSocket：みんなの選択数・お題・世代の変更をすぐ反映する
function connectWS() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    setSummary(msg.summary);
    // 世代が変わったら、見ている組は古いので取り直す
    if (msg.type === "gen" && set && msg.summary.gen !== set.gen && !busy) loadSet().catch(retryLater);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

connectWS();
loadSet().catch(retryLater);
