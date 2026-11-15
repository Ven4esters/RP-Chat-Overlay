'use strict';
/**
 * Проверка живости на Vercel: GET /api/ и GET /api/translate.
 * The liveness check on Vercel: GET /api/ and GET /api/translate.
 *
 * RU: программа сначала спрашивает этот адрес, и только потом переводит, —
 * без ответа здесь она сочтёт сервис молчащим.
 * EN: the program asks this address before translating; without an answer it
 * treats the service as silent.
 */

module.exports = function handler(req, res) {
  res.status(200).json({
    code: 200,
    message: 'DeepLX on Vercel is running',
    method: 'Free',
    runtime: process.version,
  });
};
