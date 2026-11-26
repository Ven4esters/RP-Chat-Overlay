'use strict';
/**
 * Обработчик POST /api/translate для Vercel. / The POST /api/translate handler for Vercel.
 *
 * RU: серверная функция использует тот же безопасный контракт ошибок, что и
 * локальный адаптер. EN: the serverless function shares the local adapter's
 * safe error contract.
 */

const { translate } = require('../translate');
const { log, errorCode } = require('../logger');
const { publicErrorMessage, responseStatus, safeErrorType } = require('../errors');

function reply(res, payload, status) {
  return res.status(status).json(payload);
}

function authorized(req, token) {
  if (!token) return true;
  const header = String(req.headers.authorization || '');
  const bearer = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
  return bearer === token;
}

function createHandler({
  tokenProvider = () => String(process.env.TOKEN || '').trim(),
  translateFn = translate,
  logger = log,
} = {}) {
  return async function handler(req, res) {
    if (req.method === 'GET') {
      return reply(res, {
        code: 200,
        message: 'DeepLX on Vercel is running. POST text + target_lang here.',
        method: 'Free',
      }, 200);
    }
    if (req.method !== 'POST') {
      res.setHeader('Allow', ['GET', 'POST']);
      return reply(res, { code: 405, message: 'Method not allowed' }, 405);
    }
    if (!authorized(req, tokenProvider())) {
      return reply(res, { code: 401, message: 'Unauthorized' }, 401);
    }

    let body = req.body;
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body || '{}');
      } catch (error) {
        logger('warn', 'deepl.invalid_request', {
          status: 400,
          error_type: safeErrorType(error),
        });
        return reply(res, { code: 400, message: publicErrorMessage(400) }, 400);
      }
    }
    body = body && typeof body === 'object' ? body : {};

    const text = body.text !== undefined ? body.text : (body.texts !== undefined ? body.texts : '');
    const target = body.target_lang || body.target || 'en';
    const source = body.source_lang || body.source || 'auto';
    const started = Date.now();

    try {
      const items = Array.isArray(text) ? text : [text];
      const result = await translateFn(items, source, target, String(body.pro_token || '').trim());
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
      const status = responseStatus(error);
      logger('warn', 'deepl.translation_failed', {
        status,
        error_type: safeErrorType(error),
        error_code: errorCode(error),
        retryable: status === 429 || status === 503,
      });
      return reply(res, { code: status, message: publicErrorMessage(status) }, status);
    }
  };
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
