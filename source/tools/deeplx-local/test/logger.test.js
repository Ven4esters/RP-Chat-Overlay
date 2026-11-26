'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { log } = require('../logger');

test('structured logs redact credential fields and keep diagnostic metadata', () => {
  const output = [];
  const originalWrite = process.stdout.write;
  process.stdout.write = (chunk) => {
    output.push(String(chunk));
    return true;
  };

  try {
    log('info', 'deepl.server_started', {
      host: '127.0.0.1',
      port: 1188,
      token: 'private-test-token',
      authorization: 'Bearer private-test-token',
      client_credential: 'private-client-credential',
      apiKey: 'private-api-key',
    });
  } finally {
    process.stdout.write = originalWrite;
  }

  assert.equal(output.length, 1);
  const record = JSON.parse(output[0]);
  assert.equal(record.event, 'deepl.server_started');
  assert.equal(record.host, '127.0.0.1');
  assert.equal(record.port, 1188);
  assert.equal(record.token, '[REDACTED]');
  assert.equal(record.authorization, '[REDACTED]');
  assert.equal(record.client_credential, '[REDACTED]');
  assert.equal(record.apiKey, '[REDACTED]');
  assert.ok(!output[0].includes('private-test-token'));
  assert.ok(!output[0].includes('private-client-credential'));
  assert.ok(!output[0].includes('private-api-key'));
  assert.ok(Number.isFinite(Date.parse(record.timestamp)));
});
