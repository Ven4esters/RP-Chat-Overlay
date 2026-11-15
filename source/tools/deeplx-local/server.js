'use strict';
/**
 * Локальный сервис DeepL, совместимый с DLX. / A local DeepL service, DLX-compatible.
 *
 * RU: зачем нужен. dlx.exe — готовый бинарник: его надо скачивать, и он иногда
 * не поднимается. Этот сервер делает ту же работу на Node.js: те же адреса
 * (/translate, /v1/translate, /v2/translate), тот же формат ответа, тот же
 * необязательный токен. Программа умеет работать и с ним — достаточно указать
 * адрес в настройках.
 * EN: why it exists. dlx.exe is a prebuilt binary that has to be downloaded and
 * sometimes refuses to start. This server does the same job on Node.js: same
 * routes (/translate, /v1/translate, /v2/translate), same answer shape, same
 * optional token. The program can talk to it as well — just point it at the URL.
 *
 * Порт по умолчанию 1188 — тот же, что у DLX. / Default port 1188, same as DLX.
 */

const express = require('express');
const { translate, TranslationError } = require('./translate');

const PORT = Number(process.env.PORT || 1188);
const HOST = process.env.HOST || '0.0.0.0';
const TOKEN = String(process.env.TOKEN || '').trim();

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '2mb' }));

function authorized(req) {
  if (!TOKEN) return true;
  const header = String(req.headers.authorization || '');
  const bearer = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
  return bearer === TOKEN;
}

function send(res, payload, status) {
  res.status(status).json(payload);
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
    const result = await translate(items, source, target, String(body.pro_token || '').trim());
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
    const status = error instanceof TranslationError ? error.code : 503;
    // RU: причину видно в консоли сервера, а не только в ответе
    // EN: the reason is visible in the server console, not only in the answer
    console.warn(`DeepLX-local: ${status} — ${error.message}`);
    return send(res, { code: status, message: error.message }, status);
  }
}

// RU: GET / — проверка живости, её же дёргает программа
// EN: GET / is the liveness check the program calls as well
app.get('/', (req, res) => send(res, {
  code: 200, message: 'DeepLX local is running', method: 'Free',
}, 200));

['/translate', '/v1/translate', '/v2/translate'].forEach((route) => {
  app.post(route, handle);
});

app.use((req, res) => send(res, { code: 404, message: 'Not found' }, 404));

const server = app.listen(PORT, HOST, () => {
  console.log(`DeepLX-local слушает http://${HOST}:${PORT}${TOKEN ? ' (с токеном, / with a token)' : ''}`);
});

['SIGINT', 'SIGTERM'].forEach((signal) => {
  process.on(signal, () => server.close(() => process.exit(0)));
});
