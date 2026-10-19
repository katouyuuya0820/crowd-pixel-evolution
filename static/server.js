// 管理画面
const $ = (id) => document.getElementById(id);
let shownGen = "";
let cells = new Map(); // 個体ID → {el, meta}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function setSummary(s) {
  const el = $("total");
  if (el.textContent !== String(s.total_votes)) {
    el.textContent = s.total_votes;
    const b = $("badge");
    b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump");
  }
  $("gen").textContent = `第${s.gen}世代`;
  $("sGen").textContent = s.gen;
  $("sGenVotes").textContent = s.gen_votes;
  $("sThr").textContent = s.threshold;
  $("sPart").textContent = s.participants;
  $("sSize").textContent = s.size;
  $("bar").style.width = `${Math.min(100, (s.gen_votes / s.threshold) * 100)}%`;
  $("topicShow").textContent = s.topic || "（未設定）";
  if (document.activeElement !== $("thrIn")) $("thrIn").value = s.threshold;
}

// 世代が変わったら画像を描き直し、同じ世代なら数字と順番だけ更新する
async function refresh() {
  const st = await api("/api/admin/state");
  setSummary(st);
  const pop = st.population;
  const genKey = `${st.session}:${st.gen}`;
  if (genKey !== shownGen) {
    shownGen = genKey;
    const grid = $("grid");
    grid.innerHTML = "";
    cells = new Map();
    const jobs = [];
    for (const ind of pop) {
      const el = document.createElement("div");
      el.className = "cell";
      const c = document.createElement("canvas");
      c.className = "art";
      c.width = c.height = 128;
      const meta = document.createElement("div");
      meta.className = "meta";
      el.append(c, meta);
      grid.append(el);
      cells.set(ind.id, { el, meta });
      jobs.push([ind.genome, c, 128]);
    }
    Pixel.renderQueue(jobs);
  }
  const grid = $("grid");
  pop.forEach((ind, i) => {
    const cell = cells.get(ind.id);
    if (!cell) return;
    cell.el.classList.toggle("rank1", i === 0);
    cell.meta.innerHTML = `<span>#${i + 1}</span><span>${ind.wins}/${ind.comps}・${(ind.fitness * 100).toFixed(0)}%</span>`;
    grid.append(cell.el); // 評価の順に並べ替え
  });
  if (st.model_best) {
    Pixel.render(st.model_best, $("model"));
    $("modelEvents").textContent = st.model_events;
    $("colors").innerHTML = st.model_colors.map((c) =>
      `<span style="display:inline-flex;align-items:center;gap:4px"><span style="width:14px;height:14px;border:1px solid #000;background:${c.color}"></span>×${c.lift.toFixed(2)}</span>`
    ).join("");
  }
  const best = pop[0];
  if (best && $("best").dataset.id !== best.id) {
    $("best").dataset.id = best.id;
    Pixel.render(best.genome, $("best"), 360);
  }
  if (best) {
    $("bestWC").textContent = `${best.wins} / ${best.comps}`;
    $("bestFit").textContent = `${(best.fitness * 100).toFixed(1)}%`;
  }
}

let refreshTimer = null;
function scheduleRefresh() { // 票が続けて来ても描画は間引く
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => { refreshTimer = null; refresh().catch(console.error); }, 300);
}

async function loadJoin() {
  const j = await api("/api/admin/join");
  if (!j.urls.length) return;
  $("url").textContent = j.urls[0];
  $("qr").src = `/api/admin/qr.svg?url=${encodeURIComponent(j.urls[0])}`;
  $("urlOthers").textContent = j.urls.length > 1 ? `ほかのIP：${j.urls.slice(1).join("  ")}` : "";
}

$("topicBtn").onclick = async () => setSummary(await api("/api/admin/topic", { topic: $("topicIn").value }));
$("topicIn").addEventListener("keydown", (e) => { if (e.key === "Enter") $("topicBtn").click(); });
$("thrBtn").onclick = async () => { setSummary(await api("/api/admin/threshold", { threshold: +$("thrIn").value })); scheduleRefresh(); };
$("advBtn").onclick = async () => { await api("/api/admin/advance", {}); scheduleRefresh(); };
$("resetBtn").onclick = async () => {
  if (!confirm("砂嵐からやり直します。よろしいですか？")) return;
  const thr = $("rthrIn").value ? +$("rthrIn").value : null;
  await api("/api/admin/reset", { size: +$("sizeIn").value, threshold: thr, res: +$("resIn").value, k: +$("kIn").value, palette: $("palIn").value });

  scheduleRefresh();
};

function connectWS() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    setSummary(msg.summary);
    if (msg.type === "gen" || msg.type === "vote") scheduleRefresh();
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

refresh().then(() => { $("topicIn").value = $("topicShow").textContent.startsWith("（") ? "" : $("topicShow").textContent; });
loadJoin().catch(console.error);
connectWS();
setInterval(() => api("/api/summary").then(setSummary).catch(() => {}), 10000); // 参加人数の更新
