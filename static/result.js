// リザルト画面：一定世代ごとにどんな画像が作られたかを並べる
const $ = (id) => document.getElementById(id);
let data = null;

function pickGens(history, k) {
  if (!history.length) return [];
  if (k === "auto") k = Math.max(1, Math.ceil(history.length / 12));
  const out = history.filter((h, i) => i % k === 0);
  const last = history[history.length - 1];
  if (out[out.length - 1] !== last) out.push(last); // 最後の世代は必ず入れる
  return out;
}

function fig(genome, size, caption) {
  const f = document.createElement("figure");
  const c = document.createElement("canvas");
  c.className = "art";
  c.width = c.height = size;
  f.append(c);
  if (caption) {
    const cap = document.createElement("figcaption");
    cap.textContent = caption;
    f.append(cap);
  }
  return [f, [genome, c, size]];
}

function draw() {
  const k = $("kSel").value === "auto" ? "auto" : +$("kSel").value;
  const gens = pickGens(data.history, k);
  const jobs = [];
  const strip = $("strip");
  const rows = $("rows");
  strip.innerHTML = "";
  rows.innerHTML = "";
  $("empty").style.display = gens.length ? "none" : "block";

  for (const h of gens) {
    const [f, job] = fig(h.top[0].genome, 110, `第${h.gen}世代`);
    strip.append(f);
    jobs.push(job);
  }
  for (const h of gens) {
    const row = document.createElement("div");
    row.className = "gen-row";
    const no = document.createElement("div");
    no.className = "gno";
    no.innerHTML = `第${h.gen}世代<small>${h.votes}票（累計${h.total_votes}）${h.topic ? "<br>お題：" + escapeHtml(h.topic) : ""}</small>`;
    const [bestFig, bestJob] = fig(h.top[0].genome, 220, `1位　${h.top[0].wins}/${h.top[0].comps}勝`);
    const others = document.createElement("div");
    others.className = "others";
    h.top.slice(1, 4).forEach((ind, i) => {
      const [f, job] = fig(ind.genome, 120, `${i + 2}位　${ind.wins}/${ind.comps}勝`);
      others.append(f);
      jobs.push(job);
    });
    row.append(no, bestFig, others);
    rows.append(row);
    jobs.push(bestJob);
  }
  Pixel.renderQueue(jobs);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function load() {
  data = await (await fetch("/api/history")).json();
  const s = data.summary;
  $("total").textContent = s.total_votes;
  $("gen").textContent = `現在 第${s.gen}世代・終わった世代 ${data.history.length}`;
  $("topic").textContent = s.topic || "（未設定）";
  draw();
}

$("kSel").onchange = draw;
$("reload").onclick = load;
load();
