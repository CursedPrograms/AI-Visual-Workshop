const $ = (id) => document.getElementById(id);
const gallery = $("gallery"), msg = $("msg");
const EMPTY_GALLERY = gallery.innerHTML;  // the welcome card, put back when the gallery empties
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
  generate: { label: "Prompt", button: "Generate", busy: "Generating…", icon: "✦",
              desc: "Text to image: Qwen-Image 2.1, Krea 2 Turbo, SDXL or Chroma.",
              placeholder: "a watercolour lighthouse on a rocky coast at dusk" },
  edit:     { label: "Edit instruction", button: "Edit photo", busy: "Editing…", icon: "✎",
              desc: "Describe the change; everything you don't mention stays.",
              placeholder: "change the dress to a red evening gown" },
  inpaint:  { label: "Prompt for the painted area", button: "Inpaint", busy: "Inpainting…", icon: "◐",
              desc: "Paint a mask and regenerate only that part.",
              placeholder: "a red evening gown" },
  uncrop:   { label: "Describe the wider scene (optional)", button: "Uncrop", busy: "Uncropping…", icon: "⤢",
              desc: "Extend the photo past its borders.",
              placeholder: "a sunlit beach with palm trees and a boardwalk" },
  pose:     { label: "Describe the new picture", button: "Generate in this pose", busy: "Posing…", icon: "🕺",
              desc: "Finds the pose in a photo (SDPose) and draws something new in exactly that pose.",
              placeholder: "an astronaut in a white spacesuit on the moon, cinematic light" },
  background: { label: "Describe the new background", button: "Remove background", busy: "Cutting out…", icon: "✂",
              desc: "Cut out the subject (transparent PNG), or give it a new background.",
              placeholder: "a sunlit beach at golden hour, palm trees, soft bokeh" },
  relight:  { label: "Describe the light", button: "Relight", busy: "Relighting…", icon: "☀",
              desc: "Change the lighting of a photo; people, pose and composition stay.",
              placeholder: "warm golden-hour sunlight from the left, long soft shadows" },
  upscale:  { label: "", button: "Upscale", busy: "Upscaling…", icon: "⇱",
              desc: "Enlarge a photo 2× or 4× with real added detail.", placeholder: "" },
  video:    { label: "Describe the motion", button: "Make video", busy: "Rendering video…", icon: "▶",
              desc: "Bring a photo to life, or make a clip from text (Wan 2.2).",
              placeholder: "she slowly turns toward the camera and smiles, wind in her hair, slow push-in" },
  videofx:  { label: "", button: "Apply to video", busy: "Processing video…", icon: "◎",
              desc: "Smooth a video (RIFE in-between frames) or remove its background.", placeholder: "" },
};
const NEEDS_PHOTO = ["edit", "inpaint", "uncrop", "pose", "background", "relight", "upscale"];
// Don't mention the grey padding here: told to "fill the grey border", the model paints grey.
const UNCROP_DEFAULT = "Extend the photo outward, seamlessly continuing the scene, with the same " +
  "lighting, perspective, colours and photographic style.";

function setMode(m) {
  mode = m;
  $("modeSelect").value = m;
  $("modeIcon").textContent = MODES[m].icon;
  $("modeDesc").textContent = MODES[m].desc;
  document.querySelectorAll("[data-modes]").forEach((el) => {
    el.hidden = !el.dataset.modes.split(" ").includes(m) || (el.id === "preview" && !photo);
  });
  document.querySelectorAll("[data-not-modes]").forEach((el) => {
    el.hidden = el.dataset.notModes.split(" ").includes(m);
  });
  $("promptLabel").textContent = MODES[m].label;
  $("prompt").placeholder = MODES[m].placeholder;
  $("go").textContent = MODES[m].button;
  $("photoLabel").textContent = { video: "Start photo (optional)", pose: "Pose photo" }[m] || "Photo";
  updateSubModes();
  refreshModelOptions();
  showVideoSize();
}
$("modeSelect").addEventListener("change", () => {
  setMode($("modeSelect").value);
  window.history.replaceState(null, "", "#" + mode);  // link straight to a tool
});

// ---- collapsible panel and sections (remembered per browser) ----
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const sectionState = store.get("sections") || {};
document.querySelectorAll("details.section").forEach((d) => {
  const key = d.dataset.section;
  if (key in sectionState) d.open = sectionState[key];
  d.addEventListener("toggle", () => { sectionState[key] = d.open; store.set("sections", sectionState); });
});
function setPanel(collapsed) {
  $("layout").classList.toggle("collapsed", collapsed);
  $("expandPanel").hidden = !collapsed;
  store.set("panelCollapsed", collapsed);
}
$("collapsePanel").addEventListener("click", () => setPanel(true));
$("expandPanel").addEventListener("click", () => setPanel(false));
if (store.get("panelCollapsed")) setPanel(true);

// Background: remove (no prompt, no model) or replace (prompt + Qwen-Image settings).
let bgMode = "remove", fxMode = "smooth";
function updateSubModes() {
  const removing = mode === "background" && bgMode === "remove";
  for (const key of ["prompt", "settings", "models"])
    document.querySelector(`[data-section="${key}"]`).hidden =
      removing || ["upscale", "videofx"].includes(mode);
  if (mode === "background") {
    $("go").textContent = removing ? "Remove background" : "Replace background";
    $("bgHint").textContent = removing ? "Cuts out the subject as a transparent PNG (BiRefNet)."
      : "Keeps the subject exactly and paints a new background around it (BiRefNet + Qwen-Image).";
  }
  $("fxSmooth").hidden = fxMode !== "smooth";
  $("fxBg").hidden = fxMode !== "remove_bg";
}
function segment(id, attr, set) {
  document.querySelectorAll(`#${id} .seg-btn`).forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(`#${id} .seg-btn`).forEach((x) => x.classList.toggle("active", x === b));
    set(b.dataset[attr]);
    updateSubModes();
  }));
}
segment("bgSeg", "bg", (v) => { bgMode = v; });
segment("fxSeg", "fx", (v) => { fxMode = v; });
let upscaleQuality = "fast";
segment("qualitySeg", "quality", (v) => { upscaleQuality = v; });

// Video FX input.
let videoBlob = null, videoName = "";
function loadVideo(file) {
  videoBlob = file; videoName = file.name;
  $("videoPreview").src = URL.createObjectURL(file);
  $("videoPreview").hidden = false;
}
$("videoFile").addEventListener("change", () => { if ($("videoFile").files[0]) loadVideo($("videoFile").files[0]); });
const vdrop = $("videoDrop");
vdrop.addEventListener("dragover", (e) => { e.preventDefault(); vdrop.classList.add("over"); });
vdrop.addEventListener("dragleave", () => vdrop.classList.remove("over"));
vdrop.addEventListener("drop", (e) => {
  e.preventDefault(); vdrop.classList.remove("over");
  const file = [...e.dataTransfer.files].find((f) => f.type.startsWith("video/"));
  if (file) loadVideo(file);
});

// Upscale factor (2x / 4x segmented control).
document.querySelectorAll("#scaleSeg .seg-btn").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#scaleSeg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  $("scale").value = b.dataset.scale;
}));

// ---- model family (Generate picks; Edit/Inpaint/Uncrop use Qwen-Image; Video uses Wan) + LoRA ----
const FAMILIES = JSON.parse($("modelsData").textContent);
const VIDEO_NEGATIVE = JSON.parse($("videoNegative").textContent);
let shownFamily = null;

function family() { return mode === "generate" ? $("model").value : mode === "video" ? $("videoModel").value : "qwen"; }

function refreshModelOptions() {
  const fam = family();
  if (fam === shownFamily) return;
  shownFamily = fam;
  const m = FAMILIES[fam];
  for (const [id, files] of [["unet", m.unets], ["clip", m.clips]]) {
    $(id).innerHTML = "";
    for (const f of files) $(id).add(new Option(f, f));
  }
  $("clipBox").hidden = !m.clips.length;  // SDXL checkpoints carry their own encoders
  $("steps").value = m.steps;
  $("cfg").value = m.cfg || 1;
  applyPreset();
  $("negativeBox").hidden = fam === "krea2";  // Krea 2 Turbo runs at cfg 1 with no negative
  $("negative").placeholder = fam.startsWith("wan") ? VIDEO_NEGATIVE : "blurry, low quality";
  // Video length labels follow the model's frame rate (Wan 5B: 24 fps, face model: 16 fps).
  const fps = m.fps || 24;
  for (const o of $("frames").options) o.textContent = `${+((o.value - 1) / fps).toFixed(1)} s`;
  $("videoHint").textContent = fam === "wanface"
    ? "(test) Needs a start photo. Best for faces and keeping the person's identity. 16 fps."
    : "With a photo it comes to life; without one the video comes from the prompt alone. 24 fps.";
}
// Some checkpoints need other steps / CFG than their family's default (e.g. non-Lightning SDXL).
function applyPreset() {
  const m = FAMILIES[shownFamily], preset = (m.presets || {})[$("unet").value];
  $("steps").value = preset ? preset.steps : m.steps;
  $("cfg").value = preset ? preset.cfg : (m.cfg || 1);
}
$("unet").addEventListener("change", applyPreset);
$("model").addEventListener("change", refreshModelOptions);
$("videoModel").addEventListener("change", refreshModelOptions);
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
    $("preview").hidden = !["edit", "video", "pose", "upscale", "background", "relight"].includes(mode);
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

// Drop a photo onto the picker.
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  const file = [...e.dataTransfer.files].find((f) => f.type.startsWith("image/"));
  if (file) { history = []; loadPhoto(file, file.name); }
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
setMode(MODES[location.hash.slice(1)] ? location.hash.slice(1) : "generate");

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
    if (!gallery.children.length) gallery.innerHTML = EMPTY_GALLERY;
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
    else {
      image.alt = "result";
      image.addEventListener("click", () => openLightbox(img.url));
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const seed = document.createElement("button");
    seed.type = "button"; seed.className = "link seed"; seed.textContent = "seed " + j.seed;
    seed.title = "Use this seed for the next run";
    seed.addEventListener("click", () => { $("seed").value = j.seed; });
    if (j.seed == null) seed.hidden = true;
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
    const up = document.createElement("button");
    up.type = "button"; up.className = "link"; up.textContent = "upscale";
    up.title = "Enlarge 2× with 4x-UltraSharp";
    up.addEventListener("click", async () => {
      const blob = await (await fetch(img.data)).blob();
      const job = newJobId(), form = new FormData();
      form.append("image", blob, img.filename);
      form.append("scale", 2); form.append("job", job); form.append("client", clientId);
      runJob(job, "upscale", `${img.filename} ×2`, ["/api/upscale", { method: "POST", body: form }]);
    });
    const cut = document.createElement("button");
    cut.type = "button"; cut.className = "link"; cut.textContent = "cut out";
    cut.title = "Remove the background (transparent PNG)";
    cut.addEventListener("click", async () => {
      const blob = await (await fetch(img.data)).blob();
      const job = newJobId(), form = new FormData();
      form.append("image", blob, img.filename);
      form.append("mode", "remove"); form.append("job", job); form.append("client", clientId);
      runJob(job, "background", `${img.filename}: remove background`, ["/api/background", { method: "POST", body: form }]);
    });
    const smooth = document.createElement("button");
    smooth.type = "button"; smooth.className = "link"; smooth.textContent = "smooth";
    smooth.title = "Double the frame rate with RIFE in-between frames";
    smooth.addEventListener("click", async () => {
      const blob = await (await fetch(img.url)).blob();
      const job = newJobId();
      runJob(job, "videofx", `${img.filename} ×2 smooth`, videoFxRequest(blob, img.filename, job, "smooth", 2));
    });
    if (isVideo) actions.append(smooth, dl);
    else actions.append(reuse, up, cut, dl);
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
  if (card.classList.contains("stopping")) {
    // GGUF models (Qwen, Wan) can only be stopped between sampler steps, and one step of a
    // long video can take a long time on a 6 GB card, so say what's happening.
    label.textContent = p.state === "running"
      ? "Stopping… ComfyUI stops after the step it's on — on a long video that can take a while."
      : "Removing it from the queue…";
    return;
  }
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
  note.className = "card job note" + (isError ? " failed" : "");
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
  if (mode === "pose") {
    form.append("image", photoBlob, photoName);
    form.append("resolution", $("resolution").value);
    return ["/api/pose", { method: "POST", body: form }];
  }
  if (mode === "upscale") {
    form.append("image", photoBlob, photoName);
    form.append("scale", $("scale").value);
    form.append("quality", upscaleQuality);
    return ["/api/upscale", { method: "POST", body: form }];
  }
  if (mode === "relight") {
    form.append("image", photoBlob, photoName);
    form.append("resolution", $("resolution").value);
    form.append("kind", "relight");
    return ["/api/edit", { method: "POST", body: form }];
  }
  if (mode === "background") {
    form.append("mode", bgMode);
    // replace inpaints, so it needs the photo at multiples of 32 (the inpaint canvas size)
    if (bgMode === "replace") form.append("image", await toBlob(photoCanvas), photoName.replace(/\.[^.]+$/, "") + ".png");
    else form.append("image", photoBlob, photoName);
    return ["/api/background", { method: "POST", body: form }];
  }
  if (mode === "videofx") return videoFxRequest(videoBlob, videoName, job, fxMode);
  if (mode === "video") {
    const [w, h] = videoSize();
    form.append("width", w); form.append("height", h);
    form.append("frames", $("frames").value);
    form.append("model", $("videoModel").value);
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
  if (NEEDS_PHOTO.includes(mode) && !photoBlob) return fail("Choose a photo first.");
  if (mode === "video" && $("videoModel").value === "wanface" && !photoBlob)
    return fail("The face video model (test) needs a start photo.");
  if (mode === "video" && $("videoModel").value === "wanface" && !confirmLongFaceVideo()) return;
  if (mode === "inpaint" && !painted) return fail("Paint over the area to change first.");
  if (mode === "uncrop") {
    if (!uncropGeometry()?.padded) return fail("Pick an aspect ratio or drag a slider to add canvas first.");
    prompt = prompt ? `${UNCROP_DEFAULT} The wider scene: ${prompt}` : UNCROP_DEFAULT;
  }
  if (mode === "upscale") prompt = `${photoName} ×${$("scale").value}`;
  if (mode === "background" && bgMode === "remove") prompt = `${photoName}: remove background`;
  if (mode === "videofx") {
    if (!videoBlob) return fail("Choose a video first.");
    prompt = fxMode === "smooth" ? `${videoName} ×${$("multiplier").value} smooth` : `${videoName}: remove background`;
  }
  if (!prompt) return fail(mode === "edit" ? "Enter an edit instruction first." : "Enter a prompt first.");
  msg.className = ""; msg.textContent = "";

  // Snapshot everything now, so changing the form afterwards doesn't affect this job.
  const job = newJobId();
  runJob(job, mode, prompt, await buildRequest(prompt, job));
});

function videoFxRequest(blob, name, job, effect, multiplier = $("multiplier").value) {
  const form = new FormData();
  form.append("video", blob, name);
  form.append("effect", effect);
  form.append("multiplier", multiplier);
  form.append("color", $("fxColor").value);
  form.append("job", job); form.append("client", clientId);
  return ["/api/videofx", { method: "POST", body: form }];
}

// The 14B face model's cost grows much faster than its size (attention over all frames,
// then spilling out of a 6 GB card). Measured on an RTX 2060: 480×832 × 49 frames (20k
// tokens) ~6 min; 640×640 × 121 (50k) ~4 h. A power law through both: time ∝ size^4.1.
function confirmLongFaceVideo() {
  const [w, h] = videoSize(), frames = +$("frames").value;
  const tokens = ((frames - 1) / 4 + 1) * (w / 16) * (h / 16), ref = 13 * 30 * 52;
  if (tokens <= ref * 1.3) return true;
  const ratio = tokens / ref;
  const minutes = Math.round(6 * Math.pow(ratio, 4.1));
  const guess = minutes >= 90 ? `${Math.round(minutes / 60)} hours or more` : `${minutes} minutes or more`;
  return confirm(`This face video is ${ratio.toFixed(1)}× the size of a 3-second 480×832 clip (about 6 min).

` +
    `On a 6 GB card it may take ${guess}, and once it's running it can only stop between steps.

` +
    `Tip: pick 3 s (and a smaller size), then click "smooth" on the result for 32 fps.

Start it anyway?`);
}

function newJobId() { return Date.now().toString(36) + Math.random().toString(36).slice(2); }

// Show a job card for `request` (fetch arguments), track it, and swap in the result.
async function runJob(job, kind, prompt, request) {
  const card = jobCard(MODES[kind].button, prompt);
  addToGallery(card);
  const stop = trackJob(card, job, MODES[kind].busy);

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
  countGallery();
}

function addToGallery(card) {
  const empty = gallery.querySelector(".empty");
  if (empty) empty.remove();
  gallery.prepend(card);
  countGallery();
}

function countGallery() {
  const done = gallery.querySelectorAll(".card:not(.job)").length;
  const running = gallery.querySelectorAll(".card.job:not(.note)").length;
  $("galleryCount").textContent = [done && `${done} result${done > 1 ? "s" : ""}`,
                                   running && `${running} running`].filter(Boolean).join(" · ");
}
new MutationObserver(countGallery).observe(gallery, { childList: true });

function openLightbox(url) {
  $("lightboxImg").src = url;
  $("lightbox").hidden = false;
}
function closeLightbox() { $("lightbox").hidden = true; $("lightboxImg").src = ""; }
$("lightbox").addEventListener("click", (e) => { if (e.target !== $("lightboxImg")) closeLightbox(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("lightbox").hidden) closeLightbox(); });

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
      card.classList.add("stopping");
      cancel.textContent = "Stopping…";
      card.querySelector(".job-label").textContent = "Stopping…";
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

// ---- views: Studio (tools + gallery) and Models (what's installed, downloads) ----
function setView(view) {
  document.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("layout").classList.toggle("models-mode", view !== "studio");
  $("modelsView").hidden = view !== "models";
  $("galleryView").hidden = view !== "gallery";
  if (view === "models") loadModels();
  else clearTimeout(modelsTimer);
  if (view === "gallery") loadGallery(true);
}
document.querySelectorAll(".view-btn").forEach((b) => b.addEventListener("click", () => {
  setView(b.dataset.view);
  window.history.replaceState(null, "", b.dataset.view === "studio" ? "#" + mode : "#" + b.dataset.view);
}));
document.querySelectorAll("[data-view-link]").forEach((a) => a.addEventListener("click", (e) => {
  e.preventDefault();
  setView(a.dataset.viewLink);
  window.history.replaceState(null, "", "#models");
}));

const gb = (n) => (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + " GB";
let modelsTimer = null;

async function loadModels() {
  clearTimeout(modelsTimer);
  let j;
  try { j = await (await fetch("/api/models")).json(); }
  catch { $("modelsInfo").textContent = "Server unreachable."; return; }
  const busy = j.models.some((m) => m.progress && ["queued", "downloading"].includes(m.progress.state)
                                    || m.files.some((f) => f.state === "writing"));
  $("modelsInfo").innerHTML = (j.comfy ? "" : "<b>ComfyUI is offline</b>, so only files in <code>models/</code> are checked. ") +
    `Downloads go to <code>${j.models_dir}</code>, which ComfyUI already reads; new models show up in the tools after a page reload.`;
  const list = $("modelsList");
  list.innerHTML = "";
  for (const [title, items] of [["Base models", j.models.filter((m) => m.base)],
                                ["Optional", j.models.filter((m) => !m.base)]]) {
    const h = document.createElement("h3");
    h.className = "models-group"; h.textContent = title;
    const grid = document.createElement("div");
    grid.className = "models-grid";
    for (const m of items) grid.append(modelCard(m));
    list.append(h, grid);
  }
  if (busy && !$("modelsView").hidden) modelsTimer = setTimeout(loadModels, 2000);
}

function modelCard(m) {
  const card = document.createElement("div");
  card.className = "model-card" + (m.installed ? " installed" : "");
  const p = m.progress, active = p && ["queued", "downloading"].includes(p.state);
  const writing = m.files.some((f) => f.state === "writing");
  let badge, cls;
  if (m.installed) { badge = "Installed"; cls = "ok"; }
  else if (active) { badge = p.state === "queued" ? "Queued" : "Downloading"; cls = "busy"; }
  else if (writing) { badge = "Downloading (script)"; cls = "busy"; }
  else if (m.files.some((f) => f.state === "partial")) { badge = "Partly downloaded"; cls = "warn"; }
  else { badge = "Not installed"; cls = "off"; }
  card.innerHTML = `
    <div class="model-top">
      <span class="model-kind"></span>${m.test ? '<span class="test-badge">test</span>' : ""}
      <span class="badge ${cls}">${badge}</span>
    </div>
    <h4></h4><p class="model-note"></p>
    <div class="model-meta"><span></span><span class="lic"></span></div>
    <ul class="model-files"></ul>`;
  card.querySelector(".model-kind").textContent = m.kind;
  card.querySelector("h4").textContent = m.name;
  card.querySelector(".model-note").textContent = m.note;
  card.querySelector(".model-meta span").textContent = gb(m.size) + (m.installed ? "" : ` · ${gb(m.missing)} to download`);
  card.querySelector(".lic").textContent = m.license;
  const ul = card.querySelector(".model-files");
  for (const f of m.files) {
    const li = document.createElement("li");
    li.className = f.state;
    li.textContent = `${f.name}`;
    li.title = `${f.repo} → ${f.folder}/ (${gb(f.size)})`;
    if (f.state !== "installed" && f.have) li.textContent += ` · ${Math.floor(100 * f.have / f.size)}%`;
    ul.append(li);
  }
  if (active || (p && p.state === "failed")) {
    const pct = p.total ? Math.floor(100 * p.done / p.total) : 0;
    const bar = document.createElement("div");
    bar.className = "model-progress";
    bar.innerHTML = '<div class="progress"><div></div></div><div class="hint"></div>';
    bar.querySelector(".progress > div").style.width = pct + "%";
    bar.querySelector(".hint").textContent = p.state === "failed" ? "Failed: " + p.error
      : p.state === "queued" ? "Waiting for the current download…"
      : `${pct}% · ${p.file} · ${(p.speed / 1e6).toFixed(1)} MB/s`;
    card.append(bar);
  }
  if (!m.installed && !writing) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = active ? "small" : "model-get";
    btn.textContent = active ? "Cancel" : (m.files.some((f) => f.have) ? "Resume download" : "Download " + gb(m.missing));
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await fetch(`/api/models/${m.id}/${active ? "cancel" : "download"}`, { method: "POST" }).catch(() => {});
      loadModels();
    });
    card.append(btn);
  }
  return card;
}

// ---- Gallery: everything in output/, newest first ----
let galleryType = "", galleryOffset = 0;
const GALLERY_PAGE = 60;

async function loadGallery(reset) {
  if (reset) { galleryOffset = 0; $("allGallery").innerHTML = ""; }
  let j;
  try {
    j = await (await fetch(`/api/gallery?type=${galleryType}&offset=${galleryOffset}&limit=${GALLERY_PAGE}`)).json();
  } catch { $("galleryInfo").textContent = "Server unreachable."; return; }
  for (const it of j.items) $("allGallery").append(galleryCard(it));
  galleryOffset += j.items.length;
  $("galleryInfo").innerHTML = `${j.total} file${j.total === 1 ? "" : "s"} in <code>output/</code>, newest first.`;
  $("galleryMore").hidden = galleryOffset >= j.total;
  if (!j.total) $("allGallery").innerHTML = '<div class="empty"><p>Nothing in output/ yet.</p></div>';
}

function galleryCard(it) {
  const card = document.createElement("div");
  card.className = "card";
  const media = document.createElement(it.video ? "video" : "img");
  media.src = it.video ? it.url + "#t=0.1" : it.url;  // #t: browsers then draw that frame as a thumbnail
  if (it.video) Object.assign(media, { controls: true, loop: true, muted: true, preload: "metadata", playsInline: true });
  else { media.alt = it.kind; media.loading = "lazy"; media.addEventListener("click", () => openLightbox(it.url)); }
  const meta = document.createElement("div");
  meta.className = "meta";
  const label = document.createElement("span");
  label.className = "g-label";
  label.innerHTML = `<b></b><small></small>`;
  label.querySelector("b").textContent = it.kind;
  label.querySelector("small").textContent = new Date(it.mtime * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
  if (it.prompt) label.title = it.prompt + (it.seed != null ? `  (seed ${it.seed})` : "");
  const actions = document.createElement("span");
  actions.className = "actions";
  const link = (text, title, fn) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "link"; b.textContent = text; b.title = title;
    b.addEventListener("click", fn);
    actions.append(b);
  };
  const blob = async () => (await fetch(it.url)).blob();
  if (it.video) {
    link("smooth", "Double the frame rate with RIFE", async () => {
      const job = newJobId(); setView("studio");
      runJob(job, "videofx", `${it.filename} ×2 smooth`, videoFxRequest(await blob(), it.filename, job, "smooth", 2));
    });
  } else {
    link("use as photo", "Open it in the Studio as the working photo", async () => {
      const b = await blob(); setView("studio");
      if (mode === "generate") setMode("edit");
      loadPhoto(b, it.filename, { remember: true });
    });
    link("upscale", "Enlarge 2× (Fast)", async () => {
      const job = newJobId(), form = new FormData();
      form.append("image", await blob(), it.filename);
      form.append("scale", 2); form.append("job", job); form.append("client", clientId);
      setView("studio");
      runJob(job, "upscale", `${it.filename} ×2`, ["/api/upscale", { method: "POST", body: form }]);
    });
  }
  const dl = document.createElement("a");
  dl.href = it.url; dl.download = it.filename; dl.textContent = "download";
  actions.append(dl);
  meta.append(label, actions);
  card.append(media, meta);
  return card;
}

document.querySelectorAll("#galleryFilters .seg-btn").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#galleryFilters .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  galleryType = b.dataset.type;
  loadGallery(true);
}));
$("galleryMore").addEventListener("click", () => loadGallery(false));

// ---- model pickers with an info card: hover (or arrow to) a model to read about it ----
function richSelect(select, infoFor) {
  const wrap = document.createElement("div");
  wrap.className = "rsel";
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "rsel-btn";
  btn.setAttribute("aria-haspopup", "listbox");
  const menu = document.createElement("div");
  menu.className = "rsel-menu"; menu.hidden = true;
  const list = document.createElement("div");
  list.className = "rsel-list"; list.setAttribute("role", "listbox");
  const info = document.createElement("div");
  info.className = "rsel-info";
  menu.append(list, info);
  wrap.append(btn);
  document.body.append(menu);  // outside the sticky panel, so it layers above the gallery
  select.classList.add("native-hidden");
  select.after(wrap);
  let active = 0;

  const items = () => [...list.children];
  const syncButton = () => {
    const o = select.options[select.selectedIndex];
    btn.textContent = o ? o.textContent : "";
  };
  function showInfo(i) {
    active = i;
    items().forEach((el, k) => el.classList.toggle("hover", k === i));
    const o = select.options[i];
    const m = infoFor(o.value);
    if (!m) { info.innerHTML = ""; return; }
    const a = m.about || {};
    info.innerHTML = `
      <div class="rsel-info-top"><b></b>${/\(test\)/.test(m.label) ? '<span class="test-badge">test</span>' : ""}
        <span class="badge ${m.installed ? "ok" : "off"}">${m.installed ? "Installed" : "Not installed"}</span></div>
      <p class="rsel-text"></p>
      <dl><dt>Best for</dt><dd class="i-best"></dd><dt>Speed</dt><dd class="i-speed"></dd><dt>License</dt><dd class="i-lic"></dd></dl>
      ${m.installed ? "" : '<a href="#models" class="rsel-get">Get it on the Models page →</a>'}`;
    info.querySelector("b").textContent = m.label;
    info.querySelector(".rsel-text").textContent = a.text || "";
    info.querySelector(".i-best").textContent = a.best || "—";
    info.querySelector(".i-speed").textContent = a.speed || `${m.steps} steps`;
    info.querySelector(".i-lic").textContent = a.license || "—";
    const get = info.querySelector(".rsel-get");
    if (get) get.addEventListener("click", (e) => { e.preventDefault(); close(); setView("models"); });
  }
  function build() {
    list.innerHTML = "";
    [...select.options].forEach((o, i) => {
      const el = document.createElement("div");
      el.className = "rsel-opt" + (o.disabled ? " disabled" : "") + (i === select.selectedIndex ? " selected" : "");
      el.setAttribute("role", "option");
      el.textContent = o.textContent;
      el.addEventListener("mouseenter", () => showInfo(i));
      el.addEventListener("click", () => choose(i));
      list.append(el);
    });
  }
  function choose(i) {
    if (select.options[i].disabled) return showInfo(i);  // not installed: just explain
    select.selectedIndex = i;
    select.dispatchEvent(new Event("change"));
    syncButton();
    close();
  }
  function open() {
    build();
    menu.hidden = false;
    wrap.classList.add("open");
    showInfo(select.selectedIndex);
    // The panel scrolls (and would clip the menu), so the menu floats over the page.
    const r = btn.getBoundingClientRect(), wide = innerWidth > 900;
    const width = wide ? Math.min(640, innerWidth - r.left - 16) : r.width;
    menu.style.cssText = `position:fixed;left:${r.left}px;width:${width}px;top:${r.bottom + 6}px`;
    const h = menu.getBoundingClientRect().height;
    if (r.bottom + 6 + h > innerHeight - 8 && r.top - 6 - h > 8) menu.style.top = `${r.top - 6 - h}px`;
  }
  function close() { menu.hidden = true; wrap.classList.remove("open"); }

  btn.addEventListener("click", () => (menu.hidden ? open() : close()));
  btn.addEventListener("keydown", (e) => {
    if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      if (menu.hidden) return open();
      showInfo((active + (e.key === "ArrowDown" ? 1 : -1) + select.options.length) % select.options.length);
    } else if (e.key === "Enter" && !menu.hidden) { e.preventDefault(); choose(active); }
    else if (e.key === "Escape") close();
  });
  document.addEventListener("click", (e) => { if (!wrap.contains(e.target) && !menu.contains(e.target)) close(); });
  $("form").addEventListener("scroll", close);
  addEventListener("resize", close);
  select.addEventListener("change", syncButton);
  syncButton();
}
richSelect($("model"), (v) => FAMILIES[v]);
richSelect($("videoModel"), (v) => FAMILIES[v]);

// Open the page named in the URL (#models / #gallery) once everything above exists.
if (location.hash === "#models" || location.hash === "#gallery") setView(location.hash.slice(1));
