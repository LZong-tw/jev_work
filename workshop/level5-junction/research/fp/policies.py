"""Policies for sim.run: policy(history, current) -> {crossing_id: phase}, synchronous."""
import asyncio
import contextlib
import importlib.util
import io
import os
import sys

LEVEL5 = "/Users/untionglim/projects/jev_work/workshop/level5-junction"


def _load_my_jev():
    os.environ["JEV_MODE"] = "rule"          # read at import time (my_jev.py MODE)
    sys.path.insert(0, os.path.dirname(LEVEL5))
    spec = importlib.util.spec_from_file_location("my_jev_rule", f"{LEVEL5}/my_jev.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.MODE == "rule"
    return mod


_my_jev = _load_my_jev()


def current_rule(history, current):
    """The current my_jev.py decide() with JEV_MODE=rule (no network call in that mode)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(_my_jev.decide(history, current))


def fixed(phase_by_crossing):
    return lambda history, current: dict(phase_by_crossing)
