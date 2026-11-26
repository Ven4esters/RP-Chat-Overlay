'use strict';
/**
 * Перевод через тот же путь, которым ходит приложение DeepL для iOS.
 * Translation over the very path the DeepL iOS app uses.
 *
 * RU: старый способ (POST https://www2.deepl.com/jsonrpc, метод
 * LMT_handle_texts) больше не работает: DeepL отвечает на него текстом
 * «You're using an older version of DeepL» вместо перевода. Актуальный путь —
 * oneshot-эндпоинт https://oneshot-free.www.deepl.com/v1/translate.
 * EN: the old way (POST https://www2.deepl.com/jsonrpc, LMT_handle_texts) no
 * longer works: DeepL answers it with "You're using an older version of DeepL"
 * instead of a translation. The current path is the oneshot endpoint
 * https://oneshot-free.www.deepl.com/v1/translate.
 *
 * RU: версия клиента в User-Agent и app_information обязана совпадать с той,
 * что DeepL выпустил в App Store: устаревшая получает 429 на каждый запрос.
 * Поэтому версия берётся из открытого App Store lookup и кэшируется.
 * EN: the client version in the User-Agent and app_information must match what
 * DeepL currently ships in the App Store: a stale one is answered with 429 on
 * every request. So the version is read from Apple's open lookup and cached.
 */

const axios = require('axios').default;
const crypto = require('crypto');
const { log, errorCode } = require('./logger');

const FREE_ENDPOINT = 'https://oneshot-free.www.deepl.com/v1/translate';
const PRO_ENDPOINT = 'https://oneshot-pro.www.deepl.com/v1/translate';

// Совпадает с DeepLX: те же значения держат TLS, UA и app_information согласованными.
// Same as DeepLX: these values keep the TLS profile, UA and app_information coherent.
const FALLBACK_VERSION = '26.58';
const APP_BUILD = '5443737';
const OS_VERSION = '26.0';
const CFNETWORK = '3826.600.41';
const DARWIN = '25.0.0';
const MAX_CHARS = 1500;               // лимит анонимного oneshot / anonymous cap
const LOOKUP_URL = 'https://itunes.apple.com/lookup?id=1552407475&country=us';
const LOOKUP_TTL = 24 * 60 * 60 * 1000;
const LOOKUP_BACKOFF = 15 * 60 * 1000;

// Один идентификатор установки на процесс: ротация на каждый запрос — лишний
// признак бота / one install id per process: per-request rotation looks like a bot
const instanceId = crypto.randomUUID();
const sessionId = crypto.randomUUID();

let cachedVersion = '';
let cachedAt = 0;
let lookupTriedAt = 0;

function validVersion(value) {
  return typeof value === 'string' && /^\d+\.\d+$/.test(value.trim());
}

async function appVersion() {
  const now = Date.now();
  if (validVersion(cachedVersion) && now - cachedAt < LOOKUP_TTL) return cachedVersion;
  if (lookupTriedAt && now - lookupTriedAt < LOOKUP_BACKOFF) {
    return validVersion(cachedVersion) ? cachedVersion : FALLBACK_VERSION;
  }
  lookupTriedAt = now;
  try {
    const answer = await axios.get(LOOKUP_URL, { timeout: 3000 });
    const version = answer.data?.results?.[0]?.version;
    if (!validVersion(version)) throw new Error(`implausible version ${version}`);
    cachedVersion = version.trim();
    cachedAt = now;
    return cachedVersion;
  } catch (error) {
    const fallback = validVersion(cachedVersion) ? cachedVersion : FALLBACK_VERSION;
    log('warn', 'deepl.version_lookup_failed', {
      fallback_version: fallback,
      error_code: errorCode(error),
    });
    return fallback;
  }
}

// RU: oneshot понимает только нижний регистр; «IT» молча даёт английский.
// EN: oneshot only understands lowercase; "IT" silently yields English.
function normLang(code) {
  const value = String(code || '').trim().toLowerCase();
  if (!value || value === 'auto' || value === 'a') return '';
  const table = { 'zh-cn': 'zh', 'zh-tw': 'zh-hant', 'es-mx': 'es-419' };
  return table[value] || value;
}

function utf16Length(text) {
  return String(text || '').length;
}

function headers(token) {
  const ua = `DeepL/${cachedVersion || FALLBACK_VERSION} CFNetwork/${CFNETWORK} Darwin/${DARWIN}`;
  return {
    'Content-Type': 'application/json',
    Authorization: token ? `Bearer ${token}` : 'None',
    'User-Agent': ua,
    'x-app-os-version': OS_VERSION,
    'x-app-instance-id': instanceId,
    'x-app-session-id': sessionId,
    Accept: '*/*',
  };
}

class TranslationError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

/**
 * Перевести один или несколько текстов. / Translate one or several texts.
 * Порядок сохраняется, пустые строки остаются пустыми.
 * Order is kept, blank strings stay blank.
 */
async function translate(texts, sourceLang = 'auto', targetLang = 'en', token = '') {
  const list = Array.isArray(texts) ? texts.map((item) => String(item == null ? '' : item)) : [String(texts == null ? '' : texts)];
  const target = normLang(targetLang);
  const source = normLang(sourceLang);
  if (!target) throw new TranslationError(400, 'target_lang is required');

  const total = list.reduce((sum, item) => sum + utf16Length(item), 0);
  if (total > MAX_CHARS) {
    throw new TranslationError(413, `text exceeds maximum length: ${total} characters (anonymous oneshot limit is ${MAX_CHARS})`);
  }

  const wanted = [];
  const positions = [];
  list.forEach((item, index) => {
    if (item.trim()) {
      wanted.push(item);
      positions.push(index);
    }
  });
  if (!wanted.length) return list.slice();

  const version = await appVersion();
  const body = {
    text: wanted,
    target_lang: target,
    usage_type: 'translate',
    app_information: {
      os: 'iOS',
      os_version: OS_VERSION,
      app_version: version,
      app_build: APP_BUILD,
      instance_id: instanceId,
    },
  };
  if (source) body.source_lang = source;

  let answer;
  try {
    answer = await axios.post(token ? PRO_ENDPOINT : FREE_ENDPOINT, body, {
      headers: headers(token), timeout: 20000, decompress: true,
    });
  } catch (error) {
    const status = (error.response && error.response.status) || 0;
    const payload = error.response && error.response.data;
    if (status === 429) {
      throw new TranslationError(429, 'too many requests, your IP has been blocked by DeepL temporarily, please don\'t request it frequently in a short time');
    }
    if (status === 403) {
      throw new TranslationError(403, (payload && (payload.title || payload.message)) || 'request forbidden by DeepL (auth failed, outdated client, or blocked)');
    }
    throw new TranslationError(503, (payload && payload.message) || error.message || `request failed with status code: ${status}`);
  }

  const found = answer.data && answer.data.translations;
  if (!Array.isArray(found) || found.length !== wanted.length) {
    throw new TranslationError(503, 'DeepL вернул неожиданный ответ — / unexpected answer from DeepL');
  }
  const result = list.slice();
  positions.forEach((position, index) => {
    const item = found[index];
    result[position] = String((item && item.text) || '');
  });
  return result;
}

module.exports = { translate, TranslationError, MAX_CHARS };
