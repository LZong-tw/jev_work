"""
jev.py - a tiny client for the TypeSafe Jev API (POST /v1/systemone). Python 3.8+, no pip install.

    from jev import decide, noul, choice, score, show

    result = decide(
        state="I waited 40 minutes and my bubble tea was cold.",
        questions={"happy": noul("Is the customer happy?")},
    )
    print(result["answers"]["happy"]["noul"])   # e.g. 0.03

Settings come from environment variables or a .env file next to this file:

    JEV_BASE_URL   the workshop proxy, e.g. https://jev-proxy.example.com
                   (or the real API: https://api.typesafe.ai)
    JEV_API_KEY    your workshop key (jvp_...)
    JEV_MODEL      optional: jev-latest (default) or jev-preview
    JEV_MOCK=1     offline practice mode: fake answers, no network, no key
    JEV_CACHE      optional: a file that saves every answer. The same request again
                   gets the same answer from the file: repeatable runs, and free.

The official SDK names also work: TYPESAFE_BASE_URL, TYPESAFE_API_KEY, TYPESAFE_DEFAULT_MODEL.
API reference: https://docs.typesafe.ai/api

Run `python jev.py` to check your setup.
"""

import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_env_file(os.path.join(os.getcwd(), ".env"))
_load_env_file(os.path.join(HERE, ".env"))


_mock_warned = False


class JevError(Exception):
    def __init__(self, status, message, code=None, request_id=None):
        super().__init__(f"[{status}] {message}" + (f" ({code})" if code else ""))
        self.status, self.message, self.code, self.request_id = status, message, code, request_id


# ---------------------------------------------------------------------------
# Question builders. They only build plain dicts, so you can always see the
# exact JSON that goes to the API.
# ---------------------------------------------------------------------------

def noul(instructions, yes=None, no=None):
    """Yes/no question. Answer: {"noul": 0.0 .. 1.0}, the chance it is YES.
    Optional: say exactly what counts as yes and as no:
        noul("Is this spam?", yes="unsolicited ads or scams", no="normal messages from people")"""
    q = {"type": "noul", "instructions": instructions}
    if yes is not None or no is not None:
        q["criteria"] = {"true": yes, "false": no}
    return q


def choice(instructions, criteria):
    """Pick one label. criteria = {"label": "what it means", ...} (up to 255 labels).
    A description can be None when the label says it all: {"calm": None, "angry": None}."""
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions, levels):
    """Rate on an ordered scale. levels = ["lowest", ..., "highest"] (up to 10 levels).
    Answer: {"score": 0.0 .. len(levels)-1}, can be a fraction like 2.4, plus a "legend"."""
    return {"type": "score", "instructions": instructions, "criteria": levels}


# ---------------------------------------------------------------------------
# The API call
# ---------------------------------------------------------------------------

PRICE_PER_MILLION_INPUT_TOKENS = 0.042  # US$42 per billion input tokens; output tokens are free


def _env(*names):
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    return ""


def config():
    return {
        "base_url": _env("JEV_BASE_URL", "TYPESAFE_BASE_URL").rstrip("/"),
        "api_key": _env("JEV_API_KEY", "TYPESAFE_API_KEY"),
        "model": _env("JEV_MODEL", "TYPESAFE_DEFAULT_MODEL") or "jev-latest",
        "mock": os.environ.get("JEV_MOCK", "0").lower() in ("1", "true", "yes", "on"),
    }


def cost_usd(result):
    """What a call cost, from its token usage."""
    return result.get("usage", {}).get("input_tokens", 0) * PRICE_PER_MILLION_INPUT_TOKENS / 1e6


def _error(e):
    """Turn an HTTP error into (message, code). TypeSafe sends {"detail": ...}."""
    try:
        err = json.loads(e.read().decode("utf-8"))
    except Exception:
        return e.reason, None
    return _detail(err)


def _detail(err):
    """{"detail": {"error_type", "message"}} or {"detail": "text"} (400, 401, ...)
    or {"detail": [{"type", "loc", "msg"}, ...]} (422 validation errors)."""
    detail = err.get("detail", err) if isinstance(err, dict) else err
    if isinstance(detail, dict):
        return detail.get("message") or detail.get("error") or str(detail), detail.get("error_type") or detail.get("code")
    if isinstance(detail, list) and detail:  # validation errors (HTTP 422)
        first = detail[0]
        where = ".".join(str(x) for x in first.get("loc", [])[1:])
        return f"{where}: {first.get('msg')}", first.get("type")
    return str(detail), None


def _request(path, body=None, retries=3, timeout=30):
    cfg = config()
    if not cfg["base_url"] or not cfg["api_key"]:
        raise JevError(0, "Set JEV_BASE_URL and JEV_API_KEY (or JEV_MOCK=1). See workshop/.env.example")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            cfg["base_url"] + path,
            data=data,
            method="POST" if data is not None else "GET",
            headers={
                "Authorization": "Bearer " + cfg["api_key"],
                "Content-Type": "application/json",
                "User-Agent": "jev-workshop/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 408 = timeout, 429 = slow down, 5xx (529 = overloaded) = server busy: wait and try again.
            if (e.code in (408, 429) or 500 <= e.code < 600) and attempt < retries:
                time.sleep(min(_retry_wait(e.headers, attempt), 20))
                continue
            message, code = _error(e)
            raise JevError(e.code, message, code, e.headers.get("x-typesafe-request-id")) from None
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise JevError(0, f"Cannot reach {cfg['base_url']}: {e.reason}") from None


def _retry_wait(headers, attempt):
    """Seconds to wait: the server's retry-after-ms or Retry-After header, else 1, 2, 4... seconds."""
    for name, scale in (("retry-after-ms", 1000.0), ("Retry-After", 1.0)):
        try:
            return float(headers.get(name)) / scale
        except (TypeError, ValueError):
            pass
    return 2 ** attempt


MOCK_MODELS = [
    {"name": "jev-latest", "description": "Mock of the latest Jev model (keyword matching, not the real model).",
     "release_date": "2026-09-10T18:38:01.391457+00:00"},
    {"name": "jev-preview", "description": "Mock of the Jev preview model (keyword matching, not the real model).",
     "release_date": "2026-09-10T18:39:06.057655+00:00"},
]


def models():
    """GET /v1/models: {"models": [{"name", "description", "release_date"}, ...]}."""
    if config()["mock"]:
        return {"models": [dict(m) for m in MOCK_MODELS]}
    return _request("/v1/models")


def decide(state, questions, model=None, retries=3, timeout=30, cache=None):
    """POST /v1/systemone. Returns the JSON response as a dict:
    {"model": ..., "answers": {question_id: {...}}, "usage": {"input_tokens": ..., "output_tokens": ...}}

    cache: a file name (or set JEV_CACHE). Jev's probabilities move a little between two
    identical calls; with a cache the same request always gets the same saved answer."""
    cfg = config()
    body = {"model": model or cfg["model"], "state": state, "questions": questions}
    cache = cache or os.environ.get("JEV_CACHE")
    key = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest() if cache else None
    if cache:
        with _cache_lock:
            saved = _cache(cache).get(key)
        if saved is not None:
            return saved

    if cfg["mock"]:
        global _mock_warned
        if not _mock_warned:
            print("[jev] MOCK MODE: fake keyword-matching answers, not the real model.", file=sys.stderr)
            _mock_warned = True
        result = mock_decide(body)
    else:
        result = _request("/v1/systemone", body, retries=retries, timeout=timeout)
    if cache:
        with _cache_lock:  # several officers may answer at the same time
            _cache(cache)[key] = result
            with open(cache, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "result": result}) + "\n")
    return result


_caches = {}
_cache_lock = threading.Lock()


def _cache(path):
    """The answers saved in a cache file (one JSON line per answer), loaded once."""
    path = os.path.abspath(path)
    if path not in _caches:
        _caches[path] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        _caches[path][row["key"]] = row["result"]
    return _caches[path]


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def bar(p, width=20):
    p = max(0.0, min(1.0, float(p)))
    full = int(round(p * width))
    return "#" * full + "." * (width - full)


def show(result, title=None):
    """Print the answers in a friendly way."""
    if title:
        print(f"\n=== {title} ===")
    for qid, a in result["answers"].items():
        t = a.get("type")
        if t == "noul" or "noul" in a:
            print(f"  {qid:<16} noul   {a['noul']:.2f}  [{bar(a['noul'])}]")
        elif t == "choice" or "choice" in a:
            print(f"  {qid:<16} choice {a['choice']!r}  (confidence {a.get('confidence', 0):.2f})")
            for label, p in sorted(a.get("probabilities", {}).items(), key=lambda kv: -kv[1]):
                print(f"  {'':<16}   {label:<16} {p:.2f} [{bar(p)}]")
        elif t == "score" or "score" in a:
            print(f"  {qid:<16} score  {a['score']:.2f}  (confidence {a.get('confidence', 0):.2f})")
        else:
            print(f"  {qid:<16} {a}")
    u = result.get("usage", {})
    if u:
        print(f"  usage: {u.get('input_tokens', '?')} input tokens, ${cost_usd(result):.6f}")


# ---------------------------------------------------------------------------
# Mock mode: a keyword-matching fake that returns the same JSON shape.
# Good for practice without internet. It is NOT smart. Use the real API for
# real results.
# ---------------------------------------------------------------------------

_STOP = set(
    "a an the is are was were be been to of in on at for and or but if then this that these those it its "
    "with as by from about into than so do does did not no yes should would could can will what which who "
    "how why when where your you i we they he she my our their me us them there here any all some more most "
    "less very just only".split()
)
_POS = {"good", "great", "love", "like", "happy", "delicious", "amazing", "best", "nice", "thank", "excellent",
        "fresh", "friendly", "fast", "recommend", "perfect"}
_NEG = {"bad", "terrible", "hate", "angry", "cold", "late", "slow", "wrong", "broken", "refund", "worst", "rude",
        "dirty", "never", "charged", "missing", "sick", "complain", "disappointed", "delete", "transfer", "all"}
_URG = {"urgent", "now", "immediately", "asap", "emergency", "today", "help", "fire", "ambulance", "danger",
        "critical", "stuck", "blocked"}


def _stem(w):
    return re.sub(r"(ing|ed|es|s)$", "", w)[:8]


def _tokens(text):
    return [_stem(w) for w in re.findall(r"[^\W_]+|_", str(text).lower()) if w not in _STOP and w != "_"]


_POS_S, _NEG_S, _URG_S = ({_stem(w) for w in s} for s in (_POS, _NEG, _URG))


def _jitter(seed):
    h = 2166136261
    for ch in seed:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return (h % 1000) / 1000


def _softmax(xs, temp):
    m = max(xs)
    e = [math.exp((x - m) / temp) for x in xs]
    s = sum(e)
    return [v / s for v in e]


def _polarity(instr, st):
    ins = set(instr)
    pos = sum(w in _POS_S for w in st)
    neg = sum(w in _NEG_S for w in st)
    urg = sum(w in _URG_S for w in st)
    if ins & _POS_S or _stem("positive") in ins:
        return pos - neg
    if ins & _NEG_S or _stem("negative") in ins or _stem("upset") in ins or _stem("dangerous") in ins:
        return neg - pos
    if ins & _URG_S or _stem("escalate") in ins:
        return urg + neg * 0.5
    return 0


def _is_text(v):
    return isinstance(v, (str, list, dict))  # str | object | array


def _text(v):
    return "" if v is None else v if isinstance(v, str) else json.dumps(v)


def _err(kind, loc, msg, value):
    return {"type": kind, "loc": ["body"] + list(loc), "msg": msg, "input": value}


def _text_errors(loc, value):
    return [_err("string_type", loc + ["str"], "Input should be a valid string", value),
            _err("dict_type", loc + ["dict[any,any]"], "Input should be a valid dictionary", value),
            _err("list_type", loc + ["list[any]"], "Input should be a valid list", value)]


_USAGE_ERROR = {"detail": {"error_type": "api_usage_error", "message": "Invalid request."}}
_KNOWN_MODEL = re.compile(r"^(jev-latest|jev-preview|jev-\d+\.\d+\.\d+)$")


def _question_errors(qid, q):
    if not isinstance(q, dict) or "type" not in q:
        return [_err("union_tag_not_found", ["questions", qid], "Unable to extract tag using discriminator 'type'", q)]
    at, errors = ["questions", qid, q["type"]], []
    if q.get("instructions") is not None and not _is_text(q["instructions"]):
        errors += _text_errors(at + ["instructions"], q["instructions"])
    crit = q.get("criteria")
    if q["type"] == "choice":
        if crit is None:
            errors.append(_err("missing", at + ["criteria"], "Field required", q))
        elif not isinstance(crit, dict):
            errors.append(_err("dict_type", at + ["criteria"], "Input should be a valid dictionary", crit))
        else:
            for option, value in crit.items():
                if value is not None and not _is_text(value):
                    errors += _text_errors(at + ["criteria", option], value)
    elif q["type"] == "score":
        if crit is None:
            errors.append(_err("missing", at + ["criteria"], "Field required", q))
        elif not isinstance(crit, list):
            errors.append(_err("list_type", at + ["criteria"], "Input should be a valid list", crit))
        elif not crit:
            errors.append(_err("too_short", at + ["criteria"], "List should have at least 1 item after validation, not 0", crit))
    elif crit is not None and not isinstance(crit, dict):
        errors.append(_err("dict_type", at + ["criteria"], "Input should be a valid dictionary", crit))
    return errors


def mock_validate(body):
    """Check a request like the real API does. Returns (status, error_body), or None when it is fine.
    422 = the JSON has the wrong shape; 400 = the shape is fine but the request makes no sense."""
    if not isinstance(body, dict):
        return 422, {"detail": [_err("model_attributes_type", [], "Input should be a valid dictionary or object to extract fields from", body)]}
    errors = []
    if body.get("model") is None:
        errors.append(_err("missing", ["model"], "Field required", body))
    elif not isinstance(body["model"], str):
        errors.append(_err("string_type", ["model"], "Input should be a valid string", body["model"]))
    if body.get("state") is not None and not _is_text(body["state"]):
        errors += _text_errors(["state"], body["state"])
    questions = body.get("questions")
    if questions is None:
        errors.append(_err("missing", ["questions"], "Field required", body))
    elif not isinstance(questions, dict):
        errors.append(_err("dict_type", ["questions"], "Input should be a valid dictionary", questions))
    elif not questions:
        errors.append(_err("too_short", ["questions"], "Dictionary should have at least 1 item after validation, not 0", questions))
    else:
        for qid, q in questions.items():
            if isinstance(q, dict) and "type" in q and q["type"] not in ("noul", "choice", "score"):
                return 400, _USAGE_ERROR
            errors += _question_errors(qid, q)
    if errors:
        return 422, {"detail": errors}
    if body.get("state") is None:
        return 422, {"detail": [_err("missing", ["state"], "Field required", body)]}
    if set(body) - {"model", "state", "questions"}:
        return 400, _USAGE_ERROR
    if not _KNOWN_MODEL.match(body["model"]):
        return 400, {"detail": {"error_type": "api_usage_error", "message": f"Unknown model: {body['model']}"}}
    for qid, q in questions.items():
        if q["type"] == "noul" and q.get("instructions") is None and q.get("criteria") is None:
            return 400, {"detail": f"Noul question must have criteria or instructions: {qid}"}
        if q["type"] == "choice" and not q["criteria"]:
            return 400, {"detail": f"Choice question must have at least one choice: {qid}"}
        if q["type"] == "choice" and len(q["criteria"]) > 255:
            return 400, {"detail": "Too many choices. Must have at most 255 choices."}
        if q["type"] == "score" and len(q["criteria"]) > 10:
            return 400, {"detail": "Too many score levels. Must have at most 10 levels."}
    return None


def mock_decide(body):
    invalid = mock_validate(body)
    if invalid:
        status, err = invalid
        message, code = _detail(err)
        raise JevError(status, message, code)
    state = body["state"]
    text = _text(state)
    st = _tokens(text)
    sset = set(st)
    answers = {}
    for qid, q in body["questions"].items():
        seed = text + "|" + qid
        instr = _tokens(_text(q.get("instructions")))
        if q["type"] == "noul":
            instr += _tokens(_text(q.get("criteria")))
            signal = _polarity(instr, st) * 0.9 + len(set(instr) & sset) * 0.35 - 0.6
            p = 1 / (1 + math.exp(-signal)) * 0.9 + 0.05 + (_jitter(seed) - 0.5) * 0.04
            answers[qid] = {"type": "noul", "noul": round(min(0.99, max(0.01, p)), 2)}
        elif q["type"] == "choice":
            labels = list(q["criteria"])
            raw = [len(set(_tokens(l.replace("_", " ") + " " + _text(q["criteria"][l]))) & sset) + _jitter(seed + l) * 0.3
                   for l in labels]
            probs = _softmax(raw, 0.6)
            best = probs.index(max(probs))
            answers[qid] = {"type": "choice", "choice": labels[best], "confidence": round(probs[best], 2),
                            "probabilities": {l: round(p, 2) for l, p in zip(labels, probs)}}
        else:
            levels = q["criteria"]
            pol = _polarity(instr, st)
            raw = [len(set(_tokens(_text(lv))) & sset) + pol * i / max(1, len(levels) - 1) + _jitter(seed + str(i)) * 0.2
                   for i, lv in enumerate(levels)]
            probs = _softmax(raw, 0.7)
            answers[qid] = {"type": "score", "score": round(sum(i * p for i, p in enumerate(probs)), 2),
                            "confidence": round(max(probs), 2),
                            "legend": {str(i): lv for i, lv in enumerate(levels)},
                            "probabilities": {str(i): round(p, 2) for i, p in enumerate(probs)}}
    tokens = len(json.dumps(body)) // 4
    return {"model": "jev-mock", "answers": answers,
            "usage": {"input_tokens": tokens, "output_tokens": 24 * len(answers)}}


# ---------------------------------------------------------------------------
# `python jev.py` = setup check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = config()
    print(f"Python      {sys.version.split()[0]}")
    if cfg["mock"]:
        print("Mode        MOCK (offline practice, fake answers)")
    else:
        print(f"Base URL    {cfg['base_url'] or '(missing! set JEV_BASE_URL)'}")
        key = cfg["api_key"]
        print(f"API key     {key[:8] + '...' + key[-4:] if len(key) > 12 else '(missing! set JEV_API_KEY)'}")
    try:
        t0 = time.time()
        r = decide("I love the brown sugar milk tea here! Super fresh pearls.",
                   {"happy": noul("Is the customer happy?")}, retries=1)
        print(f"Test call   OK in {time.time() - t0:.2f}s, model {r.get('model')}")
        show(r)
        print("\nYou are ready.")
    except JevError as e:
        print(f"Test call   FAILED: {e}")
        sys.exit(1)
