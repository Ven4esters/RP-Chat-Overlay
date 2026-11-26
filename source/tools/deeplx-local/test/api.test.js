'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createHandler } = require('../api/translate');
const healthHandler = require('../api');
const vercelConfig = require('../vercel.json');
const { TranslationError } = require('../translate');

function responseRecorder() {
  return {
    statusCode: null,
    headers: {},
    payload: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    setHeader(name, value) {
      this.headers[name] = value;
    },
    json(payload) {
      this.payload = payload;
      return this;
    },
  };
}

test('Vercel health function and rewrite aliases are configured', () => {
  const res = responseRecorder();
  healthHandler({ method: 'GET' }, res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.payload.code, 200);
  assert.equal(res.payload.runtime, process.version);
  assert.deepEqual(vercelConfig.rewrites, [
    { source: '/', destination: '/api' },
    { source: '/translate', destination: '/api/translate' },
    { source: '/v1/translate', destination: '/api/translate' },
    { source: '/v2/translate', destination: '/api/translate' },
  ]);
  assert.equal(vercelConfig.functions['api/translate.js'].maxDuration, 30);
});

test('serverless adapter returns the same safe translation error contract', async () => {
  const privateText = 'private_serverless_chat_phrase';
  const events = [];
  const handler = createHandler({
    tokenProvider: () => '',
    translateFn: async () => {
      throw new TranslationError(503, `upstream echoed ${privateText}`);
    },
    logger: (level, event, fields) => events.push({ level, event, fields }),
  });
  const res = responseRecorder();

  await handler({ method: 'POST', headers: {}, body: { text: privateText } }, res);

  assert.equal(res.statusCode, 503);
  assert.deepEqual(res.payload, {
    code: 503,
    message: 'Translation service is temporarily unavailable',
  });
  assert.equal(events[0].event, 'deepl.translation_failed');
  assert.ok(!JSON.stringify(res.payload).includes(privateText));
  assert.ok(!JSON.stringify(events).includes(privateText));
});

test('serverless adapter rejects malformed JSON without echoing its body', async () => {
  const privateText = 'private_invalid_request_text';
  const events = [];
  const handler = createHandler({
    tokenProvider: () => '',
    logger: (level, event, fields) => events.push({ level, event, fields }),
  });
  const res = responseRecorder();

  await handler({
    method: 'POST',
    headers: {},
    body: `{invalid ${privateText}`,
  }, res);

  assert.equal(res.statusCode, 400);
  assert.deepEqual(res.payload, { code: 400, message: 'Invalid translation request' });
  assert.ok(!JSON.stringify(events).includes(privateText));
});

test('serverless adapter reports supported methods and a stable health response', async () => {
  const handler = createHandler({ tokenProvider: () => '' });
  const health = responseRecorder();
  await handler({ method: 'GET', headers: {} }, health);
  assert.equal(health.statusCode, 200);
  assert.match(health.payload.message, /is running/);

  const unsupported = responseRecorder();
  await handler({ method: 'DELETE', headers: {} }, unsupported);
  assert.equal(unsupported.statusCode, 405);
  assert.deepEqual(unsupported.headers.Allow, ['GET', 'POST']);
  assert.deepEqual(unsupported.payload, { code: 405, message: 'Method not allowed' });
});
