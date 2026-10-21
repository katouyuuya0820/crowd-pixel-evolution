// ベスト画面：いまの集団で評価が一番高い画像だけを出す（お題は出さない）。右上に選択数と世代
const $ = (id) => document.getElementById(id);

function setSummary(s) {
  $("total").textContent = s.total_votes;
  $("gen").textContent = s.gen;
}

async function load() {
  const d = await (await fetch("/api/best")).json();
  if (d.genome) Pixel.render(d.genome, $("art"));
}

// 票が入る・世代が変わる・設定が変わるたびに描き直す
function connectWS() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    setSummary(JSON.parse(ev.data).summary);
    load();
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

load();
connectWS();
