'use strict';

const SECRET_FIELD = /token|password|passwd|secret|authorization|credential|signature|api[_-]?key|private[_-]?key|cookie/i;

function log(level, event, fields = {}) {
  const safeFields = Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, SECRET_FIELD.test(key) ? '[REDACTED]' : value]),
  );
  const record = {
    timestamp: new Date().toISOString(),
    level,
    event,
    ...safeFields,
  };
  const output = `${JSON.stringify(record)}\n`;
  (level === 'error' || level === 'warn' ? process.stderr : process.stdout).write(output);
}

function errorCode(error) {
  const value = error && error.code;
  if (typeof value === 'number' && Number.isInteger(value)) return value;
  if (typeof value === 'string' && /^[A-Z0-9_-]{1,32}$/.test(value)) return value;
  return undefined;
}

module.exports = { log, errorCode };
