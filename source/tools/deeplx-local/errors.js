'use strict';

const { TranslationError } = require('./translate');

const SAFE_MESSAGES = Object.freeze({
  400: 'Invalid translation request',
  403: 'Translation service refused the request',
  413: 'Text exceeds the service limit',
  429: 'Translation service rate limit reached',
  503: 'Translation service is temporarily unavailable',
});

function responseStatus(error) {
  const status = error instanceof TranslationError ? error.code : 503;
  return Object.hasOwn(SAFE_MESSAGES, status) ? status : 503;
}

function publicErrorMessage(status) {
  return SAFE_MESSAGES[status] || SAFE_MESSAGES[503];
}

function safeErrorType(error) {
  const name = error && error.constructor && error.constructor.name;
  return typeof name === 'string' && /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(name) ? name : 'Error';
}

module.exports = { publicErrorMessage, responseStatus, safeErrorType };
