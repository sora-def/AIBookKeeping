<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useChat } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const {
  messages,
  hasMore,
  streaming,
  loading,
  loadingOlder,
  error,
  toolHint,
  stickToBottom,
  pending,
  bootstrap,
  loadOlder,
  send,
  confirmPending,
  cancelPending,
} = useChat()

const draft = ref('')
const listEl = ref<HTMLElement | null>(null)
const showJump = ref(false)

onMounted(async () => {
  await bootstrap(20)
  await nextTick()
  scrollToBottom(true)
})

watch(
  messages,
  async () => {
    if (!stickToBottom.value) return
    await nextTick()
    scrollToBottom(false)
  },
  { deep: true },
)

function scrollToBottom(force = false) {
  const el = listEl.value
  if (!el) return
  if (!force && !stickToBottom.value) return
  el.scrollTop = el.scrollHeight
  showJump.value = false
}

async function onScroll() {
  const el = listEl.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = distance < 80
  showJump.value = distance > 160

  if (el.scrollTop < 48 && hasMore.value && !loadingOlder.value) {
    const prevHeight = el.scrollHeight
    await loadOlder()
    await nextTick()
    el.scrollTop = el.scrollHeight - prevHeight
  }
}

async function onSend() {
  if (streaming.value) return
  const text = draft.value
  draft.value = ''
  stickToBottom.value = true
  await send(text)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void onSend()
  }
}

function jumpLatest() {
  stickToBottom.value = true
  scrollToBottom(true)
}
</script>

<template>
  <div class="panel chat-main-only">
    <section class="chat-main">
      <div class="chat-top">
        <strong>AI 记账</strong>
      </div>

      <div ref="listEl" class="messages" @scroll="onScroll">
        <div v-if="loading" class="empty">正在加载最近对话…</div>
        <button
          v-else-if="hasMore"
          class="load-older"
          type="button"
          :disabled="loadingOlder"
          @click="loadOlder"
        >
          {{ loadingOlder ? '加载中…' : '加载更早的消息' }}
        </button>

        <div v-if="!loading && !messages.length" class="empty">
          直接跟我说就行，比如「今天午餐花了 28 元」。
          <br />
          记一笔或删一笔前，我会先跟你确认。
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="msg-block msg-in"
          :class="msg.role"
        >
          <div
            v-if="msg.content"
            class="bubble"
            :class="msg.role"
            v-html="renderMarkdown(msg.content)"
          />
          <div
            v-if="msg.streaming"
            class="typing"
            :class="{ 'typing-follow': msg.content }"
            aria-label="正在回复"
          >
            <span /><span /><span />
          </div>
          <div
            v-if="msg.showConfirmActions && pending?.active && !streaming"
            class="confirm-actions"
          >
            <button class="btn" type="button" @click="confirmPending">确认</button>
            <button class="btn ghost" type="button" @click="cancelPending">取消</button>
          </div>
        </div>
      </div>

      <button
        v-if="showJump"
        class="jump-latest"
        type="button"
        aria-label="回到最新"
        @click="jumpLatest"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M12 5v13M6.5 12.5 12 18l5.5-5.5"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <p v-if="toolHint" class="status-hint">{{ toolHint }}</p>
      <p v-if="error" class="error-text">{{ error }}</p>

      <div class="composer">
        <textarea
          v-model="draft"
          class="input chat-input"
          rows="1"
          placeholder="发消息…"
          :disabled="streaming"
          @keydown="onKeydown"
        />
        <button class="send-btn" type="button" :disabled="streaming || !draft.trim()" @click="onSend" aria-label="发送">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path
              d="M12 19V6M6.5 11.5 12 6l5.5 5.5"
              fill="none"
              stroke="currentColor"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      </div>
    </section>
  </div>
</template>
