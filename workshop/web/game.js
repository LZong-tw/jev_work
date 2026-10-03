"use strict";
// The game layer of the level simulators: pixel-art sprites, 8-bit sounds, pops, coin bursts and stars.
//   GAME.sprite("coin", 4)          a <canvas> with the sprite, 4 screen pixels per sprite pixel
//   GAME.sfx("coin")                an 8-bit sound (blip, coin, hit, win, lose, block, whoosh, tick, cash)
//   GAME.pop(el, "+1", "#2fd27a")   a number that jumps out of an element
//   GAME.burst(el, 6)               coins fly out of an element
//   GAME.shake(el)                  the element shakes (a hit)
//   GAME.stars(fraction)            three stars, lit by how well it went
//   GAME.hearts(left, all)          lives
//   GAME.banner("PERFECT!")         a big banner for a moment
//   GAME.soundButton()              a 🔊 / 🔇 button (kept in this browser)
const GAME = (() => {
  // ----- sprites: one character per pixel, "." is clear ------------------------------------------------------
  const PAL = { k: "#0b0f14", w: "#f5f7fa", y: "#ffcd38", Y: "#fff2a8", o: "#c77d12", r: "#ff4d55", R: "#a3202b",
                g: "#2fd27a", G: "#167a45", b: "#3987e5", B: "#1d4f8f", c: "#6ad8ff", p: "#c38bff", s: "#9aa8b6",
                S: "#4d5b6a", n: "#8a5a2b", t: "#e8b98a", a: "#ff9f1c" };
  const SPRITES = {
    coin: ["..oyyo..", ".oyYYyo.", "oyYyyYyo", "oyYyoYyo", "oyYyoYyo", "oyYyyYyo", ".oyYYyo.", "..oyyo.."],
    heart: [".rr.rr..", "rwrrrrr.", "rrrrrrr.", "rrrrrrr.", ".rrrrr..", "..rrr...", "...r...."],
    heartOff: [".SS.SS..", "SSSSSSS.", "SSSSSSS.", "SSSSSSS.", ".SSSSS..", "..SSS...", "...S...."],
    star: ["....y....", "...yyy...", "...yYy...", "yyyyYyyyy", ".yyyYyyy.", "..yyyyy..", "..yy.yy..", ".yy...yy.", ".y.....y."],
    starOff: ["....S....", "...SSS...", "...SSS...", "SSSSSSSSS", ".SSSSSSS.", "..SSSSS..", "..SS.SS..", ".SS...SS.", ".S.....S."],
    shield: [".bbbbbb.", "bBccccBb", "bBcwccBb", "bBccccBb", "bBccccBb", ".bBccBb.", ".bBccBb.", "..bBBb..", "...bb..."],
    skull: [".wwwwww.", "wwwwwwww", "wkkwwkkw", "wkkwwkkw", "wwwkkwww", ".wwwwww.", ".wkwwkw.", ".wwwwww."],
    rocket: ["...rr...", "..rwwr..", "..wwww..", "..wccw..", "..wccw..", "..wwww..", ".rwwwwr.", "rr.ww.rr", "...ya...", "...aa..."],
    bag: ["..o..o..", "...oo...", "..oyyo..", ".oyykyo.", "oyykyyyo", "oyyykyyo", "oyykkyyo", ".oyyyyo.", "..oooo.."],
    trophy: ["oyyyyyyo", "yyYyyyyy", ".yYyyyy.", "..yyyy..", "...yy...", "...yy...", "..oyyo..", ".oooooo."],
    robot: ["...cc...", "..sccs..", ".ssssss.", ".skssks.", ".ssssss.", ".ssrrss.", "ss.ss.ss", ".s....s."],
    mail: ["wwwwwwww", "wSwwwwSw", "wwSwwSww", "wwwSSwww", "wwwwwwww", "wwwwwwww"],
    tea: ["...s....", "...s....", ".wwwwww.", ".wttttw.", ".wttttw.", ".wttttw.", ".wnknkw.", ".wknknw.", "..wwww.."],
    bolt: ["...yy.", "..yy..", ".yy...", "yyyyy.", "...yy.", "..yy..", ".yy...", "yy...."],
    check: [".......g", "......gg", ".....gg.", "g...gg..", "gg.gg...", ".ggg....", "..g....."],
    cross: ["r......r", ".r....r.", "..r..r..", "...rr...", "...rr...", "..r..r..", ".r....r.", "r......r"],
    bomb: [".....y..", "....o.y.", "...o....", ".kkkk...", "kkwkkk..", "kkkkkk..", "kkkkkk..", ".kkkk..."],
    happy: ["..yyyy..", ".yyyyyy.", "yykyykyy", "yyyyyyyy", "ykyyyyky", "yykkkkyy", ".yyyyyy.", "..yyyy.."],
    meh: ["..yyyy..", ".yyyyyy.", "yykyykyy", "yyyyyyyy", "yyyyyyyy", "ykkkkkky", ".yyyyyy.", "..yyyy.."],
    angry: ["..rrrr..", ".rrrrrr.", "rkrrrrkr", "rrkrrkrr", "rrrrrrrr", "rrkkkkrr", ".krrrrk.", "..rrrr.."],
    gem: ["..cccc..", ".cwccccc", "cwcccccc", "cccccccb", ".ccccccb", "..ccccb.", "...ccb..", "....b..."],
    up: ["...gg...", "..gggg..", ".gggggg.", "gggggggg", "...gg...", "...gg...", "...gg...", "...gg..."],
    down: ["...rr...", "...rr...", "...rr...", "...rr...", "rrrrrrrr", ".rrrrrr.", "..rrrr..", "...rr..."],
  };
  const cache = new Map();
  function sprite(name, scale = 3, title) {
    const rows = SPRITES[name] || SPRITES.cross, w = Math.max(...rows.map(r => r.length)), h = rows.length;
    const key = `${name}@${scale}`;
    if (!cache.has(key)) {
      const c = document.createElement("canvas"); c.width = w * scale; c.height = h * scale;
      const g = c.getContext("2d");
      rows.forEach((row, y) => [...row].forEach((ch, x) => { if (PAL[ch]) { g.fillStyle = PAL[ch]; g.fillRect(x * scale, y * scale, scale, scale); } }));
      cache.set(key, c);
    }
    const src = cache.get(key), out = document.createElement("canvas");
    out.width = src.width; out.height = src.height; out.className = `sprite sprite-${name}`;
    out.getContext("2d").drawImage(src, 0, 0);
    if (title) out.title = title;
    return out;
  }

  // ----- 8-bit sounds (WebAudio square waves); off with the 🔊 button --------------------------------------
  let audio = null, muted = (() => { try { return localStorage.getItem("jev.sound") === "off"; } catch { return false; } })();
  function tone(freq, dur, { type = "square", at = 0, vol = 0.045, to } = {}) {
    const t0 = audio.currentTime + at, o = audio.createOscillator(), g = audio.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t0 + dur);
    g.gain.setValueAtTime(vol, t0); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(audio.destination); o.start(t0); o.stop(t0 + dur + 0.02);
  }
  const SFX = {
    blip: () => tone(880, 0.05),
    tick: () => tone(1600, 0.025, { vol: 0.02 }),
    coin: () => { tone(988, 0.07); tone(1319, 0.14, { at: 0.07 }); },
    cash: () => [784, 988, 1175, 1568].forEach((f, i) => tone(f, 0.08, { at: i * 0.06 })),
    hit: () => tone(220, 0.2, { type: "sawtooth", to: 70 }),
    block: () => { tone(140, 0.12, { vol: 0.06 }); tone(90, 0.16, { at: 0.08, type: "sawtooth", vol: 0.05 }); },
    whoosh: () => tone(300, 0.25, { type: "triangle", to: 1400, vol: 0.05 }),
    win: () => [523, 659, 784, 1047, 1319].forEach((f, i) => tone(f, i === 4 ? 0.3 : 0.1, { at: i * 0.09 })),
    lose: () => [392, 330, 262, 196].forEach((f, i) => tone(f, 0.14, { at: i * 0.12, type: "triangle" })),
  };
  function sfx(name) {
    if (muted || !SFX[name]) return;
    try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); if (audio.state === "suspended") audio.resume(); SFX[name](); } catch { /* no sound here */ }
  }
  function soundButton() {
    const b = document.createElement("button");
    const paint = () => { b.textContent = muted ? "🔇" : "🔊"; b.title = muted ? "sound is off" : "sound is on"; };
    b.className = "sound"; b.type = "button";
    b.onclick = () => { muted = !muted; try { localStorage.setItem("jev.sound", muted ? "off" : "on"); } catch { /* not kept */ } paint(); if (!muted) sfx("blip"); };
    paint();
    return b;
  }

  // ----- effects -----------------------------------------------------------------------------------------
  function at(el) { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2 + scrollX, y: r.top + r.height / 3 + scrollY }; }
  function pop(el, text, color = "#ffcd38") {
    if (!el || !el.isConnected) return;
    const p = at(el), d = document.createElement("div");
    d.className = "pop"; d.textContent = text; d.style.cssText = `left:${p.x}px;top:${p.y}px;color:${color}`;
    document.body.append(d); setTimeout(() => d.remove(), 1000);
  }
  function burst(el, n = 6, name = "coin") {
    if (!el || !el.isConnected) return;
    const p = at(el);
    Array.from({ length: n }, (_, i) => {
      const s = sprite(name, 3), a = -Math.PI / 2 + (i - (n - 1) / 2) * 0.35;
      s.classList.add("flying");
      s.style.cssText = `left:${p.x}px;top:${p.y}px;--dx:${Math.cos(a) * (50 + (i % 3) * 18)}px;--dy:${Math.sin(a) * (60 + (i % 2) * 25)}px;animation-delay:${i * 30}ms`;
      document.body.append(s); setTimeout(() => s.remove(), 1100 + i * 30);
      return s;
    });
  }
  function shake(el) { if (!el) return; el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 450); }
  function stars(f, scale = 3) {
    const box = document.createElement("span"); box.className = "stars";
    box.title = `${f >= 1 ? 3 : f >= 2 / 3 ? 2 : f >= 1 / 3 ? 1 : 0} of 3 stars`;
    [1 / 3, 2 / 3, 1].forEach(t => box.append(sprite(f >= t - 1e-9 ? "star" : "starOff", scale)));
    return box;
  }
  // a row of hearts: lives left of lives in all
  function hearts(left, all, scale = 3) {
    const box = document.createElement("span"); box.className = "hearts"; box.title = `${left} of ${all} lives left`;
    Array.from({ length: all }, (_, i) => box.append(sprite(i < left ? "heart" : "heartOff", scale)));
    return box;
  }
  // a big banner over the page for a moment: "PERFECT!", "LEVEL CLEAR"
  function banner(text) {
    const d = document.createElement("div"); d.className = "levelup";
    const t = document.createElement("div"); t.textContent = text; d.append(t);
    document.body.append(d); setTimeout(() => d.remove(), 2300);
  }
  return { sprite, sfx, soundButton, pop, burst, shake, stars, hearts, banner, SPRITES };
})();
