// Shared helpers: boot Pyodide, call the Python bridge, render tiny Markdown + tables.
const JURYRIG_VERSION = "0.3.2";
const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
let py = null;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

// Minimal Markdown for the strings the Python side produces: headings, tables, lists, paragraphs.
function md(text) {
  const out = [];
  const lines = String(text).split("\n");
  for (let i = 0; i < lines.length; ) {
    const l = lines[i];
    if (l.startsWith("|")) {
      const block = [];
      while (i < lines.length && lines[i].startsWith("|")) block.push(lines[i++]);
      const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(block[0]);
      const body = block.slice(2).map(cells);
      const hasHead = head.some((h) => h);
      out.push("<table>" + (hasHead ? "<tr>" + head.map((h) => `<th>${inline(h)}</th>`).join("") + "</tr>" : "") +
        body.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</table>");
      continue;
    }
    const h = l.match(/^(#{1,4}) (.*)/);
    if (h) { out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`); i++; continue; }
    if (l.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) items.push(`<li>${inline(lines[i++].slice(2))}</li>`);
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (l.trim()) out.push(`<p>${inline(l)}</p>`);
    i++;
  }
  return out.join("");
}

function table(headers, rows) {
  return "<table><tr>" + headers.map((h) => `<th>${esc(h)}</th>`).join("") + "</tr>" +
    rows.map((r) => "<tr>" + r.map((c) => `<td>${esc(c)}</td>`).join("") + "</tr>").join("") + "</table>";
}

function status(msg, cls = "") { const el = $("#status"); el.textContent = msg; el.className = cls; }

async function boot(pkg, wheelFile) {
  const t0 = performance.now();
  status("Loading Python (Pyodide, ~10 MB on first visit)…");
  py = await loadPyodide({ indexURL: PYODIDE_URL });
  await py.loadPackage(["micropip", "sqlite3"]);
  status(`Installing ${pkg} from PyPI…`);
  const micropip = py.pyimport("micropip");
  try {
    await micropip.install(pkg);
  } catch (err) {
    // Fallback: a wheel bundled next to index.html (see README "Offline wheel").
    console.warn("PyPI install failed, trying bundled wheel", err);
    await micropip.install(new URL(`wheels/${wheelFile}`, location.href).href);
  }
  const src = await (await fetch("space.py")).text();
  py.FS.writeFile("/home/pyodide/space.py", src);
  py.runPython("import space");
  const secs = ((performance.now() - t0) / 1000).toFixed(1);
  status(`Ready: real ${pkg} running in your browser (loaded in ${secs}s). No keys, no server.`, "ok");
  document.body.dataset.ready = "1";
  document.querySelectorAll("button[disabled]").forEach((b) => (b.disabled = false));
}

// Call a function in space.py; returns its result or throws with the friendly error text.
function call(name, ...args) {
  const r = JSON.parse(py.globals.get("space").api(name, JSON.stringify(args)));
  if (!r.ok) throw new Error(r.error);
  return r.result;
}

function wire(btnSel, fn) {
  $(btnSel).addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const errBox = btn.closest("section").querySelector(".error");
    errBox.textContent = "";
    btn.closest("section").querySelector(".download-report")?.remove();
    btn.disabled = true;
    await new Promise((r) => setTimeout(r, 20)); // let the UI repaint before Python blocks the thread
    try { fn(); } catch (e) { errBox.textContent = "⚠ " + e.message; } finally { btn.disabled = false; }
  });
}

function selectTab(id) {
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("active", x.dataset.tab === id));
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== id));
}

function setReport(audit, sampleSize, settings, results) {
  const section = $("#" + audit);
  const button = document.createElement("button");
  button.className = "secondary download-report";
  button.textContent = "Download report (JSON)";
  button.type = "button";
  button.addEventListener("click", () => {
    const report = { schema_version: 1, juryrig_version: JURYRIG_VERSION, audit,
      sample_size: sampleSize, settings, results };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "juryrig-" + audit + "-report.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  section.append(button);
}

// ---- juryrig UI ----
document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
});
$("#d-try").addEventListener("click", () => {
  selectTab("position");
  $("#p-in").focus();
});
const examples = { "#p-in": "EXAMPLE_POSITION", "#v-in": "EXAMPLE_VERBOSITY", "#c-in": "EXAMPLE_CALIBRATION", "#a-in": "EXAMPLE_AGREEMENT" };
document.querySelectorAll("button[data-example]").forEach((b) => b.addEventListener("click", () => {
  if (py) $(b.dataset.example).value = py.globals.get("space")[examples[b.dataset.example]];
}));
const n = (id) => Number($(id).value);

wire("#d-btn", () => {
  const [rows, text, cases, example] = call("run_demo");
  $("#d-tbl").innerHTML = table(["Judge", "Position: flip rate / first-slot wins", "Verbosity Δ", "Injection Δ", "Consistency spread", "Verdict"], rows);
  $("#d-txt").textContent = text;
  $("#d-box").hidden = false;
  $("#d-example").hidden = !example;
  if (example) {
    $("#d-prompt").textContent = example.prompt;
    $("#d-x").textContent = example.response_x;
    $("#d-y").textContent = example.response_y;
    $("#d-orders").innerHTML = table(["Order", "Slot A", "Slot B", "Picked slot", "Winning answer"], example.choices);
  }
  setReport("demo", cases, { mock_data: true }, { judges: rows, summary: text, worked_example: example });
});
wire("#p-btn", () => {
  const settings = { flip_limit: n("#p-flip"), slot_skew_limit: n("#p-skew") };
  const [head, rows, cases, changed] = call("on_position", $("#p-in").value, settings.flip_limit, settings.slot_skew_limit);
  $("#p-head").innerHTML = md(head);
  $("#p-tbl").innerHTML = table(["Metric", "Value", "Note"], rows);
  if (changed.length) {
    $("#p-tbl").innerHTML += "<h3>Cases where the outcome changed</h3>" +
      table(["Case", "Original slot", "Swapped slot", "Original winner", "Swapped winner"], changed);
  }
  setReport("position", cases, settings, { summary: head, metrics: rows, changed_outcomes: changed });
});
wire("#v-btn", () => {
  const settings = { score_scale: n("#v-scale"), mean_limit: n("#v-mean"), max_limit: n("#v-max") };
  const [head, rows, cases, count] = call("on_verbosity", $("#v-in").value, settings.score_scale, settings.mean_limit, settings.max_limit);
  $("#v-head").innerHTML = md(head);
  $("#v-tbl").innerHTML = table(["Metric", "Value", "Note"], rows) + "<h4>Per case</h4>" + table(["Case", "Original", "Padded", "Change"], cases);
  setReport("verbosity", count, settings, { summary: head, metrics: rows, changes: cases });
});
wire("#c-btn", () => {
  const settings = { bins: n("#c-bins") };
  const [head, rows, cases] = call("on_calibration", $("#c-in").value, settings.bins);
  $("#c-head").innerHTML = md(head);
  $("#c-tbl").innerHTML = table(["Score bin", "Count", "Mean score", "Accuracy", "|gap|"], rows);
  setReport("calibration", cases, settings, { summary: head, bins: rows });
});
wire("#a-btn", () => {
  const settings = { score_scale: n("#a-scale"), epsilon: n("#a-eps") };
  const [head, rows, atlas, cases] = call("on_agreement", $("#a-in").value, settings.score_scale, settings.epsilon);
  $("#a-head").innerHTML = md(head);
  $("#a-tbl").innerHTML = table(["Pair", "Within ε", "Cohen's κ", "Mean |Δ|", "Verdict"], rows) + md(atlas);
  setReport("agreement", cases, settings, { summary: head, pairs: rows, disagreement_atlas_markdown: atlas });
});
boot(`juryrig==${JURYRIG_VERSION}`, `juryrig-${JURYRIG_VERSION}-py3-none-any.whl`)
  .then(() => Object.keys(examples).forEach((sel) => ($(sel).value = py.globals.get("space")[examples[sel]])))
  .catch((e) => status("Failed to load Python: " + e.message, "err"));
