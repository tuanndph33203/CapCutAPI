<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { MicIcon, SquareIcon, Trash2Icon, UploadIcon, DownloadIcon } from 'lucide-vue-next';
import { getASRAssetUrl, ASR_CODE_BASE, getASRModelsListUrl, DEFAULT_ASR_MODEL, ASR_MODELS_FALLBACK, ASR_MODEL_STORAGE_KEY } from '../config.js';

/** Shared scripts (same for all models) from code/asr-wasm. Model-specific main .js loaded separately. */
const sharedScriptUrls = [
  `${ASR_CODE_BASE}sherpa-onnx-asr.js`,
  `${ASR_CODE_BASE}sherpa-onnx-vad.js`,
  `${ASR_CODE_BASE}app-vad-asr.js`,
];

const loadedScripts = ref([]);
const asrMode = ref('mic');
const asrModels = ref([]);
/** Current model id (from storage or default). Used to load WASM; changing it triggers reload. */
const selectedModel = ref(DEFAULT_ASR_MODEL);
const selectedFile = ref(null);
const uploadStatus = ref('');
const isProcessing = ref(false);
const asrReady = ref(false);

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.onload = () => {
      loadedScripts.value.push(script);
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });
}

function onFileChange(e) {
  const f = e.target.files?.[0];
  selectedFile.value = f || null;
  uploadStatus.value = '';
}

async function processUpload() {
  if (!selectedFile.value || isProcessing.value) return;
  const startBtn = document.getElementById('startBtn');
  if (startBtn && startBtn.disabled) {
    uploadStatus.value = 'Stop microphone first.';
    return;
  }
  const processUploadedAudio = window.processUploadedAudio;
  if (typeof processUploadedAudio !== 'function') return;
  uploadStatus.value = 'Processing...';
  isProcessing.value = true;
  window.asrUploadInProgress = true;
  try {
    const buf = await selectedFile.value.arrayBuffer();
    await processUploadedAudio(buf);
    uploadStatus.value = 'Done';
  } catch (err) {
    console.error(err);
    uploadStatus.value = err?.message || 'Unsupported audio format or error';
  } finally {
    isProcessing.value = false;
    window.asrUploadInProgress = false;
  }
}

function downloadSubtitle(ext) {
  const getSRT = window.getASRSubtitleSRT;
  if (typeof getSRT !== 'function') return;
  const content = getSRT();
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = ext === 'srt' ? 'subtitles.srt' : 'subtitles.txt';
  a.click();
  URL.revokeObjectURL(a.href);
}

function onAsrReady() {
  asrReady.value = true;
}

function setMode(mode) {
  asrMode.value = mode;
  if (typeof window !== 'undefined') window.asrCurrentMode = mode;
}

function onAsrModelChange(event) {
  const value = event?.target?.value;
  if (!value || value === selectedModel.value) return;
  try {
    localStorage.setItem(ASR_MODEL_STORAGE_KEY, value);
  } catch (_) {}
  window.location.reload();
}

function clearUpload() {
  if (typeof window !== 'undefined') window.asrCurrentMode = 'upload';
  document.getElementById('clearBtn')?.click();
}

onMounted(async () => {
  if (typeof window !== 'undefined') window.asrCurrentMode = 'mic';
  try {
    const saved = localStorage.getItem(ASR_MODEL_STORAGE_KEY);
    if (saved) selectedModel.value = saved;
  } catch (_) {}

  try {
    const res = await fetch(getASRModelsListUrl());
    const data = await res.json().catch(() => ({}));
    const list = Array.isArray(data?.models) ? data.models : [];
    asrModels.value = list.length > 0 ? list : ASR_MODELS_FALLBACK;
    if (asrModels.value.length && !asrModels.value.includes(selectedModel.value)) {
      selectedModel.value = asrModels.value[0];
      try {
        localStorage.setItem(ASR_MODEL_STORAGE_KEY, selectedModel.value);
      } catch (_) {}
    }
  } catch (_) {
    asrModels.value = ASR_MODELS_FALLBACK;
  }

  window.addEventListener('asr-ready', onAsrReady);
  const model = selectedModel.value;
  const getUrl = (filename) => getASRAssetUrl(filename, model);
  try {
    await loadScript(sharedScriptUrls[0]);
    await loadScript(sharedScriptUrls[1]);
    await loadScript(sharedScriptUrls[2]);
    if (window.Module) {
      window.Module.locateFile = (path) => getUrl(path);
    }
    const wasmUrl = getUrl('sherpa-onnx-wasm-main-vad-asr.wasm');
    const r = await fetch(wasmUrl);
    const contentType = r.headers.get('Content-Type') || '';
    const isHtml = contentType.includes('text/html') || r.status === 404;
    if (isHtml) {
      const statusEl = document.getElementById('status');
      if (statusEl) {
        statusEl.textContent = `ASR model "${model}" not found. Add .wasm and .data to public/asr-model/${model}/. Build with build-wasm-simd-vad-asr.sh (sherpa-onnx) and copy from install/bin/wasm/vad-asr/.`;
      }
      return;
    }
    await loadScript(getUrl('sherpa-onnx-wasm-main-vad-asr.js'));
    if (window.asrReady) asrReady.value = true;
  } catch (e) {
    console.error('ASR WASM load error:', e);
    const statusEl = document.getElementById('status');
    if (statusEl) statusEl.textContent = 'Failed to load ASR. Ensure shared scripts are in public/code/asr-wasm/ and model .wasm/.data in public/asr-model/<model>/ (or R2 asr/<model>/).';
  }
});

onUnmounted(() => {
  window.removeEventListener('asr-ready', onAsrReady);
  loadedScripts.value.forEach((script) => {
    if (script.parentNode) script.parentNode.removeChild(script);
  });
  loadedScripts.value = [];
});
</script>

<template>
  <div>
    <div class="bg-white/70 dark:bg-gray-900/70 backdrop-blur-xl rounded-2xl shadow-xl border border-white/20 dark:border-gray-700/50 overflow-hidden">
      <div class="p-6 pb-0 space-y-6">
        <div class="flex flex-wrap items-center gap-3">
          <span id="status" class="text-sm font-medium text-gray-700 dark:text-gray-300">
            Loading...
          </span>
          <label v-if="asrModels.length" class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <span>Model:</span>
            <select
              :value="selectedModel"
              class="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              @change="onAsrModelChange"
            >
              <option v-for="m in asrModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <span class="text-xs text-gray-500 dark:text-gray-500">(page reloads when changed)</span>
          </label>
        </div>

        <div id="singleAudioContent" class="tab-content loading space-y-4">
          <div class="flex border-b border-gray-200 dark:border-gray-700">
            <button
              type="button"
              :class="asrMode === 'mic' ? 'border-b-2 border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400 font-medium' : 'text-gray-600 dark:text-gray-400'"
              class="px-4 py-2 text-sm transition-colors"
              @click="setMode('mic')"
            >
              Mic
            </button>
            <button
              type="button"
              :class="asrMode === 'upload' ? 'border-b-2 border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400 font-medium' : 'text-gray-600 dark:text-gray-400'"
              class="px-4 py-2 text-sm transition-colors"
              @click="setMode('upload')"
            >
              Upload
            </button>
          </div>

          <div v-show="asrMode === 'mic'" class="flex flex-col sm:flex-row gap-3">
            <button
              id="startBtn"
              disabled
              class="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-semibold text-white bg-blue-800 shadow-lg transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:scale-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <MicIcon class="w-5 h-5" />
              Start
            </button>
            <button
              id="stopBtn"
              disabled
              class="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-orange-500 to-orange-700 shadow-lg transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:scale-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <SquareIcon class="w-5 h-5" />
              Stop
            </button>
            <button
              id="clearBtn"
              class="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-medium bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <Trash2Icon class="w-4 h-4" />
              Clear
            </button>
          </div>

          <div v-show="asrMode === 'upload'" class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <label class="flex items-center gap-2 px-4 py-2 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                <UploadIcon class="w-4 h-4" />
                <span>Choose file</span>
                <input
                  type="file"
                  accept="audio/*"
                  class="hidden"
                  @change="onFileChange"
                />
              </label>
              <button
                type="button"
                :disabled="!selectedFile || isProcessing || !asrReady"
                class="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-semibold text-white bg-blue-800 shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                @click="processUpload"
              >
                Transcribe
              </button>
              <button
                type="button"
                class="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-medium bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
                @click="clearUpload"
              >
                <Trash2Icon class="w-4 h-4" />
                Clear
              </button>
            </div>
            <p v-if="selectedFile" class="text-sm text-gray-600 dark:text-gray-400">
              {{ selectedFile.name }}
            </p>
            <p v-if="uploadStatus" class="text-sm font-medium" :class="uploadStatus === 'Done' ? 'text-green-600 dark:text-green-400' : uploadStatus.startsWith('Processing') ? 'text-gray-600 dark:text-gray-400' : 'text-red-600 dark:text-red-400'">
              {{ uploadStatus }}
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="flex items-center justify-center gap-2 px-4 py-2 rounded-xl font-medium bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
              @click="downloadSubtitle('srt')"
            >
              <DownloadIcon class="w-4 h-4" />
              Download SRT
            </button>
            <button
              type="button"
              class="flex items-center justify-center gap-2 px-4 py-2 rounded-xl font-medium bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
              @click="downloadSubtitle('txt')"
            >
              <DownloadIcon class="w-4 h-4" />
              Download TXT
            </button>
          </div>

          <div v-show="asrMode === 'mic'" class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">Transcript (Mic)</label>
            <textarea
              id="results-mic"
              rows="10"
              placeholder="Mic output will appear here..."
              readonly
              class="w-full min-h-[180px] text-lg leading-relaxed p-4 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-0 transition-colors resize-y"
            />
          </div>
          <div v-show="asrMode === 'upload'" class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">Transcript (Upload)</label>
            <textarea
              id="results-upload"
              rows="10"
              placeholder="Upload output will appear here..."
              readonly
              class="w-full min-h-[180px] text-lg leading-relaxed p-4 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-0 transition-colors resize-y"
            />
          </div>

          <section v-show="asrMode === 'mic'" id="sound-clips" class="space-y-2 overflow-auto" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-content.loading {
  display: none;
}
</style>
