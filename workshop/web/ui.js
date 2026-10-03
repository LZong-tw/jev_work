"use strict";
// Shared by the level simulators (Levels 1-4): talking to the server, the cost meter, the interface a
// page expects from Jev, and the Jev editor (the exact request for one item, and its answer).
const UI = (() => {
  // ----- small helpers ---------------------------------------------------------------------------------
  // el("div", { class: "card", onclick: fn }, "text", child): text is always text, never HTML
  function el(tag, props = {}, ...kids) {
    const e = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v === undefined || v === null || v === false) return;
      if (k === "class") e.className = v;
      else if (k === "style") e.style.cssText = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    });
    kids.flat().forEach(k => { if (k !== null && k !== undefined && k !== false) e.append(k instanceof Node ? k : String(k)); });
    return e;
  }
  const $ = (sel, root = document) => root.querySelector(sel);
  const pct = p => `${Math.round(Math.max(0, Math.min(1, p)) * 100)}%`;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const json = x => JSON.stringify(x, null, 2);

  // a 0..1 bar, with a mark at the threshold (optional)
  function pbar(p, mark, color) {
    return el("div", { class: "pbar" }, el("i", { style: `width:${pct(p ?? 0)};${color ? `background:${color}` : ""}` }),
              mark === undefined ? null : el("b", { style: `left:calc(${pct(mark)} - 1px)` }));
  }

  // ----- the server ------------------------------------------------------------------------------------
  async function api(path, body) {
    const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }
  const usage = { calls: 0, tokens: 0, cost: 0 };
  let meterEl = null, jevInfo = null;
  function paintMeter() {
    if (!meterEl || !jevInfo) return;
    meterEl.replaceChildren(
      el("span", { class: `badge ${jevInfo.mock ? "mock" : "real"}`, title: jevInfo.mock ? "JEV_MOCK=1: fake keyword-matching answers" : "the real Jev API" },
         jevInfo.mock ? "Jev: MOCK" : `Jev: ${jevInfo.model}`), " ",
      el("b", {}, usage.calls), " calls · ", el("b", {}, usage.tokens.toLocaleString()), " tokens · ", el("b", {}, `$${usage.cost.toFixed(5)}`));
  }
  // one Jev call through the server (your key stays there)
  async function ask(request) {
    const r = await api("/api/jev", request);
    usage.calls++; usage.tokens += (r.usage && r.usage.input_tokens) || 0; usage.cost += r.cost_usd || 0;
    paintMeter();
    return r;
  }
  // the level's data (read fresh from your Python code), and the header meter
  async function boot() {
    const level = await api("/api/level");
    jevInfo = level.jev; meterEl = $("#meter"); paintMeter();
    return level;
  }

  // ----- what a page expects from Jev: { id: { type, use, labels?, needs?, optional? } } ---------------
  const ANSWER_SHAPE = {
    noul: "{ noul: number 0..1 }",
    choice: "{ choice: one of its labels, confidence: number 0..1, probabilities?: { label: number } }",
    score: "{ score: number 0..(levels - 1), confidence?: number 0..1 }",
  };
  const QUESTION_SHAPE = {
    noul: '{ type: "noul", instructions: string, criteria?: { true: string, false: string } }',
    choice: '{ type: "choice", instructions: string, criteria: { label: "what it means", ... } }',
    score: '{ type: "score", instructions: string, criteria: ["lowest", ..., "highest"] }',
  };
  function interfaceText(expect) {
    const rows = Object.entries(expect);
    const labels = s => s.labels ? `\n      labels: ${s.labels.join(" | ")}` : "";
    return ["request  {", "  state: string or JSON object,   // what Jev reads", "  questions: {",
      ...rows.map(([id, s]) => `    ${id}${s.optional ? "?" : ""}: ${QUESTION_SHAPE[s.type]}${labels(s)}\n      // ${s.use}`),
      "    ...more questions are fine (Jev answers them, this page does not use them)", "  }", "}",
      "response {", "  answers: {",
      ...rows.map(([id, s]) => `    ${id}${s.optional ? "?" : ""}: ${ANSWER_SHAPE[s.type]}`), "  }", "}"].join("\n");
  }
  const isObj = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const in01 = x => typeof x === "number" && x >= 0 && x <= 1;
  function checkRequest(req, expect) {
    if (!isObj(req)) return ['the request is a JSON object: { "state": ..., "questions": { ... } }'];
    const errs = [];
    if (!("state" in req) || req.state === null || req.state === "") errs.push('state: missing. Put what Jev should read in "state" (text or a JSON object).');
    if (!isObj(req.questions)) return [...errs, 'questions: missing. It is an object: { "your_id": { "type": "noul", "instructions": "..." } }'];
    Object.entries(expect).forEach(([id, s]) => {
      const q = req.questions[id];
      if (!q) { if (!s.optional) errs.push(`questions.${id}: missing. This page needs a ${s.type} question named "${id}" (${s.use}).`); return; }
      if (q.type !== s.type) errs.push(`questions.${id}.type: "${q.type}". This page needs "${s.type}" here (${s.use}).`);
      if (typeof q.instructions !== "string" || !q.instructions.trim()) errs.push(`questions.${id}.instructions: write the question as text.`);
      if (s.type === "choice") {
        const labels = isObj(q.criteria) ? Object.keys(q.criteria) : [];
        if (labels.length < 2) errs.push(`questions.${id}.criteria: at least 2 labels: { "label": "what it means", ... }.`);
        const unknown = s.labels ? labels.filter(l => !s.labels.includes(l)) : [];
        if (unknown.length) errs.push(`questions.${id}.criteria: "${unknown.join('", "')}" is not known here. Labels this page can use: ${s.labels.join(", ")}.`);
      }
      if (s.type === "score" && !(Array.isArray(q.criteria) && q.criteria.length >= 2 && q.criteria.length <= 10))
        errs.push(`questions.${id}.criteria: the levels, lowest first, 2 to 10 of them: ["low", "high"].`);
    });
    return errs;
  }
  function checkResponse(res, req, expect) {
    if (!isObj(res) || !isObj(res.answers)) return ['the response is a JSON object: { "answers": { "id": { ... } } }'];
    const errs = [];
    Object.entries(expect).forEach(([id, s]) => {
      const a = res.answers[id], q = isObj(req) && isObj(req.questions) ? req.questions[id] : null;
      if (!isObj(a)) { if (!s.optional) errs.push(`answers.${id}: missing. This page needs ${ANSWER_SHAPE[s.type]}.`); return; }
      if (s.type === "noul" && !in01(a.noul)) errs.push(`answers.${id}.noul: a number from 0 to 1 (the chance of YES).`);
      if (s.type === "choice") {
        const labels = q && isObj(q.criteria) ? Object.keys(q.criteria) : s.labels;
        if (typeof a.choice !== "string" || (labels && !labels.includes(a.choice))) errs.push(`answers.${id}.choice: one of ${labels ? labels.join(", ") : "the labels"}.`);
        if ((s.needs || []).includes("confidence") && !in01(a.confidence)) errs.push(`answers.${id}.confidence: a number from 0 to 1.`);
      }
      if (s.type === "score") {
        const top = q && Array.isArray(q.criteria) ? q.criteria.length - 1 : null;
        if (typeof a.score !== "number" || a.score < 0 || (top !== null && a.score > top)) errs.push(`answers.${id}.score: a number from 0 to ${top ?? "(levels - 1)"}.`);
      }
    });
    return errs;
  }
  function parse(text, what) {
    try { return { value: JSON.parse(text) }; } catch (e) { return { errors: [`${what} is not valid JSON: ${e.message}`] }; }
  }

  // ----- the Jev editor --------------------------------------------------------------------------------
  // editor.open({ title, request, response, onResult(result, request, how) }): how = "jev" (sent) or "apply"
  function Editor(root, expect) {
    const target = el("span", { class: "ed-target" });
    const req = el("textarea", { class: "req", spellcheck: "false", "aria-label": "Jev request JSON" });
    const res = el("textarea", { class: "res", spellcheck: "false", "aria-label": "Jev response JSON" });
    const errors = el("ul", { class: "ed-errors" }), status = el("div", { class: "ed-status" });
    const sendBtn = el("button", { class: "primary", onclick: () => send() }, "Send to Jev");
    const applyBtn = el("button", { onclick: () => apply() }, "Apply response");
    const empty = el("div", { class: "ed-empty" }, "Click an item to see the exact JSON Jev gets for it, change it, and send it.");
    const body = el("div", { class: "ed-body" },
      el("details", {}, el("summary", {}, "What this page expects from Jev"), el("pre", {}, interfaceText(expect))),
      el("label", {}, "Request", el("span", {}, "POST /v1/systemone · jev.py adds the model")), req,
      el("div", { class: "ed-btns" }, sendBtn, el("button", { onclick: () => format(req) }, "Format")),
      el("label", {}, "Response", el("span", {}, "edit + Apply: no Jev call, no cost")), res,
      el("div", { class: "ed-btns" }, applyBtn), errors, status);
    body.hidden = true;
    root.replaceChildren(el("div", { class: "ed-head" }, el("b", {}, "🧪 Jev editor"), target), empty, body);
    let cur = null;
    const showErrors = list => errors.replaceChildren(...(list || []).map(m => el("li", {}, m)));
    function format(t) { const p = parse(t.value, "This"); if (p.value !== undefined) t.value = json(p.value); else showErrors(p.errors); }
    function open(o) {
      cur = o; target.textContent = o.title || "";
      empty.hidden = true; body.hidden = false;
      req.value = json(o.request); res.value = o.response ? json(clean(o.response)) : ""; showErrors([]); status.textContent = "";
    }
    const clean = r => { const { cost_usd, latency_ms, ...rest } = r; return rest; };   // the API's own JSON
    function showResponse(o, r) { if (cur === o) { res.value = json(clean(r)); showErrors([]); } }
    async function send() {
      if (!cur) return;
      const p = parse(req.value, "The request");
      const errs = p.errors || checkRequest(p.value, expect);
      if (errs.length) return showErrors(errs);
      const o = cur;
      showErrors([]); status.textContent = "asking Jev…"; sendBtn.disabled = true;
      try {
        const r = await ask(p.value);
        status.textContent = `answered in ${r.latency_ms} ms · ${(r.usage && r.usage.input_tokens) || 0} input tokens · $${(r.cost_usd || 0).toFixed(6)}`;
        showResponse(o, r);
        const bad = checkResponse(r, p.value, expect);
        if (bad.length) return showErrors(bad);
        o.onResult(r, p.value, "jev");
      } catch (e) { showErrors([e.message]); status.textContent = ""; }
      finally { sendBtn.disabled = false; }
    }
    function apply() {
      if (!cur) return;
      const pq = parse(req.value, "The request"), pr = parse(res.value, "The response");
      const errs = pq.errors || pr.errors || [...checkRequest(pq.value, expect), ...checkResponse(pr.value, pq.value, expect)];
      if (errs.length) return showErrors(errs);
      showErrors([]); status.textContent = "applied your response (no Jev call)";
      cur.onResult(pr.value, pq.value, "apply");
    }
    return { open, showResponse, get current() { return cur; } };
  }

  // ----- a small code editor: a textarea over a highlighted copy of its own text (Python) ----------------
  const PY_KEYWORDS = new Set(("False None True and as assert async await break class continue def del elif else except finally for " +
                               "from global if import in is lambda nonlocal not or pass raise return try while with yield").split(" "));
  const PY_BUILTINS = new Set("print len range dict list str int float bool isinstance any all sum min max sorted tuple set".split(" "));
  const PY_TOKEN = /(#[^\n]*)|((?:[rbfuRBFU]{1,2})?(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?))|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)/g;
  const esc = t => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  function highlightPython(src) {   // escaped text, plus <span class="k|s|c|n|b|f"> around tokens
    const done = [...src.matchAll(PY_TOKEN)].reduce((acc, m) => {
      const [all, com, str, num, word] = m;
      const base = com ? "c" : str ? "s" : num ? "n" : PY_KEYWORDS.has(word) ? "k" : acc.prev === "def" ? "f" : PY_BUILTINS.has(word) ? "b" : "";
      const cls = (com || str) && /\bTODO\b/.test(all) ? `${base} t` : base;   // a TODO stands out
      return { html: acc.html + esc(src.slice(acc.at, m.index)) + (cls ? `<span class="${cls}">${esc(all)}</span>` : esc(all)),
               at: m.index + all.length, prev: word || "" };
    }, { html: "", at: 0, prev: "" });
    return done.html + esc(src.slice(done.at));
  }
  // The editor: Enter keeps the indent (one more after ":"), Tab / Shift+Tab indent / dedent the lines,
  // Cmd/Ctrl+/ comments them, Cmd/Ctrl+S saves. markError(line) marks the line a save was refused for.
  function CodeEditor(root, { value = "", onSave, onChange } = {}) {
    const gutter = el("pre", { class: "ce-gutter", "aria-hidden": "true" }), hl = el("pre", { class: "ce-hl", "aria-hidden": "true" });
    const stripe = el("div", { class: "ce-err", hidden: true });
    const ta = el("textarea", { class: "ce-text", spellcheck: "false", autocapitalize: "off", "aria-label": "Python code" });
    let errLine = null;
    const lineHeight = () => parseFloat(getComputedStyle(ta).lineHeight) || 18.75;
    const sync = () => {
      hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; gutter.scrollTop = ta.scrollTop;
      stripe.hidden = !errLine; if (errLine) stripe.style.top = `${10 + (errLine - 1) * lineHeight() - ta.scrollTop}px`;
    };
    const paint = () => {
      hl.innerHTML = highlightPython(ta.value) + "\n";
      gutter.innerHTML = ta.value.split("\n").map((_, i) => i + 1 === errLine ? `<span class="bad">${i + 1}</span>` : `${i + 1}`).join("\n") + "\n";
      sync();
    };
    const changed = () => { paint(); if (onChange) onChange(ta.value); };
    // replace a range and keep the browser's undo (execCommand where it exists)
    const put = (text, from, to, select) => {
      ta.setSelectionRange(from, to);
      if (!document.execCommand || !document.execCommand("insertText", false, text)) ta.setRangeText(text, from, to, "end");
      if (select) ta.setSelectionRange(from, from + text.length);
      changed();
    };
    const lineBlock = () => { const from = ta.value.lastIndexOf("\n", ta.selectionStart - 1) + 1; return { from, to: ta.selectionEnd, lines: ta.value.slice(from, ta.selectionEnd).split("\n") }; };
    ta.addEventListener("input", changed);
    ta.addEventListener("scroll", sync);
    ta.addEventListener("keydown", e => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); if (onSave) onSave(ta.value); return; }
      if (mod && e.key === "/") {
        e.preventDefault();
        const b = lineBlock(), on = b.lines.every(l => !l.trim() || /^\s*#/.test(l));
        put(b.lines.map(l => !l.trim() ? l : on ? l.replace(/^(\s*)# ?/, "$1") : l.replace(/^(\s*)/, "$1# ")).join("\n"), b.from, b.to, true);
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        const b = lineBlock();
        if (!e.shiftKey && !ta.value.slice(ta.selectionStart, ta.selectionEnd).includes("\n")) return put("    ", ta.selectionStart, ta.selectionEnd);
        return put(b.lines.map(l => e.shiftKey ? l.replace(/^ {1,4}/, "") : "    " + l).join("\n"), b.from, b.to, true);
      }
      if (e.key === "Enter" && !mod && !e.shiftKey) {
        e.preventDefault();
        const at = ta.selectionStart, line = ta.value.slice(ta.value.lastIndexOf("\n", at - 1) + 1, at);
        put("\n" + line.match(/^[ \t]*/)[0] + (/:\s*(#.*)?$/.test(line) ? "    " : ""), at, ta.selectionEnd);
      }
    });
    root.replaceChildren(el("div", { class: "ce" }, gutter, el("div", { class: "ce-body" }, stripe, hl, ta)));
    ta.value = value; paint();
    return { get value() { return ta.value; }, set value(v) { ta.value = v; paint(); }, textarea: ta,
             markError(line) { errLine = line || null; paint(); if (errLine) ta.scrollTop = Math.max(0, (errLine - 4) * lineHeight()); } };
  }

  // A challenge file in the page: the editor, Save (only if it compiles), Reload from disk, and what happened.
  function CodePanel(root, { file, source, title, onSaved }) {
    const status = el("span", { class: "hint", "aria-live": "polite" }), box = el("div");
    let saved = source, editor = null;
    const paintStatus = () => { const dirty = editor && editor.value !== saved; status.textContent = dirty ? "● not saved" : "saved"; status.className = dirty ? "warn" : "hint"; };
    async function save() {
      try {
        await api("/api/save", { file, source: editor.value });
        saved = editor.value; editor.markError(null); paintStatus();
        status.textContent = `saved ✓ ${new Date().toLocaleTimeString()}`;
        if (onSaved) onSaved(saved);
      } catch (e) {
        const m = /line (\d+)/.exec(e.message);
        editor.markError(m ? +m[1] : null); status.textContent = e.message; status.className = "err";
      }
    }
    async function reload() { saved = (await api("/api/code", {}))[file]; editor.value = saved; editor.markError(null); paintStatus(); if (onSaved) onSaved(saved); }
    root.replaceChildren(el("div", { class: "cp-head" }, el("b", {}, title || file), status), box,
      el("div", { class: "ed-btns", style: "margin-top:8px" }, el("button", { class: "primary", onclick: save }, "Save (⌘/Ctrl+S)"), el("button", { onclick: reload }, "Reload from disk")),
      el("div", { class: "hint", style: "margin-top:6px" }, "Edit here or in your own editor: the page always uses the saved file. Saving only works if the code compiles. Tab / Shift+Tab indent, ⌘/Ctrl+/ comments."));
    editor = CodeEditor(box, { value: source, onSave: save, onChange: paintStatus });
    paintStatus();
    return { save, reload, get editor() { return editor; }, get dirty() { return editor.value !== saved; } };
  }

  // ----- a score: a ring that fills, the best so far (kept in this browser), a small party at full marks ---
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
  function ScoreRing(root, { key, label = "score" }) {
    const store = `jev.best.${key}`;
    const best = () => { try { return JSON.parse(localStorage.getItem(store) || "null"); } catch { return null; } };
    const ring = f => {
      const r = 30, c = 2 * Math.PI * r, color = f >= 1 ? "#2fd27a" : f >= 0.5 ? "#ffb020" : "#ff4d55";
      const svg = svgEl("svg", { viewBox: "0 0 76 76", width: 76, height: 76, class: "ring" });
      svg.append(svgEl("circle", { cx: 38, cy: 38, r, fill: "none", stroke: "#1c2530", "stroke-width": 9 }),
                 svgEl("circle", { cx: 38, cy: 38, r, fill: "none", stroke: color, "stroke-width": 9, "stroke-linecap": "round",
                                   "stroke-dasharray": c, "stroke-dashoffset": c * (1 - Math.max(0, Math.min(1, f))), transform: "rotate(-90 38 38)" }));
      return svg;
    };
    // show(got, total): the score now. text: what to show instead of "got/total" (e.g. points);
    // record: false while it is not final yet (it does not count as a best)
    function show(got, total, { text, note, record = true } = {}) {
      const b = best(), f = total ? got / total : 0;
      if (record && total && (!b || f > b.got / b.total)) { try { localStorage.setItem(store, JSON.stringify({ got, total, text })); } catch { /* not kept */ } }
      const now = best() || b;
      root.replaceChildren(el("div", { class: `score${f >= 1 ? " full" : ""}` }, ring(f),
        el("div", {}, el("div", { class: "k" }, label), el("div", { class: "big" }, text || `${got}/${total}`, f >= 1 ? el("span", { class: "party" }, " 🎉") : null),
           el("div", { class: "hint" }, note || (now ? `best so far: ${now.text || `${now.got}/${now.total}`}` : "")))));
    }
    function clear(note) {
      const b = best();
      root.replaceChildren(el("div", { class: "score" }, ring(0), el("div", {}, el("div", { class: "k" }, label), el("div", { class: "big" }, "–"),
        el("div", { class: "hint" }, note || (b ? `best so far: ${b.text || `${b.got}/${b.total}`}` : "")))));
    }
    clear();
    return { show, clear };
  }

  return { el, $, pct, pbar, sleep, json, api, ask, boot, usage, Editor, CodeEditor, CodePanel, ScoreRing, highlightPython, checkRequest, checkResponse, interfaceText };
})();
