import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { readConfig } from '../src/config.js';
import { hashKey } from '../src/keys.js';
import { invalidJson, mockModels, mockSystemOne } from '../src/mock.js';
import { createProxy } from '../src/server.js';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-proxy-'));
const KEY = 'jvp_test_key_1';
const LIMITED = 'jvp_test_key_limited';
const BROKE = 'jvp_test_key_broke';
const OWNER_KEY = 'apikey_owner_secret';
const ANSWER = { model: 'jev-1.13.0', answers: { ok: { type: 'noul', noul: 0.9 } }, usage: { input_tokens: 100, output_tokens: 21 } };

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}

describe('proxy against a fake upstream', () => {
  let upstream;
  let proxy;
  let base;
  const seen = [];

  before(async () => {
    upstream = http.createServer((req, res) => {
      let body = '';
      req.on('data', (c) => (body += c));
      req.on('end', () => {
        seen.push({ url: req.url, headers: req.headers, body });
        if (req.url === '/v1/busy') {
          res.writeHead(529, { 'content-type': 'application/json', 'retry-after': '2', 'retry-after-ms': '1500', 'x-typesafe-request-id': 'req_busy', 'set-cookie': 'cf=1' });
          return res.end(JSON.stringify({ detail: 'Overloaded' }));
        }
        if (req.url === '/v1/boom') {
          res.writeHead(422, { 'content-type': 'application/json' });
          return res.end(JSON.stringify({ detail: [{ type: 'missing', loc: ['body', 'model'], msg: 'Field required' }] }));
        }
        res.writeHead(200, { 'content-type': 'application/json', 'x-typesafe-request-id': 'req_up123', server: 'cloudflare' });
        res.end(JSON.stringify(ANSWER));
      });
    });
    const upPort = await listen(upstream);

    const keysFile = path.join(tmp, 'keys.json');
    fs.writeFileSync(
      keysFile,
      JSON.stringify([
        { name: 'alice', key_hash: hashKey(KEY), max_cost_usd: 1 },
        { name: 'limited', key: LIMITED, rpm: 2 },
        { name: 'broke', key: BROKE, max_cost_usd: 0.3 },
        { name: 'off', key: 'jvp_off', enabled: false },
      ]),
    );
    const config = {
      ...readConfig({}),
      upstreamBaseUrl: `http://127.0.0.1:${upPort}`,
      upstreamApiKey: OWNER_KEY,
      inputPricePerMillion: 2500, // 100 tokens = US$0.25: easy budget maths in the tests
      keysFile,
      usageFile: path.join(tmp, 'usage.json'),
      quiet: true,
      noWatch: true,
    };
    proxy = createProxy(config);
    base = `http://127.0.0.1:${await listen(proxy.server)}`;
  });

  after(async () => {
    await proxy.close();
    await new Promise((r) => upstream.close(r));
  });

  const decide = (key, pathName = '/v1/systemone', extraHeaders = {}) =>
    fetch(base + pathName, {
      method: 'POST',
      headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json', cookie: 'secret=1', ...extraHeaders },
      body: JSON.stringify({ model: 'jev-latest', state: 'hi', questions: { ok: { type: 'noul', instructions: 'ok?' } } }),
    });
  const errorType = async (res) => (await res.json()).detail.error_type;

  test('rejects missing and unknown keys with 401', async () => {
    const r1 = await fetch(base + '/v1/systemone', { method: 'POST', body: '{}' });
    assert.equal(r1.status, 401);
    assert.deepEqual(await r1.json(), {
      detail: { error_type: 'authentication_error', message: 'Cannot authenticate with the server. Please check your API key and try again.' },
    }); // word for word what TypeSafe says
    const r2 = await decide('jvp_nope');
    assert.equal(r2.status, 401);
    assert.equal(await errorType(r2), 'authentication_error');
  });

  test('forwards with the owner key and passes the answer through unchanged', async () => {
    seen.length = 0;
    const res = await decide(KEY);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), ANSWER); // byte-for-byte the same protocol
    // key has max_cost 1.0 and spent 100 tokens = 0.25 -> 0.75 left, in a header (body untouched)
    assert.equal(res.headers.get('x-proxy-budget-remaining-usd'), '0.75');
    assert.match(res.headers.get('x-request-id'), /^req_[0-9a-f]{32}$/u);
    assert.equal(res.headers.get('x-typesafe-request-id'), 'req_up123'); // the SDKs read this one
    assert.equal(res.headers.get('server'), null); // other upstream headers stay at the proxy

    const up = seen[0];
    assert.equal(up.url, '/v1/systemone');
    assert.equal(up.headers.authorization, `Bearer ${OWNER_KEY}`);
    assert.equal(up.headers.cookie, undefined);
    assert.deepEqual(JSON.parse(up.body).questions.ok.type, 'noul');
  });

  test('accepts an /api prefix and the x-api-key header', async () => {
    seen.length = 0;
    const res = await fetch(base + '/api/v1/systemone', {
      method: 'POST',
      headers: { 'x-api-key': KEY, 'content-type': 'application/json' },
      body: '{"model":"jev-latest","state":"x","questions":{}}',
    });
    assert.equal(res.status, 200);
    assert.equal(seen[0].url, '/v1/systemone');
  });

  test('passes 529 Overloaded and the retry headers through, so SDK retries work', async () => {
    const res = await decide(KEY, '/v1/busy');
    assert.equal(res.status, 529);
    assert.deepEqual(await res.json(), { detail: 'Overloaded' });
    assert.equal(res.headers.get('retry-after'), '2');
    assert.equal(res.headers.get('retry-after-ms'), '1500');
    assert.equal(res.headers.get('x-typesafe-request-id'), 'req_busy');
    assert.equal(res.headers.get('set-cookie'), null);
    assert.match(res.headers.get('access-control-expose-headers'), /x-typesafe-request-id, retry-after, retry-after-ms/u);
  });

  test('errors made by the proxy carry a TypeSafe-style request id', async () => {
    const res = await decide('jvp_nope');
    assert.match(res.headers.get('x-typesafe-request-id'), /^req_[0-9a-f]{32}$/u);
    assert.equal(res.headers.get('x-typesafe-request-id'), res.headers.get('x-request-id'));
  });

  test('passes upstream errors through unchanged', async () => {
    const res = await decide(KEY, '/v1/boom');
    assert.equal(res.status, 422);
    assert.equal((await res.json()).detail[0].loc[1], 'model');
  });

  test('disabled keys get 403', async () => {
    const res = await decide('jvp_off');
    assert.equal(res.status, 403);
    assert.equal(await errorType(res), 'permission_error');
  });

  test('rate limits per key with Retry-After', async () => {
    assert.equal((await decide(LIMITED)).status, 200);
    assert.equal((await decide(LIMITED)).status, 200);
    const res = await decide(LIMITED);
    assert.equal(res.status, 429);
    assert.equal(await errorType(res), 'rate_limit_error');
    assert.ok(Number(res.headers.get('retry-after')) >= 1);
    // other keys are not affected
    assert.equal((await decide(KEY)).status, 200);
  });

  test('stops a key once its budget is spent', async () => {
    assert.equal((await decide(BROKE)).status, 200); // 0.25 spent
    assert.equal((await decide(BROKE)).status, 200); // 0.50 spent, over 0.30
    const res = await decide(BROKE);
    assert.equal(res.status, 402);
    assert.equal(await errorType(res), 'budget_exceeded_error');
  });

  test('unknown paths are 404, health is open', async () => {
    assert.equal((await decide(KEY, '/nope')).status, 404);
    const health = await (await fetch(base + '/health')).json();
    assert.equal(health.ok, true);
    assert.equal(health.mode, 'live');
  });

  test('admin endpoints need the admin token', async () => {
    assert.equal((await fetch(base + '/admin/usage')).status, 401);
  });

  test('records usage per key and saves it to disk', async () => {
    proxy.usage.flush();
    const saved = JSON.parse(fs.readFileSync(path.join(tmp, 'usage.json'), 'utf8'));
    assert.ok(saved.alice.requests >= 3);
    assert.ok(saved.alice.input_tokens >= 300);
  });
});

describe('mock upstream', () => {
  test('answers all three question types in the TypeSafe shape', () => {
    const { status, body } = mockSystemOne({
      model: 'jev-latest',
      state: 'Customer: I was charged twice and nobody has replied for 3 days. This is urgent!',
      questions: {
        route: { type: 'choice', instructions: 'Where should this go?', criteria: { billing: 'money, charged, refund', bug: 'broken', account: 'login' } },
        urgency: { type: 'score', instructions: 'How urgent is this?', criteria: ['routine', 'today', 'urgent', 'critical'] },
        escalate: { type: 'noul', instructions: 'Is this urgent? Escalate now?' },
      },
    });
    assert.equal(status, 200);
    assert.equal(body.answers.route.choice, 'billing');
    assert.ok(body.answers.urgency.score >= 0 && body.answers.urgency.score <= 3);
    assert.ok(body.answers.escalate.noul > 0.5);
    assert.deepEqual(body.answers.urgency.legend, { 0: 'routine', 1: 'today', 2: 'urgent', 3: 'critical' });
    assert.ok(body.usage.input_tokens > 0);
    assert.ok(body.usage.output_tokens > 0);
    assert.deepEqual(mockModels().body.models.map((m) => m.name), ['jev-latest', 'jev-preview']);
  });

  test('validates like the real API', () => {
    const noModel = mockSystemOne({ state: 'x', questions: { a: { type: 'noul' } } });
    assert.equal(noModel.status, 422); // the real API requires "model"
    assert.deepEqual(noModel.body.detail[0].loc, ['body', 'model']);
    assert.equal(mockSystemOne({ model: 'jev-latest', questions: { a: { type: 'noul' } } }).status, 422);
    const bad = mockSystemOne({ model: 'jev-latest', state: 'x', questions: { a: { type: 'nope' } } });
    assert.deepEqual(bad, { status: 400, body: { detail: { error_type: 'api_usage_error', message: 'Invalid request.' } } });
    assert.deepEqual(mockSystemOne({ model: 'm', state: 'x', questions: { a: { type: 'noul', instructions: 'ok?' } } }).body, {
      detail: { error_type: 'api_usage_error', message: 'Unknown model: m' },
    });
  });

  test('matches every request recorded from the real API', () => {
    const { cases } = JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'systemone-cases.json'), 'utf8'));
    assert.ok(cases.length >= 35);
    const strip = (body) =>
      Array.isArray(body?.detail) ? { detail: body.detail.map(({ type, loc, msg }) => ({ type, loc, msg })) } : body;
    for (const { name, request, expect } of cases) {
      const { status, body } = mockSystemOne(request);
      assert.equal(status, expect.status, name);
      if (status !== 200) {
        assert.deepEqual(strip(body), expect.body, name);
        continue;
      }
      assert.deepEqual(Object.keys(body), expect.top_keys, name);
      assert.deepEqual(Object.keys(body.usage), expect.usage_keys, name);
      const answer = body.answers.q;
      assert.equal(answer.type, expect.answer_type, name);
      assert.deepEqual(Object.keys(answer), expect.answer_keys, name); // same fields, same order
      if (expect.legend) assert.deepEqual(answer.legend, expect.legend, name);
      if (expect.probability_keys) assert.deepEqual(Object.keys(answer.probabilities).sort(), expect.probability_keys, name);
    }
  });

  test('invalid JSON is a 422 json_invalid, like the real API', () => {
    let error;
    try {
      JSON.parse('{bad json');
    } catch (e) {
      error = e;
    }
    const r = invalidJson(error);
    assert.equal(r.status, 422);
    assert.equal(r.body.detail[0].type, 'json_invalid');
    assert.equal(r.body.detail[0].msg, 'JSON decode error');
    assert.deepEqual(r.body.detail[0].loc, ['body', 1]);
  });

  test('proxy in mock mode needs no upstream key', async () => {
    const keysFile = path.join(tmp, 'mock-keys.json');
    fs.writeFileSync(keysFile, JSON.stringify([{ name: 'm', key: 'jvp_m' }]));
    const p = createProxy({ ...readConfig({}), mockUpstream: true, keysFile, usageFile: null, quiet: true, noWatch: true });
    const port = await listen(p.server);
    const res = await fetch(`http://127.0.0.1:${port}/v1/systemone`, {
      method: 'POST',
      headers: { authorization: 'Bearer jvp_m' },
      body: JSON.stringify({ model: 'jev-latest', state: 'I love this bubble tea', questions: { happy: { type: 'noul', instructions: 'Is the customer happy?' } } }),
    });
    const json = await res.json();
    assert.equal(res.status, 200);
    assert.equal(json.model, 'jev-mock');
    assert.equal(res.headers.get('x-proxy-budget-remaining-usd'), null); // the key has no budget
    const models = await (await fetch(`http://127.0.0.1:${port}/v1/models`, { headers: { authorization: 'Bearer jvp_m' } })).json();
    assert.equal(models.models[0].name, 'jev-latest');
    await p.close();
  });
});
