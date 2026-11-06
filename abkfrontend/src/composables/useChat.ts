import { nextTick, ref } from 'vue'
import { fetchOlderMessages, fetchThread, streamChat } from '../api'
import type { ChatMessage, PendingAction } from '../types'

function localMessage(role: ChatMessage['role'], content: string): ChatMessage {
  return {
    id: `local-${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    created_at: new Date().toISOString(),
  }
}

function clearConfirmActions(list: ChatMessage[]) {
  for (const msg of list) {
    if (msg.showConfirmActions) msg.showConfirmActions = false
  }
}

export function useChat() {
  const currentId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const hasMore = ref(false)
  const streaming = ref(false)
  const loading = ref(false)
  const loadingOlder = ref(false)
  const error = ref('')
  const toolHint = ref('')
  const stickToBottom = ref(true)
  const pending = ref<PendingAction | null>(null)

  let epoch = 0
  let controller: AbortController | null = null
  let revealQueue = ''
  let revealTimer: ReturnType<typeof setInterval> | null = null
  let revealTarget: ChatMessage | null = null

  function stopReveal() {
    if (revealTimer) {
      clearInterval(revealTimer)
      revealTimer = null
    }
  }

  function pumpReveal(target: ChatMessage) {
    revealTarget = target
    if (revealTimer) return
    revealTimer = setInterval(() => {
      if (!revealQueue || !revealTarget) {
        stopReveal()
        return
      }
      const size = revealQueue.length > 120 ? 4 : revealQueue.length > 40 ? 2 : 1
      revealTarget.content += revealQueue.slice(0, size)
      revealQueue = revealQueue.slice(size)
      if (!revealQueue) stopReveal()
    }, 16)
  }

  function applyPending(data: Record<string, unknown> | PendingAction | null | undefined) {
    if (!data || data.active === false) {
      pending.value = null
      clearConfirmActions(messages.value)
      return
    }
    pending.value = {
      active: true,
      id: typeof data.id === 'number' ? data.id : undefined,
      action_type: typeof data.action_type === 'string' ? data.action_type : undefined,
      summary: typeof data.summary === 'string' ? data.summary : undefined,
    }
    clearConfirmActions(messages.value)
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].role === 'assistant') {
        messages.value[i].showConfirmActions = true
        break
      }
    }
  }

  async function bootstrap(limit = 20) {
    loading.value = true
    error.value = ''
    try {
      const thread = await fetchThread(limit)
      currentId.value = thread.id
      messages.value = thread.messages.map((m) => ({
        id: m.id,
        role: m.role as ChatMessage['role'],
        content: m.content,
        created_at: m.created_at,
      }))
      hasMore.value = thread.has_more
      stickToBottom.value = true
      applyPending(thread.pending)
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '加载对话失败'
    } finally {
      loading.value = false
    }
  }

  async function loadOlder() {
    if (!hasMore.value || loadingOlder.value || streaming.value || !messages.value.length) return
    const first = messages.value[0]
    const beforeId = typeof first.id === 'number' ? first.id : Number(first.id)
    if (!Number.isFinite(beforeId)) return

    loadingOlder.value = true
    try {
      const page = await fetchOlderMessages(beforeId, 20)
      const mapped = page.messages.map((m) => ({
        id: m.id,
        role: m.role as ChatMessage['role'],
        content: m.content,
        created_at: m.created_at,
      }))
      messages.value = [...mapped, ...messages.value]
      hasMore.value = page.has_more
      if (pending.value?.active) applyPending(pending.value)
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '加载更早消息失败'
    } finally {
      loadingOlder.value = false
    }
  }

  async function send(text: string) {
    const content = text.trim()
    if (!content || streaming.value) return
    const myEpoch = ++epoch
    error.value = ''
    toolHint.value = ''
    stickToBottom.value = true
    clearConfirmActions(messages.value)
    revealQueue = ''
    stopReveal()
    messages.value.push(localMessage('user', content))
    const assistant = localMessage('assistant', '')
    assistant.streaming = true
    messages.value.push(assistant)
    const live = messages.value[messages.value.length - 1]
    streaming.value = true
    controller = new AbortController()

    try {
      await streamChat(
        { message: content, conversation_id: currentId.value },
        controller.signal,
        (event, data) => {
          if (myEpoch !== epoch) return
          if (event === 'meta') {
            const id = Number(data.conversation_id)
            if (id) currentId.value = id
          } else if (event === 'delta') {
            const piece = String(data.content || '')
            if (!piece) return
            revealQueue += piece
            pumpReveal(live)
          } else if (event === 'tool') {
            toolHint.value = String(data.content || '')
          } else if (event === 'pending') {
            applyPending(data as unknown as PendingAction)
          } else if (event === 'error') {
            error.value = String(data.message || '生成失败')
          }
        },
      )
    } catch (reason) {
      if ((reason as Error).name !== 'AbortError') {
        error.value = reason instanceof Error ? reason.message : '发送失败'
      }
    } finally {
      if (myEpoch === epoch) {
        while (revealQueue) {
          await new Promise((resolve) => setTimeout(resolve, 32))
        }
        live.streaming = false
        streaming.value = false
        toolHint.value = ''
        controller = null
        if (pending.value?.active) applyPending(pending.value)
        await nextTick()
      }
    }
  }

  async function confirmPending() {
    if (streaming.value || !pending.value?.active) return
    await send('确认')
  }

  async function cancelPending() {
    if (streaming.value || !pending.value?.active) return
    await send('取消')
  }

  return {
    currentId,
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
  }
}
