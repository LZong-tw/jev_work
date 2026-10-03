// A tiny fake Jev for rehearsals and tests. It speaks the same protocol as
// POST /v1/systemone, but the "intelligence" is simple keyword overlap.
// Never present mock answers as real model output.

const STOP = new Set(
  'a an the is are was were be been to of in on at for and or but if then this that these those it its with as by from about into than so do does did not no yes should would could can will what which who whom how why when where your you i we they he she my our their me us them there here any all some more most less very just only'.split(' '),
);

const POSITIVE = ['good', 'great', 'love', 'like', 'happy', 'delicious', 'amazing', 'best', 'nice', 'thank', 'excellent', 'fresh', 'friendly', 'fast', 'recommend', 'perfect'];
const NEGATIVE = ['bad', 'terrible', 'hate', 'angry', 'cold', 'late', 'slow', 'wrong', 'broken', 'refund', 'worst', 'rude', 'dirty', 'never', 'charged', 'missing', 'sick', 'complain', 'disappointed'];
const URGENT = ['urgent', 'now', 'immediately', 'asap', 'emergency', 'today', 'help', 'fire', 'ambulance', 'danger', 'critical', 'stuck', 'blocked'];

function stem(word) {
  return word.replace(/(ing|ed|es|s)$/u, '').slice(0, 8);
}

export function tokens(text) {
  return String(text)
    .toLowerCase()
    .split(/[^\p{L}\p{N}_]+/u)
    .filter((w) => w && !STOP.has(w))
    .map(stem);
}

function stateText(state) {
  return typeof state === 'string' ? state : JSON.stringify(state);
}

// Instructions and criteria can be a string, an object, an array or null.
const text = (v) => (v == null ? '' : stateText(v));

// Deterministic jitter in [0, 1) so answers are stable for the same input.
function jitter(seed) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

function overlap(a, bSet) {
  let n = 0;
  for (const t of new Set(a)) if (bSet.has(t)) n += 1;
  return n;
}

function count(list, set) {
  return list.reduce((n, w) => n + (set.has(w) ? 1 : 0), 0);
}

function softmax(values, temperature = 1) {
  const max = Math.max(...values);
  const exps = values.map((v) => Math.exp((v - max) / temperature));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map((e) => e / sum);
}

const r2 = (n) => Math.round(n * 100) / 100;
const POS = new Set(POSITIVE.map(stem));
const NEG = new Set(NEGATIVE.map(stem));
const URG = new Set(URGENT.map(stem));

function polarity(instructionTokens, stateTokens) {
  const instr = new Set(instructionTokens);
  const pos = count(stateTokens, POS);
  const neg = count(stateTokens, NEG);
  const urg = count(stateTokens, URG);
  if ([...POS].some((w) => instr.has(w)) || instr.has(stem('positive'))) return pos - neg;
  if ([...NEG].some((w) => instr.has(w)) || instr.has(stem('negative'))) return neg - pos;
  if ([...URG].some((w) => instr.has(w)) || instr.has(stem('escalate'))) return urg + neg * 0.5;
  return 0;
}

function answerNoul(q, st, seed) {
  const it = tokens(text(q.instructions) + ' ' + text(q.criteria));
  const s = new Set(st);
  const signal = polarity(it, st) * 0.9 + overlap(it, s) * 0.35 - 0.6;
  const p = 1 / (1 + Math.exp(-signal)) * 0.9 + 0.05 + (jitter(seed) - 0.5) * 0.04;
  return { type: 'noul', noul: r2(Math.min(0.99, Math.max(0.01, p))) };
}

function answerChoice(q, st, seed) {
  const labels = Object.keys(q.criteria || {});
  const s = new Set(st);
  const raw = labels.map((label) => {
    const desc = tokens(`${label.replace(/_/g, ' ')} ${text(q.criteria[label])}`);
    return overlap(desc, s) + jitter(seed + label) * 0.3;
  });
  const probs = softmax(raw, 0.6);
  const best = probs.indexOf(Math.max(...probs));
  const probabilities = Object.fromEntries(labels.map((l, i) => [l, r2(probs[i])]));
  return { type: 'choice', choice: labels[best], confidence: r2(probs[best]), probabilities };
}

function answerScore(q, st, seed) {
  const levels = q.criteria || [];
  const s = new Set(st);
  const pol = polarity(tokens(text(q.instructions)), st);
  const raw = levels.map((level, i) => overlap(tokens(text(level)), s) + (pol * i) / Math.max(1, levels.length - 1) + jitter(seed + i) * 0.2);
  const probs = softmax(raw, 0.7);
  const score = probs.reduce((acc, p, i) => acc + p * i, 0);
  const probabilities = Object.fromEntries(probs.map((p, i) => [String(i), r2(p)]));
  const legend = Object.fromEntries(levels.map((level, i) => [String(i), level]));
  return { type: 'score', score: r2(score), confidence: r2(Math.max(...probs)), legend, probabilities };
}

// ---------------------------------------------------------------------------
// Validation, copied from the real API's answers (see test/fixtures/systemone-cases.json):
// shape problems are 422 with a FastAPI/pydantic "detail" list; meaning problems are 400.
// ---------------------------------------------------------------------------

export const MOCK_MODELS = [
  { name: 'jev-latest', description: 'Mock of the latest Jev model (keyword matching, not the real model).', release_date: '2026-09-10T18:38:01.391457+00:00' },
  { name: 'jev-preview', description: 'Mock of the Jev preview model (keyword matching, not the real model).', release_date: '2026-09-10T18:39:06.057655+00:00' },
];
const KNOWN_MODEL = /^(jev-latest|jev-preview|jev-\d+\.\d+\.\d+)$/u;
const QUESTION_KEYS = new Set(['model', 'state', 'questions']);

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isText = (v) => typeof v === 'string' || Array.isArray(v) || isObject(v); // str | object | array
const usageError = (message = 'Invalid request.') => ({ status: 400, body: { detail: { error_type: 'api_usage_error', message } } });
const plain400 = (message) => ({ status: 400, body: { detail: message } });
const err = (type, loc, msg, input) => ({ type, loc: ['body', ...loc], msg, input });
const textErrors = (loc, input) => [
  err('string_type', [...loc, 'str'], 'Input should be a valid string', input),
  err('dict_type', [...loc, 'dict[any,any]'], 'Input should be a valid dictionary', input),
  err('list_type', [...loc, 'list[any]'], 'Input should be a valid list', input),
];

function questionErrors(id, q) {
  const errors = [];
  if (!isObject(q) || q.type === undefined) {
    return [err('union_tag_not_found', ['questions', id], "Unable to extract tag using discriminator 'type'", q)];
  }
  const at = ['questions', id, q.type];
  if (q.instructions != null && !isText(q.instructions)) errors.push(...textErrors([...at, 'instructions'], q.instructions));
  if (q.type === 'choice') {
    if (q.criteria == null) errors.push(err('missing', [...at, 'criteria'], 'Field required', q));
    else if (!isObject(q.criteria)) errors.push(err('dict_type', [...at, 'criteria'], 'Input should be a valid dictionary', q.criteria));
    else {
      for (const [option, value] of Object.entries(q.criteria)) {
        if (value !== null && !isText(value)) errors.push(...textErrors([...at, 'criteria', option], value));
      }
    }
  } else if (q.type === 'score') {
    if (q.criteria == null) errors.push(err('missing', [...at, 'criteria'], 'Field required', q));
    else if (!Array.isArray(q.criteria)) errors.push(err('list_type', [...at, 'criteria'], 'Input should be a valid list', q.criteria));
    else if (q.criteria.length === 0) {
      errors.push(err('too_short', [...at, 'criteria'], 'List should have at least 1 item after validation, not 0', q.criteria));
    }
  } else if (q.type === 'noul' && q.criteria != null && !isObject(q.criteria)) {
    errors.push(err('dict_type', [...at, 'criteria'], 'Input should be a valid dictionary', q.criteria));
  }
  return errors;
}

/** Check a /v1/systemone body like the real API. Returns { status, body } for an error, or null. */
export function validateSystemOne(body) {
  if (!isObject(body)) {
    return { status: 422, body: { detail: [err('model_attributes_type', [], 'Input should be a valid dictionary or object to extract fields from', body)] } };
  }
  const errors = [];
  if (body.model == null) errors.push(err('missing', ['model'], 'Field required', body));
  else if (typeof body.model !== 'string') errors.push(err('string_type', ['model'], 'Input should be a valid string', body.model));
  if (body.state != null && !isText(body.state)) errors.push(...textErrors(['state'], body.state));
  const { questions } = body;
  if (questions == null) errors.push(err('missing', ['questions'], 'Field required', body));
  else if (!isObject(questions)) errors.push(err('dict_type', ['questions'], 'Input should be a valid dictionary', questions));
  else if (!Object.keys(questions).length) {
    errors.push(err('too_short', ['questions'], 'Dictionary should have at least 1 item after validation, not 0', questions));
  } else {
    for (const [id, q] of Object.entries(questions)) {
      if (isObject(q) && q.type !== undefined && !['noul', 'choice', 'score'].includes(q.type)) return usageError();
      errors.push(...questionErrors(id, q));
    }
  }
  if (errors.length) return { status: 422, body: { detail: errors } };
  if (body.state == null) return { status: 422, body: { detail: [err('missing', ['state'], 'Field required', body)] } };
  if (Object.keys(body).some((k) => !QUESTION_KEYS.has(k))) return usageError();
  if (!KNOWN_MODEL.test(body.model)) return usageError(`Unknown model: ${body.model}`);

  for (const [id, q] of Object.entries(questions)) {
    if (q.type === 'noul' && q.instructions == null && q.criteria == null) return plain400(`Noul question must have criteria or instructions: ${id}`);
    if (q.type === 'choice') {
      const n = Object.keys(q.criteria).length;
      if (n === 0) return plain400(`Choice question must have at least one choice: ${id}`);
      if (n > 255) return plain400('Too many choices. Must have at most 255 choices.');
    }
    if (q.type === 'score' && q.criteria.length > 10) return plain400('Too many score levels. Must have at most 10 levels.');
  }
  return null;
}

/** A body that is not valid JSON, like the real API. */
export function invalidJson(error) {
  const pos = Number(/position (\d+)/u.exec(String(error?.message))?.[1] ?? 0);
  return { status: 422, body: { detail: [{ type: 'json_invalid', loc: ['body', pos], msg: 'JSON decode error', input: {}, ctx: { error: 'Invalid JSON' } }] } };
}

/** GET /v1/models, like the real API. */
export function mockModels() {
  return { status: 200, body: { models: MOCK_MODELS } };
}

/** POST /v1/systemone: validate like the real API and answer. Returns { status, body }. */
export function mockSystemOne(body) {
  const invalid = validateSystemOne(body);
  if (invalid) return invalid;
  const { questions } = body;
  const text = stateText(body.state);
  const st = tokens(text);
  const answers = {};
  for (const [id, q] of Object.entries(questions)) {
    const seed = `${text}|${id}`;
    if (q.type === 'noul') answers[id] = answerNoul(q, st, seed);
    else if (q.type === 'choice') answers[id] = answerChoice(q, st, seed);
    else answers[id] = answerScore(q, st, seed);
  }

  const inputTokens = Math.ceil(JSON.stringify({ state: body.state, questions }).length / 4);
  return {
    status: 200,
    body: { model: 'jev-mock', answers, usage: { input_tokens: inputTokens, output_tokens: 24 * Object.keys(answers).length } },
  };
}
