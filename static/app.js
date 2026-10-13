const $ = (id) => document.getElementById(id);
const gallery = $("gallery"), msg = $("msg");
let mode = "generate";

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

const MODES = {
  generate: { label: "Prompt", button: "Generate", busy: "Generating…",
              placeholder: "a watercolour lighthouse on a rocky coast at dusk" },
  edit:     { label: "Edit instruction", button: "Edit photo", busy: "Editing…",
              placeholder: "change the dress to a red evening gown" },
  inpaint:  { label: "Prompt for the painted area", button: "Inpaint", busy: "Inpainting…",
              placeholder: "a red evening gown" },
  uncrop:   { label: "Describe the wider scene (optional)", button: "Uncrop", busy: "Uncropping…",
              placeholder: "a sunlit beach with palm trees and a boardwalk" },
  video:    { label: "Describe the motion", button: "Make video", busy: "Rendering video…",
              placeholder: "she slowly turns toward the camera and smiles, wind in her hair, slow push-in" },
};
// Don't mention the grey padding here: told to "fill the grey border", the model paints grey.
const UNCROP_DEFAULT = "Extend the photo outward, seamlessly continuing the scene, with the same " +
  "lighting, perspective, colours and photographic style.";

function setMode(m) {
  mode = m;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.mode === m));
  document.querySelectorAll("[data-modes]").forEach((el) => {
    el.hidden = !el.dataset.modes.split(" ").includes(m) || (el.id === "preview" && !photo);
  });
  $("promptLabel").textContent = MODES[m].label;
  $("prompt").placeholder = MODES[m].placeholder;
  $("go").textContent = MODES[m].button;
  $("photoLabel").textContent = m === "video" ? "Start photo (optional)" : "Photo";
  refreshModelOptions();
  showVideoSize();
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  setMode(t.dataset.mode);
  window.history.replaceState(null, "", "#" + t.dataset.mode);  // link straight to a tab
}));

// ---- model family (Generate picks; Edit/Inpaint/Uncrop use Qwen-Image; Video uses Wan) + LoRA ----
const FAMILIES = JSON.parse($("modelsData").textContent);
const VIDEO_NEGATIVE = JSON.parse($("videoNegative").textContent);
let shownFamily = null;

function family() { return mode === "generate" ? $("model").value : mode === "video" ? "wan" : "qwen"; }

function refreshModelOptions() {
  const fam = family();
  if (fam === shownFamily) return;
  shownFamily = fam;
  const m = FAMILIES[fam];
  for (const [id, files] of [["unet", m.unets], ["clip", m.clips]]) {
    $(id).innerHTML = "";
    for (const f of files) $(id).add(new Option(f, f));
  }
  $("steps").value = m.steps;
  $("cfg").value = m.cfg || 1;
  $("negativeBox").hidden = fam === "krea2";  // Krea 2 Turbo runs at cfg 1 with no negative
  $("negative").placeholder = fam === "wan" ? VIDEO_NEGATIVE : "blurry, low quality";
}
$("model").addEventListener("change", refreshModelOptions);
refreshModelOptions();

fetch("/api/loras").then((r) => r.json()).then((j) => {
  for (const f of j.loras || []) $("lora").add(new Option(f, f));
}).catch(() => {});

// ---- photo + mask painting (inpaint) ----
let photo = null;                                   // loaded HTMLImageElement
const photoCanvas = $("photoCanvas"), overlay = $("maskOverlay");
const maskCanvas = document.createElement("canvas"); // white = regenerate, black = keep
let painted = false, erasing = false, last = null;

// Same sizing rule as the TextEncodeQwenImage21 node: ~res x res pixels, multiples of 32.
function targetSize(img) {
  const res = +$("resolution").value || 1024, ratio = img.naturalWidth / img.naturalHeight;
  return [Math.max(32, Math.round(Math.sqrt(res * res * ratio) / 32) * 32),
          Math.max(32, Math.round(Math.sqrt(res * res / ratio) / 32) * 32)];
}

function copyCanvas(src) {
  const c = document.createElement("canvas");
  c.width = src.width; c.height = src.height;
  c.getContext("2d").drawImage(src, 0, 0);
  return c;
}

// (Re)size the canvases to the target size, keeping any mask already painted.
function layoutCanvases() {
  if (!photo) return;
  const [w, h] = targetSize(photo);
  const oldMask = painted ? copyCanvas(maskCanvas) : null;
  const oldOverlay = painted ? copyCanvas(overlay) : null;
  for (const c of [photoCanvas, overlay, maskCanvas]) { c.width = w; c.height = h; }
  photoCanvas.getContext("2d").drawImage(photo, 0, 0, w, h);
  const m = maskCanvas.getContext("2d");
  m.fillStyle = "#000"; m.fillRect(0, 0, w, h);
  if (oldMask) {
    m.drawImage(oldMask, 0, 0, w, h);
    overlay.getContext("2d").drawImage(oldOverlay, 0, 0, w, h);
  }
  $("canvasWrap").hidden = false;
}

function clearMask() {
  painted = false;
  layoutCanvases();
}

function strokeTo(e) {
  const r = overlay.getBoundingClientRect(), scale = overlay.width / r.width;
  const p = { x: (e.clientX - r.left) * scale, y: (e.clientY - r.top) * scale };
  const from = last || p;
  const size = +$("brush").value * scale;
  for (const [c, color] of [[maskCanvas, erasing ? "#000" : "#fff"], [overlay, "#ff3355"]]) {
    const ctx = c.getContext("2d");
    ctx.globalCompositeOperation = c === overlay && erasing ? "destination-out" : "source-over";
    ctx.strokeStyle = color; ctx.lineWidth = size; ctx.lineCap = ctx.lineJoin = "round";
    ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(p.x + 0.01, p.y); ctx.stroke();
    ctx.globalCompositeOperation = "source-over";
  }
  if (!erasing) painted = true;
  last = p;
}

overlay.addEventListener("pointerdown", (e) => { overlay.setPointerCapture(e.pointerId); last = null; strokeTo(e); });
overlay.addEventListener("pointermove", (e) => { if (e.buttons) strokeTo(e); });
overlay.addEventListener("pointerup", () => { last = null; });
$("clearMask").addEventListener("click", clearMask);
$("eraseToggle").addEventListener("click", () => {
  erasing = !erasing;
  $("eraseToggle").classList.toggle("active", erasing);
});
$("resolution").addEventListener("change", () => { layoutCanvases(); drawUncrop(); });

// ---- current photo (uploaded file or a result reused as input) + history ----
let photoBlob = null, photoName = "", history = [];

function loadPhoto(blob, name, { keepMask = false, remember = false } = {}) {
  if (remember && photoBlob) history.push({ blob: photoBlob, name: photoName });
  photoBlob = blob; photoName = name;
  if (!keepMask) painted = false;
  photo = null;
  const url = URL.createObjectURL(blob);
  $("preview").src = url;
  const img = new Image();
  img.onload = () => {
    photo = img;
    $("preview").hidden = !["edit", "video"].includes(mode);
    layoutCanvases();
    drawUncrop();
    showVideoSize();
  };
  img.src = url;
  $("photoRow").hidden = false;
  $("photoInfo").textContent = name + (history.length ? ` · ${history.length} earlier` : "");
  $("prevPhoto").hidden = !history.length;
}

$("image").addEventListener("change", () => {
  const file = $("image").files[0];
  if (!file) return;
  history = [];
  loadPhoto(file, file.name);
});

$("clearPhoto").addEventListener("click", () => {
  photo = null; photoBlob = null; photoName = ""; history = []; painted = false;
  $("image").value = "";
  $("photoRow").hidden = true; $("preview").hidden = true;
  $("canvasWrap").hidden = true; uncropCanvas.hidden = true;
  showVideoSize();
});

// ---- video size: a preset, or the photo's shape at about 832x480 (or 1280x704) pixels ----
function videoSize() {
  const v = $("vsize").value;
  if (!v.startsWith("match")) return v.split("x").map(Number);
  const area = v === "match-hd" ? 1280 * 704 : 832 * 480;
  if (!photo) return v === "match-hd" ? [1280, 704] : [832, 480];
  const ratio = photo.naturalWidth / photo.naturalHeight;
  const fit = (x) => Math.min(1280, Math.max(256, Math.round(x / 32) * 32));
  return [fit(Math.sqrt(area * ratio)), fit(Math.sqrt(area / ratio))];
}

function showVideoSize() {
  const [w, h] = videoSize();
  $("vsizeInfo").textContent = `${w}×${h}` + ($("vsize").value.startsWith("match") && !photo ? " (no photo: landscape)" : "");
}
$("vsize").addEventListener("change", showVideoSize);
if (MODES[location.hash.slice(1)]) setMode(location.hash.slice(1));

$("prevPhoto").addEventListener("click", () => {
  const prev = history.pop();
  if (prev) loadPhoto(prev.blob, prev.name, { keepMask: true });
});

const toBlob = (canvas) => new Promise((ok) => canvas.toBlob(ok, "image/png"));

// Mask as sent to ComfyUI: slightly feathered so the pasted-back edit blends in.
function maskBlob() {
  const c = document.createElement("canvas");
  c.width = maskCanvas.width; c.height = maskCanvas.height;
  const ctx = c.getContext("2d");
  ctx.filter = `blur(${Math.max(2, Math.round(c.width / 256))}px)`;
  ctx.drawImage(maskCanvas, 0, 0);
  return toBlob(c);
}

// ---- uncrop (outpaint): pad the photo, mask the new border, run the inpaint graph ----
const PADS = ["padL", "padR", "padT", "padB"];
const uncropCanvas = $("uncropCanvas");

// Layout of the expanded frame at output size (~resolution² px, multiples of 32).
function uncropGeometry() {
  if (!photo) return null;
  const [l, r, t, b] = PADS.map((id) => +$(id).value / 100);
  const w = photo.naturalWidth, h = photo.naturalHeight;
  const W0 = w * (1 + l + r), H0 = h * (1 + t + b);
  const res = +$("resolution").value || 1024, s = Math.sqrt((res * res) / (W0 * H0));
  const W = Math.max(32, Math.round((W0 * s) / 32) * 32), H = Math.max(32, Math.round((H0 * s) / 32) * 32);
  const k = Math.min(W / W0, H / H0);  // exact scale after rounding to 32
  let x = Math.round(l * w * k + (W - W0 * k) / 2), y = Math.round(t * h * k + (H - H0 * k) / 2);
  let x1 = x + Math.round(w * k), y1 = y + Math.round(h * k);
  // Sides that aren't extended sit flush with the canvas edge (a <1% stretch), so the
  // multiple-of-32 rounding never leaves a thin grey strip there.
  if (l === 0) x = 0;
  if (r === 0) x1 = W;
  if (t === 0) y = 0;
  if (b === 0) y1 = H;
  return { W, H, x, y, pw: x1 - x, ph: y1 - y, padded: l + r + t + b > 0 };
}

function paddedCanvas(g) {
  const c = document.createElement("canvas");
  c.width = g.W; c.height = g.H;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#808080"; ctx.fillRect(0, 0, g.W, g.H);
  ctx.drawImage(photo, g.x, g.y, g.pw, g.ph);
  return c;
}

function drawUncrop() {
  for (const id of PADS) $(id + "v").textContent = $(id).value + "%";
  const g = uncropGeometry();
  uncropCanvas.hidden = !g;
  if (!g) return;
  uncropCanvas.width = g.W; uncropCanvas.height = g.H;
  const ctx = uncropCanvas.getContext("2d");
  ctx.drawImage(paddedCanvas(g), 0, 0);
  ctx.setLineDash([12, 8]); ctx.lineWidth = Math.max(2, g.W / 300); ctx.strokeStyle = "#7c5cff";
  ctx.strokeRect(g.x, g.y, g.pw, g.ph);
}

// White over the new border, overlapping slightly into the photo so the seam is regenerated too.
// The keep-region is inset by `o` on extended sides and feathered across that band, so the
// regenerated seam fades into the original instead of meeting it at a hard line.
function uncropMask(g) {
  const o = Math.round(Math.min(g.pw, g.ph) * 0.04), blur = Math.max(2, Math.round(o / 2));
  const p = blur * 3;  // margin so the blur doesn't fade at the canvas edges
  const c = document.createElement("canvas");
  c.width = g.W + 2 * p; c.height = g.H + 2 * p;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
  ctx.fillStyle = "#000";
  const [l, r, t, b] = PADS.map((id) => +$(id).value > 0);
  // extended side: pull in by o; flush side: run the black past the edge into the margin
  const x0 = l ? g.x + o : -p, x1 = r ? g.x + g.pw - o : g.W + p;
  const y0 = t ? g.y + o : -p, y1 = b ? g.y + g.ph - o : g.H + p;
  ctx.fillRect(x0 + p, y0 + p, x1 - x0, y1 - y0);
  const out = document.createElement("canvas");
  out.width = g.W; out.height = g.H;
  const octx = out.getContext("2d");
  octx.filter = `blur(${blur}px)`;
  octx.drawImage(c, -p, -p);
  return toBlob(out);
}

function setPads(l, r, t, b) {
  [l, r, t, b].forEach((v, i) => { $(PADS[i]).value = Math.round(v * 100); });
  drawUncrop();
}

$("aspect").addEventListener("change", () => {
  const v = $("aspect").value;
  if (!v || !photo) return;
  if (v.startsWith("zoom")) {
    const e = (v === "zoom2" ? 2 : 1.5) - 1;
    return setPads(e / 2, e / 2, e / 2, e / 2);
  }
  const target = +v, ratio = photo.naturalWidth / photo.naturalHeight;
  if (target >= ratio) {
    const e = target / ratio - 1;   // extra width as a fraction of the photo's width
    setPads(e / 2, e / 2, 0, 0);
  } else {
    const e = ratio / target - 1;   // extra height as a fraction of the photo's height
    setPads(0, 0, e / 2, e / 2);
  }
});
for (const id of PADS) $(id).addEventListener("input", () => { $("aspect").value = ""; drawUncrop(); });

// ---- prompt enhancer (local LLM via /api/enhance) ----
let beforeEnhance = null;

$("randomSeed").addEventListener("click", () => {
  $("seed").value = Math.floor(Math.random() * 2 ** 32);
});

$("enhance").addEventListener("click", async () => {
  const prompt = $("prompt").value.trim();
  if (!prompt) { msg.className = "err"; msg.textContent = "Type a prompt to enhance first."; return; }
  const btn = $("enhance");
  btn.disabled = true; btn.textContent = "✨ thinking…";
  msg.className = ""; msg.textContent = "";
  try {
    const r = await fetch("/api/enhance", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    beforeEnhance = $("prompt").value;
    $("prompt").value = j.prompt;
    $("undoEnhance").hidden = false;
  } catch (err) {
    msg.className = "err"; msg.textContent = err.message;
  } finally {
    btn.disabled = false; btn.textContent = "✨ Enhance";
  }
});

$("undoEnhance").addEventListener("click", () => {
  if (beforeEnhance !== null) $("prompt").value = beforeEnhance;
  beforeEnhance = null;
  $("undoEnhance").hidden = true;
});

// ---- results ----
// The × in a card's corner: removes the card, and tells the server to forget it (`forget`
// is the DELETE URL, if any) so it doesn't come back on reload.
function closeButton(card, forget, title = "Remove from the gallery (the file stays in output/)") {
  const close = document.createElement("button");
  close.type = "button"; close.className = "card-close"; close.innerHTML = "&times;";
  close.title = title;
  close.addEventListener("click", () => {
    card.remove();
    if (!gallery.children.length) gallery.innerHTML = '<div class="empty">Generated images and videos will appear here.</div>';
    if (forget) fetch(forget, { method: "DELETE" }).catch(() => {});
  });
  return close;
}

function resultCards(j, job) {
  return j.images.map((img) => {
    const card = document.createElement("div");
    card.className = "card";
    const close = closeButton(card, `/api/jobs/${job}?image=${encodeURIComponent(img.filename)}`);
    const isVideo = img.video || /\.(mp4|webm|mkv)$/i.test(img.filename);
    const image = document.createElement(isVideo ? "video" : "img");
    image.src = isVideo ? img.url : img.data;
    if (isVideo) Object.assign(image, { controls: true, loop: true, muted: true, autoplay: true, playsInline: true });
    else image.alt = "result";
    const meta = document.createElement("div");
    meta.className = "meta";
    const seed = document.createElement("button");
    seed.type = "button"; seed.className = "link seed"; seed.textContent = "seed " + j.seed;
    seed.title = "Use this seed for the next run";
    seed.addEventListener("click", () => { $("seed").value = j.seed; });
    const actions = document.createElement("span");
    actions.className = "actions";
    const reuse = document.createElement("button");
    reuse.type = "button"; reuse.className = "link"; reuse.textContent = "use as photo";
    reuse.title = "Keep editing this result (the previous photo stays in history)";
    reuse.addEventListener("click", async () => {
      const blob = await (await fetch(img.data)).blob();
      if (mode === "generate") setMode("edit");
      loadPhoto(blob, img.filename, { keepMask: true, remember: true });
    });
    const dl = document.createElement("a");
    dl.href = img.url; dl.download = img.filename; dl.textContent = "download";
    if (isVideo) actions.append(dl);
    else actions.append(reuse, dl);
    meta.append(seed, actions);
    card.append(close, image, meta);
    return card;
  });
}

// ---- job cards: every submit queues a job; ComfyUI runs them one after another ----
// The server keeps each browser's jobs (tagged with this id), so reopening the page
// brings back running jobs and finished results.
const clientId = (() => {
  const fresh = Date.now().toString(36) + Math.random().toString(36).slice(2);
  try {
    let id = localStorage.getItem("clientId");
    if (!id) localStorage.setItem("clientId", (id = fresh));
    return id;
  } catch { return fresh; }
})();
const FINISHED = ["done", "failed", "cancelled"];

function jobCard(kind, prompt) {
  const card = document.createElement("div");
  card.className = "card job";
  card.innerHTML =
    '<div class="job-body"><div class="spinner"></div>' +
    '<div class="job-kind"></div><div class="job-prompt"></div>' +
    '<div class="job-label">Uploading…</div>' +
    '<div class="progress"><div></div></div>' +
    '<button type="button" class="small job-cancel">Cancel</button></div>';
  card.querySelector(".job-kind").textContent = kind;
  card.querySelector(".job-prompt").textContent = prompt;
  return card;
}

function showProgress(card, busy, p) {
  const label = card.querySelector(".job-label"), bar = card.querySelector(".progress > div");
  if (p.max) {
    const pct = Math.round((100 * p.value) / p.max);
    bar.style.width = pct + "%";
    label.textContent = `${busy} step ${p.value}/${p.max} — ${pct}%`;
  } else if (p.state === "queued") {
    label.textContent = p.ahead ? `Queued — ${p.ahead} job${p.ahead > 1 ? "s" : ""} ahead` : "Queued — starting next";
  } else {
    label.textContent = p.state === "running" ? (p.phase || "Working") + "…" : p.state === "starting" ? "Uploading…" : busy;
  }
}

function noteCard(text, isError, job) {
  const note = document.createElement("div");
  note.className = "card job" + (isError ? " failed" : "");
  const body = document.createElement("div");
  body.className = "job-body";
  body.textContent = text;
  note.append(closeButton(note, job && "/api/jobs/" + job, "Remove from the gallery"), body);
  return note;
}

async function buildRequest(prompt, job) {
  const common = {
    prompt, job, client: clientId,
    negative: $("negative").value,
    steps: +$("steps").value, cfg: +$("cfg").value,
    seed: $("seed").value === "" ? null : +$("seed").value,
    unet: $("unet").value, clip: $("clip").value,
    lora: $("lora").value || null,
    lora_strength: $("lora").value ? +$("loraStrength").value : null,
  };
  if (mode === "generate") {
    return ["/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...common,
        model: $("model").value,
        width: +$("width").value, height: +$("height").value, batch: +$("batch").value,
      }),
    }];
  }
  const form = new FormData();
  for (const [k, v] of Object.entries(common)) if (v !== null) form.append(k, v);
  if (mode === "edit") {
    form.append("image", photoBlob, photoName);
    form.append("resolution", $("resolution").value);
    return ["/api/edit", { method: "POST", body: form }];
  }
  if (mode === "video") {
    const [w, h] = videoSize();
    form.append("width", w); form.append("height", h);
    form.append("frames", $("frames").value);
    if (photoBlob) form.append("image", photoBlob, photoName);
    return ["/api/video", { method: "POST", body: form }];
  }
  const name = photoName.replace(/\.[^.]+$/, "") + ".png";
  if (mode === "uncrop") {
    const g = uncropGeometry();
    form.append("image", await toBlob(paddedCanvas(g)), name);
    form.append("mask", await uncropMask(g), "mask.png");
    form.append("reference", photoBlob, photoName);  // unpadded: the model must not see the grey
    form.append("kind", "uncrop");
    return ["/api/inpaint", { method: "POST", body: form }];
  }
  form.append("image", await toBlob(photoCanvas), name);
  form.append("mask", await maskBlob(), "mask.png");
  form.append("denoise", $("denoise").value);
  return ["/api/inpaint", { method: "POST", body: form }];
}

// Enter in the prompt boxes runs the current tab; Shift+Enter adds a new line.
for (const id of ["prompt", "negative"]) {
  $(id).addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $("form").requestSubmit();
    }
  });
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  let prompt = $("prompt").value.trim();
  const fail = (text) => { msg.className = "err"; msg.textContent = text; };
  if (!["generate", "video"].includes(mode) && !photoBlob) return fail("Choose a photo first.");
  if (mode === "inpaint" && !painted) return fail("Paint over the area to change first.");
  if (mode === "uncrop") {
    if (!uncropGeometry()?.padded) return fail("Pick an aspect ratio or drag a slider to add canvas first.");
    prompt = prompt ? `${UNCROP_DEFAULT} The wider scene: ${prompt}` : UNCROP_DEFAULT;
  }
  if (!prompt) return fail(mode === "edit" ? "Enter an edit instruction first." : "Enter a prompt first.");
  msg.className = ""; msg.textContent = "";

  // Snapshot everything now, so changing the form afterwards doesn't affect this job.
  const job = Date.now().toString(36) + Math.random().toString(36).slice(2);
  const busy = MODES[mode].busy;
  const request = await buildRequest(prompt, job);

  const card = jobCard(MODES[mode].button, prompt);
  addToGallery(card);
  const stop = trackJob(card, job, busy);

  try {
    const r = await fetch(...request);
    const j = await r.json();
    stop();
    if (j.cancelled) return card.replaceWith(noteCard("Cancelled: " + prompt, false, job));
    if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    if (!j.images.length) throw new Error("ComfyUI finished without a result (check its console).");
    card.replaceWith(...resultCards(j, job));
  } catch (err) {
    stop();
    card.replaceWith(noteCard("Failed: " + err.message, true, job));
  }
});

function addToGallery(card) {
  const empty = gallery.querySelector(".empty");
  if (empty) empty.remove();
  gallery.prepend(card);
}

// Wire a job card's Cancel button and poll its progress. Normally the caller waits on
// the request itself and swaps the card; for a job `restored` from the server, the
// poll swaps in the result once the server records the end.
// Returns a function that stops the polling.
function trackJob(card, job, busy, restored = false) {
  const cancel = card.querySelector(".job-cancel");
  cancel.addEventListener("click", async () => {
    cancel.disabled = true; cancel.textContent = "Cancelling…";
    try {
      const r = await fetch("/api/cancel/" + job, { method: "POST" });
      if (!r.ok) throw new Error((await r.json()).error || ("HTTP " + r.status));
    } catch (err) {
      card.querySelector(".job-label").textContent = err.message;
      cancel.disabled = false; cancel.textContent = "Cancel";
    }
  });

  const poll = setInterval(async () => {
    try {
      const p = await (await fetch("/api/progress/" + job)).json();
      if (restored && (FINISHED.includes(p.state) || p.state === "unknown")) {
        clearInterval(poll);
        return card.replaceWith(...finishedCards(p));
      }
      showProgress(card, busy, p);
    } catch {}
  }, 1000);
  return () => clearInterval(poll);
}

// Cards for a job the server has finished (or forgotten, e.g. after a restart).
function finishedCards(p) {
  if (p.state === "done" && p.result.images.length)
    return resultCards({ ...p.result, images: p.result.images.map((img) => ({ ...img, data: img.url })) }, p.id);
  if (p.state === "cancelled") return [noteCard("Cancelled: " + p.prompt, false, p.id)];
  if (p.state === "unknown") return [noteCard("Lost track of this job (the server restarted).", true, p.id)];
  return [noteCard("Failed: " + (p.error || "ComfyUI finished without an image (check its console)."), true, p.id)];
}

// Rebuild the gallery from the jobs this browser sent before the page was (re)opened.
(async () => {
  try {
    const { jobs } = await (await fetch("/api/jobs?client=" + encodeURIComponent(clientId))).json();
    for (const p of jobs.reverse()) {  // oldest first, so the newest ends up on top
      if (FINISHED.includes(p.state)) {
        for (const card of finishedCards(p).reverse()) addToGallery(card);
      } else {
        const m = MODES[p.kind] || MODES.generate;
        const card = jobCard(m.button, p.prompt);
        addToGallery(card);
        showProgress(card, m.busy, p);
        trackJob(card, p.id, m.busy, true);
      }
    }
  } catch {}
})();
