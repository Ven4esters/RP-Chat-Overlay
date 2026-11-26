'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createApp } = require('../server');
const { TranslationError } = require('../translate');

async function listen(t, options = {}) {
  const server = createApp(options).listen(0, '127.0.0.1');
  await new Promise((resolve, reject) => {
    server.once('listening', resolve);
    server.once('error', reject);
  });
  t.after(() => {
    server.closeAllConnections?.();
    return new Promise((resolve) => server.close(resolve));
  });
  return `http://127.0.0.1:${server.address().port}`;
}

test('health endpoint returns a stable service status', async (t) => {
  const baseUrl = await listen(t);
  const response = await fetch(`${baseUrl}/`);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    code: 200,
    message: 'DeepLX local is running',
    method: 'Free',
  });
});

test('all DLX route aliases translate with the supplied token', async (t) => {
  const calls = [];
  const baseUrl = await listen(t, {
    token: 'test-token',
    translateFn: async (...args) => {
      calls.push(args);
      return ['translated'];
    },
    logger: () => {},
  });

  for (const route of ['/translate', '/v1/translate', '/v2/translate']) {
    const response = await fetch(`${baseUrl}${route}`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer test-token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: 'hello', source_lang: 'ru', target_lang: 'it' }),
    });
    const payload = await response.json();

    assert.equal(response.status, 200);
    assert.equal(payload.data, 'translated');
    assert.equal(payload.source_lang, 'ru');
    assert.equal(payload.target_lang, 'it');
  }

  assert.deepEqual(calls, [
    [['hello'], 'ru', 'it', ''],
    [['hello'], 'ru', 'it', ''],
    [['hello'], 'ru', 'it', ''],
  ]);
});

test('invalid bearer tokens are rejected before translation', async (t) => {
  let translationCalls = 0;
  const baseUrl = await listen(t, {
    token: 'expected-token',
    translateFn: async () => {
      translationCalls += 1;
      return ['should not run'];
    },
    logger: () => {},
  });

  const response = await fetch(`${baseUrl}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: 'private request text' }),
  });

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { code: 401, message: 'Unauthorized' });
  assert.equal(translationCalls, 0);
});

test('translation failures return safe messages and never log request text', async (t) => {
  const privateText = 'private_roleplay_phrase_for_test';
  const events = [];
  const baseUrl = await listen(t, {
    translateFn: async () => {
      throw new TranslationError(429, `upstream echoed ${privateText}`);
    },
    logger: (level, event, fields) => events.push({ level, event, fields }),
  });

  const response = await fetch(`${baseUrl}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: privateText }),
  });
  const payload = await response.json();
  const diagnostic = JSON.stringify(events);

  assert.equal(response.status, 429);
  assert.deepEqual(payload, {
    code: 429,
    message: 'Translation service rate limit reached',
  });
  assert.equal(events[0].fields.retryable, true);
  assert.equal(events[0].fields.error_code, 429);
  assert.ok(!JSON.stringify(payload).includes(privateText));
  assert.ok(!diagnostic.includes(privateText));
});

test('malformed JSON gets a safe client error response', async (t) => {
  const events = [];
  const baseUrl = await listen(t, {
    logger: (level, event, fields) => events.push({ level, event, fields }),
  });
  const response = await fetch(`${baseUrl}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{invalid json}',
  });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    code: 400,
    message: 'Invalid translation request',
  });
  assert.equal(events[0].event, 'deepl.invalid_request');
});

test('oversized JSON receives a safe 413 response without logging the body', async (t) => {
  const events = [];
  const baseUrl = await listen(t, {
    logger: (level, event, fields) => events.push({ level, event, fields }),
  });
  const response = await fetch(`${baseUrl}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: 'x'.repeat(2 * 1024 * 1024) }),
  });

  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), {
    code: 413,
    message: 'Text exceeds the service limit',
  });
  assert.equal(events[0].event, 'deepl.invalid_request');
  assert.equal(events[0].fields.status, 413);
});
