'use strict';
/**
 * Обработчик POST /api/translate для Vercel. / The POST /api/translate handler for Vercel.
 *
 * RU: тот же перевод, что и в локальном server.js, но в виде бессерверной
 * функции: Vercel сам поднимает её на каждый запрос, слушающий порт не нужен.
 * EN: the same translation as the local server.js, shaped as a serverless
 * function: Vercel runs it per request, no listening port involved.
 */

const { translate, TranslationError } = require('../translate');

function reply(res, payload, status) {
  res.status(status).json(payload);
}

function authorized(req) {
  const token = String(process.env.TOKEN || '').trim();
  if (!token) return true;
  const header = String(req.headers.authorization || '');
  const bearer = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
  return bearer === token;
}

module.exports = async function handler(req, res) {
  // RU: GET отвечает подсказкой — адрес удобно проверять прямо в браузере
  // EN: GET answers with a hint, so the address can be checked in a browser
  if (req.method === 'GET') {
    return reply(res, {
      code: 200,
      message: 'DeepLX on Vercel is running. POST text + target_lang here.',
      method: 'Free',
    }, 200);
  }
  if (req.method !== 'POST') {
    res.setHeader('Allow', ['GET', 'POST']);
    return reply(res, { code: 405, message: `method ${req.method} is not allowed` }, 405);
  }
  if (!authorized(req)) {
    return reply(res, { code: 401, message: 'Unauthorized' }, 401);
  }

  // RU: Vercel разбирает JSON сам, но строку на всякий случай тоже понимаем
  // EN: Vercel parses JSON itself, yet a raw string is understood as well
  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body || '{}');
    } catch (error) {
      return reply(res, { code: 400, message: 'body is not valid JSON' }, 400);
    }
  }
  body = body || {};

  const text = body.text !== undefined ? body.text : (body.texts !== undefined ? body.texts : '');
  const target = body.target_lang || body.target || 'en';
  const source = body.source_lang || body.source || 'auto';
  const started = Date.now();

  try {
    const items = Array.isArray(text) ? text : [text];
    const result = await translate(items, source, target, String(body.pro_token || '').trim());
    return reply(res, {
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
    // RU: причина остаётся в логах функции — Vercel → Deployments → Logs
    // EN: the reason stays in the function logs — Vercel → Deployments → Logs
    console.warn(`DeepLX-vercel: ${status} — ${error.message}`);
    return reply(res, { code: status, message: error.message }, status);
  }
};
