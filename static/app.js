const $ = (id) => document.getElementById(id);
const gallery = $("gallery"), msg = $("msg");

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    const up = j.comfy === "up";
    $("dot").className = "dot " + (up ? "up" : "down");
    $("statusText").textContent = up ? "ComfyUI connected" : "ComfyUI offline (" + j.server + ")";
  } catch {
    $("dot").className = "dot down";
    $("statusText").textContent = "server unreachable";
  }
}
checkHealth();
setInterval(checkHealth, 15000);

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) { msg.className = "err"; msg.textContent = "Enter a prompt first."; return; }

  const payload = {
    prompt,
    negative: $("negative").value,
    width: +$("width").value, height: +$("height").value,
    steps: +$("steps").value, cfg: +$("cfg").value, batch: +$("batch").value,
    seed: $("seed").value === "" ? null : +$("seed").value,
    unet: $("unet").value, clip: $("clip").value,
  };

  $("go").disabled = true;
  msg.className = ""; msg.textContent = "";
  gallery.innerHTML = '<div class="empty"><div class="spinner"></div>Generating… this can take a while on first run.</div>';

  try {
    const r = await fetch("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));

    gallery.innerHTML = "";
    for (const img of j.images) {
      const card = document.createElement("div");
      card.className = "card";
      const image = document.createElement("img");
      image.src = img.data; image.alt = "result";
      const meta = document.createElement("div");
      meta.className = "meta";
      const seed = document.createElement("span");
      seed.textContent = "seed " + j.seed;
      const dl = document.createElement("a");
      dl.href = img.url; dl.download = img.filename; dl.textContent = "download";
      meta.append(seed, dl);
      card.append(image, meta);
      gallery.appendChild(card);
    }
    msg.className = ""; msg.textContent = "Done — prompt " + j.prompt_id + ", seed " + j.seed + ".";
  } catch (err) {
    gallery.innerHTML = '<div class="empty">Nothing generated.</div>';
    msg.className = "err"; msg.textContent = err.message;
  } finally {
    $("go").disabled = false;
  }
});
