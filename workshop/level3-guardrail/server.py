"""
Level 3 in your browser: watch every tool call go through Jev's judgement and YOUR gate() rules.

    python level3-guardrail/server.py          # opens http://localhost:8003/

The page reads TOOL_CALLS and QUESTIONS from agent_gate.py, and asks gate() (your rules, also in
agent_gate.py) what to do with Jev's answers. Edit them, reload the page: it uses your new code.
Red team it: click a tool call, change it (or Jev's answers) in the Jev editor, and see what gate() says.

The "Console" tab is the challenge: type ANY command an AI agent might run; YOUR console_guard.py asks Jev
(describe() + QUESTIONS) and decides with guard(): RUN, ASK or BLOCK. Nothing ever really runs. Edit the
guard in your editor, or in the page (it saves the file, only after it compiles). Both tabs have a score.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import web  # noqa: E402

GUARD_FILE = HERE / "console_guard.py"
DECISIONS = ("RUN", "ASK", "BLOCK")


def level():
    gate = web.fresh("agent_gate")
    return {"file": "agent_gate.py", "items": gate.TOOL_CALLS, "questions": gate.QUESTIONS,
            "expected": getattr(gate, "EXPECTED", None), "console": console_level()}


def console_level():
    """The console tab: your guard's goal, questions and exam (or why it does not load: fix it in the page)."""
    try:
        console = web.fresh("console_guard")
    except Exception as e:  # a bug in console_guard.py: the page still opens, with the code to fix
        return {"file": GUARD_FILE.name, "goal": "", "questions": {}, "exam": [], "error": f"{type(e).__name__}: {e}"}
    return {"file": GUARD_FILE.name, "goal": console.GOAL, "questions": console.QUESTIONS,
            "exam": [list(x) for x in getattr(console, "EXAM", [])], "error": None}


def _command(body):
    command = body.get("command") if isinstance(body, dict) else None
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        raise web.BadRequest('send {"command": "the command the agent wants to run"}')
    return command.strip()


def console_request(body):
    """POST /api/console_request {"command", "goal"}: the request YOUR describe() and QUESTIONS make for it."""
    console, command = web.fresh("console_guard"), _command(body)
    goal = body.get("goal") if isinstance(body.get("goal"), str) and body["goal"].strip() else console.GOAL
    return {"state": console.describe(command, goal), "questions": console.QUESTIONS}


def console_guard(body):
    """POST /api/console_guard {"command", "answers"}: what YOUR guard() decides. Nothing is ever run."""
    command, answers = _command(body), body.get("answers")
    if not isinstance(answers, dict):
        raise web.BadRequest('send {"command": ..., "answers": {...the answers from Jev...}}')
    try:
        decision, reason = web.fresh("console_guard").guard(answers, command)
    except (KeyError, TypeError, ValueError) as e:
        raise web.BadRequest(f"guard() could not use these answers: {type(e).__name__}: {e}") from None
    if decision not in DECISIONS:
        raise web.BadRequest(f"guard() must return one of {', '.join(DECISIONS)} (and a reason), got {decision!r}")
    return {"decision": decision, "reason": str(reason)}


def run_gate(body):
    """POST /api/gate {"answers": {...}}: what your gate() decides for these answers."""
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict):
        raise web.BadRequest('send {"answers": {"risk": {...}, "kind": {...}, "on_goal": {...}, "tricked": {...}}}')
    try:
        decision, reason = web.fresh("agent_gate").gate(answers)
    except (KeyError, TypeError, ValueError) as e:
        raise web.BadRequest(f"gate() could not use these answers: {type(e).__name__}: {e}") from None
    return {"decision": decision, "reason": reason}


if __name__ == "__main__":
    web.serve(HERE / "sim.html", "Level 3 · Guard the AI agent", level, port=8003,
              actions={"gate": run_gate, "console_request": console_request, "console_guard": console_guard},
              files={"agent_gate.py": HERE / "agent_gate.py", "console_guard.py": GUARD_FILE})
