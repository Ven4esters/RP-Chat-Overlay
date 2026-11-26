'use strict';
/**
 * Локальный сервис DeepL, совместимый с DLX. / A local DeepL service, DLX-compatible.
 *
 * RU: сервер на Node.js предоставляет те же маршруты DLX и необязательную
 * авторизацию Bearer-токеном. EN: a Node.js server exposes the DLX routes and
 * optional Bearer-token authentication.
 */

const express = require('express');
const { translate } = require('./translate');
const { log, errorCode } = require('./logger');
const { publicErrorMessage, responseStatus, safeErrorType } = require('./errors');

const PORT = Number(process.env.PORT || 1188);
const HOST = process.env.HOST || '127.0.0.1';
const TOKEN = String(process.env.TOKEN || '').trim();
const ROUTES = ['/translate', '/v1/translate', '/v2/translate'];

function send(res, payload, status) {
  res.status(status).json(payload);
}

function createApp({ token = TOKEN, translateFn = translate, logger = log } = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '2mb' }));

  function authorized(req) {
    if (!token) return true;
    const header = String(req.headers.authorization || '');
    const bearer = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
    return bearer === token;
  }

  async function handle(req, res) {
    if (!authorized(req)) return send(res, { code: 401, message: 'Unauthorized' }, 401);
    const body = req.body || {};
    const text = body.text !== undefined ? body.text : (body.texts !== undefined ? body.texts : '');
    const target = body.target_lang || body.target || 'en';
    const source = body.source_lang || body.source || 'auto';
    const started = Date.now();
    try {
      const items = Array.isArray(text) ? text : [text];
      const result = await translateFn(items, source, target, String(body.pro_token || '').trim());
      return send(res, {
        alternatives: [],
        code: 200,
        data: Array.isArray(text) ? result : result[0],
        id: Date.now() * 1000 + Math.floor(Math.random() * 1000),
        method: 'Free',
        source_lang: source,
        target_lang: target,
        elapsed: (Date.now() - started) / 1000,
      }, 200);
    } catch (error) {
      const status = responseStatus(error);
      logger('warn', 'deepl.translation_failed', {
        status,
        error_type: safeErrorType(error),
        error_code: errorCode(error),
        retryable: status === 429 || status === 503,
      });
      return send(res, { code: status, message: publicErrorMessage(status) }, status);
    }
  }

  // RU: GET / — проверка доступности, её же вызывает приложение.
  // EN: GET / is the health check used by the application.
  app.get('/', (req, res) => send(res, {
    code: 200,
    message: 'DeepLX local is running',
    method: 'Free',
  }, 200));

  ROUTES.forEach((route) => app.post(route, handle));

  app.use((error, req, res, _next) => {
    const status = error && error.status === 413 ? 413 : 400;
    logger('warn', 'deepl.invalid_request', {
      status,
      error_type: safeErrorType(error),
    });
    return send(res, { code: status, message: publicErrorMessage(status) }, status);
  });

  app.use((req, res) => send(res, { code: 404, message: 'Not found' }, 404));
  return app;
}

function startServer({ host = HOST, port = PORT } = {}) {
  const server = createApp().listen(port, host, () => {
    log('info', 'deepl.server_started', {
      host,
      port: server.address().port,
      authentication_required: Boolean(TOKEN),
    });
  });
  return server;
}

if (require.main === module) {
  const server = startServer();
  ['SIGINT', 'SIGTERM'].forEach((signal) => {
    process.on(signal, () => server.close(() => process.exit(0)));
  });
}

module.exports = { createApp, startServer };
