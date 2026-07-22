/**
 * Config for i18n (non-Vietnamese) TTS pages.
 * - Local: models from public/tts-model/{lang}/
 * - Production: models from /api/model/piper/{lang}/
 */

export function getModelBaseUrl(lang) {
  if (import.meta.env.PROD) {
    return `/api/model/piper/${lang}/`;
  }
  return `${import.meta.env.BASE_URL}tts-model/${lang}/`;
}

/**
 * API URL to list models for a language.
 * Local: Vite middleware /api/piper/:lang/models
 * Production: Cloudflare /api/piper/:lang/models
 */
export function getModelsListUrl(lang) {
  return `/api/piper/${lang}/models`;
}

/** Default model names per language when no API is used (e.g. local fallback). */
export const DEFAULT_LANG_MODELS = {
  en: [],
  id: [],
};

/** Default model name to auto-load per language. If not set, first available model is used. */
export const DEFAULT_MODEL = {
  vi: 'Ngọc Huyền (mới)',   // null = use first available from /api/models
  en: 'Libritts_r',
  id: 'Indo_goreng',   // null = use first available
};

/** Default ASR model name when none selected. Local: public/asr-model/{name}/. Production: R2 asr/{name}/. */
export const DEFAULT_ASR_MODEL = 'nghi-stt';

/** Fallback ASR model list when /api/asr/models fails or returns empty (e.g. production before R2 list works). */
export const ASR_MODELS_FALLBACK = ['nghi-stt-v2','sherpa-onnx-zipformer-vi-int8-2025-10-16'];

/** localStorage key for user-selected ASR model. */
export const ASR_MODEL_STORAGE_KEY = 'asr-selected-model';

/** API URL to list available ASR models. Local: Vite middleware. Production: Cloudflare /api/asr/models */
export function getASRModelsListUrl() {
  return '/api/asr/models';
}

/** Shared ASR scripts (same for all models). Served from public/code/asr-wasm/. */
export const ASR_CODE_BASE = '/code/asr-wasm/';

/** Model-specific ASR filenames (.wasm, .data, main .js); each model has its own. */
const ASR_MODEL_FILES = ['sherpa-onnx-wasm-main-vad-asr.wasm', 'sherpa-onnx-wasm-main-vad-asr.data', 'sherpa-onnx-wasm-main-vad-asr.js'];

/**
 * ASR WASM assets (sherpa-onnx VAD+ASR).
 * - Shared scripts (sherpa-onnx-asr.js, sherpa-onnx-vad.js, app-vad-asr.js): use ASR_CODE_BASE (/code/asr-wasm/).
 * - Model-specific (.wasm, .data, sherpa-onnx-wasm-main-vad-asr.js): local from asr-model/{model}/, production from R2 asr/{model}/ via /api/model/asr/{model}/.
 */
export function getASRAssetUrl(filename, model = DEFAULT_ASR_MODEL) {
  if (ASR_MODEL_FILES.includes(filename)) {
    if (import.meta.env.PROD) {
      return `/api/model/asr/${model}/${filename}`;
    }
    return `${import.meta.env.BASE_URL || '/'}asr-model/${model}/${filename}`;
  }
  return `${import.meta.env.BASE_URL || '/'}asr-wasm/${filename}`;
}
