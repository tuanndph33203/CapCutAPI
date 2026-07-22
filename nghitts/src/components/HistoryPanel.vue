<script setup>
import { ref, watch } from 'vue';
import {
  XIcon,
  PlayIcon,
  DownloadIcon,
  CopyIcon,
  Trash2Icon,
} from 'lucide-vue-next';
import { getEntries, deleteEntry, clearAll } from '../utils/history-store.js';

const props = defineProps({
  open: { type: Boolean, default: false },
});

const emit = defineEmits(['close']);

const entries = ref([]);
const loading = ref(false);
const clearing = ref(false);
const copyId = ref(null);

async function loadEntries() {
  loading.value = true;
  try {
    entries.value = await getEntries();
  } catch (err) {
    console.error('Failed to load history:', err);
    entries.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) loadEntries();
  }
);

function formatDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleString(undefined, {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

function previewText(text, maxLen = 80) {
  if (!text) return '';
  const t = text.trim();
  return t.length <= maxLen ? t : t.slice(0, maxLen) + '…';
}

function langLabel(lang) {
  const labels = { vi: 'Tiếng Việt', en: 'English', id: 'Indonesia' };
  return labels[lang] || lang;
}

function downloadFilename(entry) {
  const d = new Date(entry.createdAt);
  const date = d.toISOString().slice(0, 10);
  const time = d.toTimeString().slice(0, 8).replace(/:/g, '-');
  return `tts-${date}-${time}.wav`;
}

function playAudio(entry) {
  if (!entry?.audio) return;
  const url = URL.createObjectURL(entry.audio);
  const audio = new Audio(url);
  audio.onended = () => URL.revokeObjectURL(url);
  audio.onerror = () => URL.revokeObjectURL(url);
  audio.play().catch(() => URL.revokeObjectURL(url));
}

function downloadAudio(entry) {
  if (!entry?.audio) return;
  const url = URL.createObjectURL(entry.audio);
  const link = document.createElement('a');
  link.href = url;
  link.download = downloadFilename(entry);
  link.click();
  URL.revokeObjectURL(url);
}

async function copyText(entry) {
  if (!entry?.text) return;
  try {
    await navigator.clipboard.writeText(entry.text);
    copyId.value = entry.id;
    setTimeout(() => { copyId.value = null; }, 2000);
  } catch (err) {
    console.error('Copy failed:', err);
  }
}

async function removeEntry(entry) {
  try {
    await deleteEntry(entry.id);
    entries.value = entries.value.filter((e) => e.id !== entry.id);
  } catch (err) {
    console.error('Delete failed:', err);
  }
}

function voiceLabel(voice) {
  if (voice === null || voice === undefined) return '';
  if (typeof voice === 'number') {
    const idx = Number.isFinite(voice) ? voice : 0;
    return `Voice ${idx + 1}`;
  }
  return String(voice);
}

async function handleClearAll() {
  clearing.value = true;
  try {
    await clearAll();
    entries.value = [];
  } catch (err) {
    console.error('Clear all failed:', err);
  } finally {
    clearing.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="panel">
      <div
        v-if="open"
        class="fixed inset-0 z-[100] flex justify-end"
        role="dialog"
        aria-label="History"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/30 dark:bg-black/50"
          @click="emit('close')"
        />

        <!-- Sidebar -->
        <div
          class="relative w-full max-w-md bg-white dark:bg-gray-900 shadow-xl border-l border-gray-200 dark:border-gray-700 flex flex-col animate-slide-in"
        >
          <!-- Header -->
          <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200">
              Lịch sử
            </h2>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 disabled:opacity-50"
                :disabled="clearing || entries.length === 0"
                @click="handleClearAll"
              >
                Xóa tất cả
              </button>
              <button
                type="button"
                class="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
                aria-label="Đóng"
                @click="emit('close')"
              >
                <XIcon class="w-5 h-5" />
              </button>
            </div>
          </div>

          <!-- List -->
          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="loading" class="flex justify-center py-8">
              <div class="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full" />
            </div>
            <div
              v-else-if="entries.length === 0"
              class="text-center py-12 text-gray-500 dark:text-gray-400 text-sm"
            >
              Chưa có lịch sử
            </div>
            <ul v-else class="space-y-3">
              <li
                v-for="entry in entries"
                :key="entry.id"
                class="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-3 space-y-2"
              >
                <p class="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                  {{ previewText(entry.text) }}
                </p>
                <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>{{ formatDate(entry.createdAt) }}</span>
                  <span class="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700">
                    {{ langLabel(entry.lang) }}
                  </span>
                  <span
                    v-if="entry.model === 'Libritts_r' && voiceLabel(entry.voice)"
                    class="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700"
                  >
                    {{ voiceLabel(entry.voice) }}
                  </span>
                  <span class="truncate max-w-[120px]" :title="entry.model">
                    {{ entry.model }}
                  </span>
                </div>
                <div class="flex items-center gap-1 pt-1">
                  <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
                    title="Phát"
                    @click="playAudio(entry)"
                  >
                    <PlayIcon class="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
                    title="Tải xuống"
                    @click="downloadAudio(entry)"
                  >
                    <DownloadIcon class="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
                    :title="copyId === entry.id ? 'Đã copy' : 'Copy văn bản'"
                    @click="copyText(entry)"
                  >
                    <CopyIcon class="w-4 h-4" :class="copyId === entry.id ? 'text-green-500' : ''" />
                  </button>
                  <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-600 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                    title="Xóa"
                    @click="removeEntry(entry)"
                  >
                    <Trash2Icon class="w-4 h-4" />
                  </button>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.panel-enter-active,
.panel-leave-active {
  transition: opacity 0.2s ease;
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}
.panel-enter-active .relative,
.panel-leave-active .relative {
  transition: transform 0.25s ease;
}
.panel-enter-from .relative,
.panel-leave-to .relative {
  transform: translateX(100%);
}
.animate-slide-in {
  animation: slideIn 0.25s ease;
}
@keyframes slideIn {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}
</style>
