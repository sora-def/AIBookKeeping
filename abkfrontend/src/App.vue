<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import AuthView from './components/AuthView.vue'
import ChatTab from './components/ChatTab.vue'
import ProfileTab from './components/ProfileTab.vue'
import TimelineTab from './components/TimelineTab.vue'
import { useAuth } from './composables/useAuth'

const { ready, isLoggedIn, bootstrap } = useAuth()
const tab = ref<'chat' | 'timeline' | 'me'>('chat')
const timelineRef = ref<{ reload: () => Promise<void> } | null>(null)
const views = { chat: ChatTab, timeline: TimelineTab, me: ProfileTab }
const currentView = computed(() => views[tab.value])

onMounted(() => {
  void bootstrap()
})

watch(tab, async (value) => {
  if (value !== 'timeline') return
  await nextTick()
  const panel = timelineRef.value as { reload?: () => Promise<void> } | null
  void panel?.reload?.()
})
</script>

<template>
  <div v-if="!ready" class="auth-page muted">加载中…</div>
  <AuthView v-else-if="!isLoggedIn" />
  <div v-else class="app-shell">
    <main class="app-main">
      <Transition name="tab-fade" mode="out-in">
        <KeepAlive>
          <component
            :is="currentView"
            :key="tab"
            ref="timelineRef"
            @compose="tab = 'chat'"
          />
        </KeepAlive>
      </Transition>
    </main>
    <nav class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'chat' }" type="button" @click="tab = 'chat'">AI 记账</button>
      <button class="tab-btn" :class="{ active: tab === 'timeline' }" type="button" @click="tab = 'timeline'">时间线</button>
      <button class="tab-btn" :class="{ active: tab === 'me' }" type="button" @click="tab = 'me'">我的</button>
    </nav>
  </div>
</template>
