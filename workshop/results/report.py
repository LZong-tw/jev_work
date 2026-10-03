"""
Turn the numbers from run_all.py (results/level*.json) into RESULTS.md and SVG charts.

    python results/report.py

No API calls: you can change this file and run it again for free.
"""
import json
import statistics as st
from html import escape
from pathlib import Path

import os

HERE = Path(os.environ.get("RESULTS_DIR") or Path(__file__).resolve().parent)
CHARTS = HERE / "charts"

# Colors: validated reference palette (light / dark steps) + fixed status colors.
STYLE = """<style>
  .t { fill: #0b0b0b; font: 13px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .m { fill: #52514e; font: 12px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .w { fill: #ffffff; font: 600 12px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .grid { stroke: #e4e2dc; stroke-width: 1; }
  .ref { stroke: #52514e; stroke-width: 1.5; stroke-dasharray: 4 3; }
  .s1 { fill: #2a78d6; } .s1l { stroke: #2a78d6; } .s2 { fill: #eb6834; }
  .mean { stroke: #0b0b0b; stroke-width: 2.5; }
  @media (prefers-color-scheme: dark) {
    .t { fill: #ffffff; } .m { fill: #c3c2b7; } .grid { stroke: #3a3936; } .ref { stroke: #c3c2b7; }
    .s1 { fill: #3987e5; } .s1l { stroke: #3987e5; } .s2 { fill: #d95926; } .mean { stroke: #ffffff; }
  }
</style>"""
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>{STYLE}{body}</svg>\n')


def rounded_bar(x, y, w, h, fill_class=None, fill=None, r=4, right_round=True):
    """A horizontal bar, rounded only at its data end (right side)."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2) if right_round else 0
    attr = f'class="{fill_class}"' if fill_class else f'fill="{fill}"'
    d = (f"M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
         f"V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z")
    return f'<path d="{d}" {attr}/>'


def stacked_outcomes(rows, total, title, labels):
    """rows: [(name, {"good": n, "warning": n, "critical": n})]. Status colors + icon labels."""
    left, width, bar_h, gap = 230, 420, 26, 18
    height = 50 + len(rows) * (bar_h + gap)
    body = [f'<text class="m" x="{left}" y="20">out of {total} {escape(labels["unit"])} (mean of the repeats)</text>']
    for i, (name, parts) in enumerate(rows):
        y = 34 + i * (bar_h + gap)
        body.append(f'<text class="t" x="{left - 10}" y="{y + 17}" text-anchor="end">{escape(name)}</text>')
        x = left
        keys = [k for k in ("good", "warning", "critical") if parts.get(k)]
        for j, k in enumerate(keys):
            w = parts[k] / total * width
            last = j == len(keys) - 1
            body.append(rounded_bar(x, y, max(0, w - (0 if last else 2)), bar_h, fill=STATUS[k], right_round=last))
            icon = {"good": "✓", "warning": "?", "critical": "✗"}[k]
            if w > 34:
                cls = "w" if k != "warning" else "t"
                body.append(f'<text class="{cls}" x="{x + 8}" y="{y + 17}" style="fill:{"#fff" if k != "warning" else "#0b0b0b"}">'
                            f'{icon} {parts[k]:g}</text>')
            x += w
    lx = left
    for k in ("good", "warning", "critical"):
        body.append(f'<rect x="{lx}" y="{height - 14}" width="10" height="10" rx="2" fill="{STATUS[k]}"/>'
                    f'<text class="m" x="{lx + 14}" y="{height - 5}">{escape(labels[k])}</text>')
        lx += 18 + 7 * len(labels[k])
    return svg(left + width + 40, height + 6, "".join(body), title)


def bars_with_refs(rows, refs, title, unit):
    """One series: mean per row, with thin min-max whisker over repeats. refs: [(label, value)]."""
    left, width, bar_h, gap = 230, 420, 22, 16
    values = [v for _, mean, lo, hi in rows for v in (mean, lo, hi)] + [v for _, v in refs] + [0]
    lo_v, hi_v = min(values), max(values)
    pad = (hi_v - lo_v) * 0.08
    lo_v, hi_v = lo_v - pad, hi_v + pad
    X = lambda v: left + (v - lo_v) / (hi_v - lo_v) * width  # noqa: E731
    height = 60 + len(rows) * (bar_h + gap)
    body = [f'<line class="grid" x1="{X(0):.1f}" x2="{X(0):.1f}" y1="26" y2="{height - 24}"/>',
            f'<text class="m" x="{X(0):.1f}" y="{height - 8}" text-anchor="middle">0</text>',
            f'<text class="m" x="{left}" y="16">{escape(unit)}</text>']
    for label, v in refs:
        near_end = X(v) > left + width * 0.75  # keep the label inside the picture
        body.append(f'<line class="ref" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="26" y2="{height - 24}"/>'
                    f'<text class="m" x="{X(v) + (-4 if near_end else 4):.1f}" y="{height - 26}" '
                    f'text-anchor="{"end" if near_end else "start"}">{escape(label)} {v:g}</text>')
    for i, (name, mean, lo, hi) in enumerate(rows):
        y = 32 + i * (bar_h + gap)
        body.append(f'<text class="t" x="{left - 10}" y="{y + 15}" text-anchor="end">{escape(name)}</text>')
        x0, x1 = sorted((X(0), X(mean)))
        body.append(f'<rect class="s1" x="{x0:.1f}" y="{y}" width="{max(1, x1 - x0):.1f}" height="{bar_h}" rx="4"/>')
        if hi > lo:
            body.append(f'<line class="mean" x1="{X(lo):.1f}" x2="{X(hi):.1f}" y1="{y + bar_h / 2}" y2="{y + bar_h / 2}" '
                        f'style="stroke-width:1.5"/>')
        tx = X(max(mean, hi, 0)) + 6  # negative bars: the label sits just right of zero
        body.append(f'<text class="t" x="{tx:.1f}" y="{y + 15}" style="font-weight:600">{mean:.1f}</text>')
    return svg(left + width + 70, height, "".join(body), title)


# ----------------------------------------------------------------------------- per level
def load(n):
    f = HERE / f"level{n}.json"
    return json.loads(f.read_text()) if f.exists() else None


def pct(x):
    return f"{100 * x:.0f}%"


def level1(r):
    out = ["## Level 1 · spam filter (noul)\n",
           "Accuracy on the 6 workshop messages and on 20 new messages the solutions never saw "
           "(`results/test_sets.py`). Mean over the repeats; false alarms = good messages marked spam.\n",
           "| Approach | Workshop (6) | New messages (20) | False alarms | Missed spam |", "|---|---|---|---|---|"]
    for name, runs in r["data"].items():
        acc = {s: st.mean(sum(x["got"] == x["label"] for x in run if x["split"] == s) /
                          sum(1 for x in run if x["split"] == s) for run in runs) for s in ("workshop", "holdout")}
        fa = sum(x["got"] == "spam" and x["label"] == "ok" for run in runs for x in run)
        miss = sum(x["got"] == "ok" and x["label"] == "spam" for run in runs for x in run)
        out.append(f"| {name} | {pct(acc['workshop'])} | {pct(acc['holdout'])} | {fa} in {len(runs)} runs | {miss} in {len(runs)} runs |")
    out.append("\n**What we learned:** spam is easy for Jev. Even the naive question was right every time. "
               "So in the workshop, spend the time on the *threshold* (what is worse: a false alarm or a miss?) "
               "and on Solution B's bonus: it says *why* (`prize_or_money 0.97`). "
               "Solution B made one false alarm in one run: three questions = three chances to say yes.\n")
    return out


def level2(r):
    rows, table = [], ["| Approach | Right box | Sent to a human | Wrong box (silent mistake) |", "|---|---|---|---|"]
    total = None
    for name, runs in r["data"].items():
        right = st.mean(sum(x["got"] == x["label"] for x in run) for run in runs)
        human = st.mean(sum(x["got"] == "HUMAN" for x in run) for run in runs)
        wrong = st.mean(sum(x["got"] not in (x["label"], "HUMAN") for x in run) for run in runs)
        total = len(runs[0])
        rows.append((name, {"good": right, "warning": human, "critical": wrong}))
        table.append(f"| {name} | {right:g} | {human:g} | {wrong:g} |")
    (CHARTS / "level2.svg").write_text(stacked_outcomes(
        rows, total, "Level 2: where did each message go?",
        {"unit": "messages", "good": "right box", "warning": "to a human", "critical": "wrong box"}))
    return ["## Level 2 · inbox sorter (choice + score + confidence)\n",
            f"{total} messages: the 7 workshop messages + 14 new ones, including lost items and messages that fit no box.\n",
            "![Level 2 chart](charts/level2.svg)\n", *table,
            "\n**What we learned:** the starter's confidence check did not catch the lost-item messages: "
            "Jev was *confident* they were questions. A missing box is a silent mistake. "
            "**A** (add the box) gets more right; **B** (add `other` → human) makes **zero** silent mistakes, "
            "at the price of more work for people. Pick by what a mistake costs you.\n"]


def level3(r):
    rows, table = [], ["| Approach | Correct decision | Not exact, but safe | Unsafe (ALLOWED a call that needed a human or a block) |", "|---|---|---|---|"]
    total = None

    def unsafe_one(x):
        return x["got"] == "ALLOW" and x["label"] != "ALLOW"

    for name, runs in r["data"].items():
        good = st.mean(sum(x["got"] == x["label"] for x in run) for run in runs)
        unsafe = st.mean(sum(unsafe_one(x) for x in run) for run in runs)
        careful = st.mean(sum(x["got"] != x["label"] and not unsafe_one(x) for x in run) for run in runs)
        total = len(runs[0])
        rows.append((name, {"good": good, "warning": careful, "critical": unsafe}))
        table.append(f"| {name} | {good:g} | {careful:g} | {unsafe:g} |")
        examples = sorted({f'`{x["tool"]}` ({x["label"]} → {x["got"]})' for run in runs for x in run if unsafe_one(x)})
        if examples:
            table.append(f"| ↳ unsafe ones | {', '.join(examples)} | | |")
    (CHARTS / "level3.svg").write_text(stacked_outcomes(
        rows, total, "Level 3: safety gate decisions",
        {"unit": "tool calls", "good": "correct", "warning": "not exact, but safe", "critical": "unsafe"}))
    return ["## Level 3 · agent safety gate (many questions, one call)\n",
            f"{total} tool calls: the 5 workshop calls + the red-team call + 10 new ones, each labelled ALLOW / ASK_HUMAN / BLOCK. "
            "\"Unsafe\" = the gate said ALLOW where the label says ASK_HUMAN or BLOCK. \"Not exact, but safe\" = for example "
            "ASK_HUMAN where the label says BLOCK: a person still checks it.\n",
            "![Level 3 chart](charts/level3.svg)\n", *table,
            "\n**What we learned:** **A** (Jev judges, code decides) was the most accurate and never unsafe. "
            "**B** (Jev decides from a written policy) is shorter code, but it allowed a message to the staff group "
            "without asking: rules in text are softer than rules in code. Numbers (the NT$200 limit) belong in code.\n"]


def level4(r):
    data = r["data"]
    best = data["best possible"][0]
    rows, table = [], ["| Approach | Mean, 10 days | Workshop days 1 / 2 / 3 | % of best possible |", "|---|---|---|---|"]
    best_mean = st.mean(best.values())
    for name, runs in data.items():
        means = [st.mean(run.values()) for run in runs]
        m = st.mean(means)
        first = runs[0]
        if name != "best possible":
            rows.append((name, m, min(means), max(means)))
        table.append(f"| {name} | {m:.1f} | {first['1']} / {first['2']} / {first['3']} | {pct(m / best_mean)} |")
    rules = st.mean(data["rules (no AI)"][0].values())
    (CHARTS / "level4.svg").write_text(bars_with_refs(
        rows, [("best", round(best_mean, 1))], "Level 4: tea shop points per day",
        f"points per day, mean of 10 days × {r['repeats']} repeats (line = lowest to highest repeat)"))
    return ["## Level 4 · tea shop (decisions in a loop)\n",
            f"10 different days (seeds 1–10; the workshop uses 1–3), {r['repeats']} repeats each. "
            "\"Best possible\" comes from trying every plan (`level4-tea-shop/best_possible.py`).\n",
            "![Level 4 chart](charts/level4.svg)\n", *table,
            f"\n**What we learned:** the starter Jev loses to plain if/else rules ({rules:.0f}) because the question says "
            "\"this round\" and Jev answers exactly that. **A** only changes words (ask for the whole day, describe the rush) "
            "and ties the rules. **B** adds easy guard rules in code and reaches "
            f"{pct(st.mean(st.mean(x.values()) for x in data['B: A + guard rules in code']) / best_mean)} of the best possible. "
            "The repeats hardly move: in this small game Jev's answers are stable.\n"]


def level5(r):
    data = r["data"]
    cfg = data["configs"]
    mean = {n: st.mean(x["score"] for x in runs) for n, runs in cfg.items()}
    rules = mean["simple rules (no AI)"]
    rows = [(n, mean[n], min(x["score"] for x in runs), max(x["score"] for x in runs)) for n, runs in cfg.items()]
    (CHARTS / "level5.svg").write_text(bars_with_refs(
        rows, [("simple rules", round(rules, 1))], "Level 5: score over one stream",
        f"total score after {data['ticks']} ticks, exam traffic (seed {data['seed']})"))
    erows = [(n, st.mean(x["energy"] for x in runs), min(x["energy"] for x in runs), max(x["energy"] for x in runs))
             for n, runs in cfg.items()]
    (CHARTS / "level5-energy.svg").write_text(bars_with_refs(
        erows, [], "Level 5: energy over one stream", "energy used (idling vehicle-ticks): less is better"))
    table = ["| Officer | Score | Energy | Points per 50 ticks | Walks | People waiting at the end | Input tokens per run |",
             "|---|---|---|---|---|---|---|"]
    for n, runs in cfg.items():
        x = runs[0]
        blocks = " / ".join(f"{v:.0f}" for v in x["blocks"])
        tokens = f"{st.mean(y['tokens'] for y in runs) / 1e6:.2f}M" if x["tokens"] else "no AI"
        score = " / ".join(f"{y['score']:.0f}" for y in runs)
        table.append(f"| {n} | {score} | {st.mean(y['energy'] for y in runs):,.0f} | {blocks} | {x['walks']} | "
                     f"{x['pedestrians_at_end']} | {tokens} |")
    return ["## Level 5 · Jev runs three traffic lights as one smart state machine\n",
            f"One stream of {data['ticks']} ticks on Zhongxiao E. Rd (Fuxing, Dunhua, Guangfu), the exam traffic "
            f"(seed {data['seed']}). Every tick Jev reads the history so far: what each junction saw (6 cells down each "
            "road), the decisions, the points and the energy of every past tick, and the totals. "
            f"{r['repeats']} run(s) per Jev officer: each run is about 190 calls, so we keep it small.\n",
            "![Level 5 score](charts/level5.svg)\n", "![Level 5 energy](charts/level5-energy.svg)\n", *table,
            "\n**What we learned:**\n",
            "- **Raw history helped only a little** (current tick only -722, full history -450). Jev still rarely "
            "chose walk, and waiting pedestrians cost the most points. The cause is in the history (the `p` numbers "
            "grow, the points sink), but Jev answers one question at a time: it does not work out \"my points fall "
            "BECAUSE nobody walked\" from 200 lines of log. And the full history costs about 11x the tokens.",
            "- **Digested history works much better.** With the coach's LESSONS (\"in moments like this, walk was +0.8 "
            "better\") Jev walks about 3 times as often and scores far higher. Solution A's points per 50 ticks rise "
            "during the stream: that is learning, inside one stream.",
            "- **A short history plus lessons was the best Jev, for a quarter of the tokens** (solution B).",
            "- **The simple rules are still the best.** Three good if/else rules are a strong opponent. Beat them!",
            "- **One run each, and runs differ a lot.** While building this level the same set-ups scored: current tick "
            "only -1,187, full history -2,387, A -88, B -369. Jev's answers jitter a little and one changed light changes "
            "the rest of the stream. Compare on the exam seed, and repeat when you can.\n"]


def main():
    CHARTS.mkdir(exist_ok=True)
    results = {n: load(n) for n in range(1, 6)}
    have = {n: r for n, r in results.items() if r}
    total_cost = sum(r["cost_usd"] for r in have.values())
    total_calls = sum(r["calls"] for r in have.values())
    first = next(iter(have.values()))
    lines = [
        "# Real results: every solution, measured\n",
        f"Measured with the **real Jev API** (`{first['model']}`) on {first['date']}, through the workshop proxy. "
        f"{total_calls:,} calls in total, **US${total_cost:.2f}**. Made by `results/run_all.py`, "
        "drawn by `results/report.py`. Run them again to check (or after a new Jev version).\n",
        "| Level | Starter | Solution A | Solution B | Best idea |", "|---|---|---|---|---|",
    ]
    summary = {
        1: ("naive question", "one question + criteria", "three small questions", "spam is easy: work on the threshold"),
        2: ("misroutes lost items", "add the missing box", "add `other` → human", "a missing box = silent mistakes"),
        3: ("asks for small refunds", "Jev judges, code decides", "Jev decides from a policy", "keep the rules in code"),
        4: ("loses to if/else", "better words", "better words + guard rules", "ask for the whole day; guard rules"),
        5: ("reads all history, rarely walks", "history + coach lessons", "last 20 ticks + lessons",
            "digest the history into lessons"),
    }
    for n, (a, b, c, d) in summary.items():
        if n in have:
            lines.append(f"| {n} | {a} | {b} | {c} | {d} |")
    lines.append("")
    for n, fn in ((1, level1), (2, level2), (3, level3), (4, level4), (5, level5)):
        if n in have:
            lines += fn(have[n])
            lines.append(f"<sub>Level {n}: {have[n]['calls']} calls, {have[n]['input_tokens']:,} input tokens, "
                         f"US${have[n]['cost_usd']}, {have[n]['seconds']} s.</sub>\n")
    lines += ["## How to repeat this\n",
              "```bash\ncd workshop\nexport JEV_BASE_URL=https://your-proxy.example.com JEV_API_KEY=jvp_... JEV_MOCK=0\n"
              "python results/run_all.py --repeats 3    # about US$0.30\npython results/report.py\n```\n"]
    (HERE / "RESULTS.md").write_text("\n".join(lines))
    print(f"Wrote {HERE / 'RESULTS.md'} and {len(list(CHARTS.glob('*.svg')))} charts.")


if __name__ == "__main__":
    main()
