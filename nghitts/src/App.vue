<script setup>
import { ref } from 'vue';
import { RouterView } from 'vue-router';
import ThemeToggle from './components/ThemeToggle.vue';
import HistoryPanel from './components/HistoryPanel.vue';
import { History } from 'lucide-vue-next';

const shareCopied = ref(false);
let shareFeedbackTimer = null;
const historyOpen = ref(false);

function copyShareLink() {
  const url = window.location.href;
  navigator.clipboard.writeText(url).then(() => {
    shareCopied.value = true;
    if (shareFeedbackTimer) clearTimeout(shareFeedbackTimer);
    shareFeedbackTimer = setTimeout(() => {
      shareCopied.value = false;
    }, 2000);
  });
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-purple-50 via-pink-50 to-indigo-100 dark:from-gray-900 dark:via-purple-900/20 dark:to-gray-800 transition-colors duration-300">
    <!-- Header -->
    <header class="sticky top-0 z-50 backdrop-blur-xl bg-white/80 dark:bg-gray-900/80 border-b border-gray-200/50 dark:border-gray-700/50">
      <div class="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="text-3xl">🗣️</div>
          <div>
            <h1 class="text-xl font-bold bg-gradient-to-r text-blue-800 dark:text-blue-500">
              NGHI-TTS
            </h1>
            <p class="text-sm text-muted-foreground hidden sm:block">Local text-to-speech in your browser</p>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <button
            type="button"
            class="px-3 py-1.5 rounded-full text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors min-w-[5rem]"
            :class="shareCopied ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300' : ''"
            @click="copyShareLink"
          >
            {{ shareCopied ? 'Đã copy link' : 'Chia sẻ' }}
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-full text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors flex items-center gap-1.5"
            :class="historyOpen ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium' : ''"
            @click="historyOpen = !historyOpen"
          >
            <History class="w-4 h-4" />
            Lịch sử
          </button>
          <ThemeToggle />
        </div>
      </div>
    </header>

    <!-- Mode / Page tabs: TTS by language or ASR (not UI language) -->
    <div class="bg-white/50 dark:bg-gray-900/50 border-b border-gray-200/50 dark:border-gray-700/50">
      <div class="max-w-4xl mx-auto px-4 py-2">
        <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">Chế độ / Mode</p>
        <nav class="flex flex-wrap items-center gap-2 text-sm" role="tablist" aria-label="Chọn chế độ TTS hoặc ASR">
          <router-link
            to="/"
            role="tab"
            class="px-3 py-2 rounded-lg transition-colors border border-transparent"
            :class="$route.path === '/' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium border-blue-200 dark:border-blue-800' : 'bg-gray-100/80 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border-gray-200 dark:border-gray-700'"
          >
            <span class="font-medium text-gray-500 dark:text-gray-400">TTS</span> Tiếng Việt
          </router-link>
          <router-link
            to="/en"
            role="tab"
            class="px-3 py-2 rounded-lg transition-colors border border-transparent"
            :class="$route.path === '/en' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium border-blue-200 dark:border-blue-800' : 'bg-gray-100/80 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border-gray-200 dark:border-gray-700'"
          >
            <span class="font-medium text-gray-500 dark:text-gray-400">TTS</span> English
          </router-link>
          <router-link
            to="/id"
            role="tab"
            class="px-3 py-2 rounded-lg transition-colors border border-transparent"
            :class="$route.path === '/id' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium border-blue-200 dark:border-blue-800' : 'bg-gray-100/80 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border-gray-200 dark:border-gray-700'"
          >
            <span class="font-medium text-gray-500 dark:text-gray-400">TTS</span> Indonesia
          </router-link>
          <router-link
            to="/asr"
            role="tab"
            class="px-3 py-2 rounded-lg transition-colors border border-transparent"
            :class="$route.path === '/asr' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium border-blue-200 dark:border-blue-800' : 'bg-gray-100/80 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border-gray-200 dark:border-gray-700'"
          >
            <span class="font-medium text-gray-500 dark:text-gray-400">ASR</span> Nhận dạng giọng nói
          </router-link>
        </nav>
      </div>
    </div>

    <!-- Main Content -->
    <main class="container mx-auto px-4 pt-6 pb-4 max-w-4xl">
      <RouterView />
    </main>

    <HistoryPanel :open="historyOpen" @close="historyOpen = false" />
  </div>
</template>
