// ドット絵の遺伝子（{w, h, pal: [色], px: "0312..."}）を canvas に描く。拡大はドットのまま
const Pixel = (() => {
  const rgbCache = new Map();
  function rgb(hex) {
    if (!rgbCache.has(hex)) {
      const n = parseInt(hex.slice(1), 16);
      rgbCache.set(hex, [(n >> 16) & 255, (n >> 8) & 255, n & 255]);
    }
    return rgbCache.get(hex);
  }

  function render(genome, canvas) {
    const { w, h, pal, px } = genome;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const img = ctx.createImageData(w, h);
    const cols = pal.map(rgb);
    for (let i = 0, j = 0; i < w * h; i++) {
      const c = cols[parseInt(px[i], 16)];
      img.data[j++] = c[0]; img.data[j++] = c[1]; img.data[j++] = c[2]; img.data[j++] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  function renderQueue(jobs) {
    for (const [g, c] of jobs) render(g, c);
  }

  return { render, renderQueue };
})();
