<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchStats } from '../api'
import { useAuth } from '../composables/useAuth'
import type { StatsOut } from '../types'
import LineChart from './LineChart.vue'

const { user, logout } = useAuth()
const error = ref('')
const loading = ref(false)
const refreshing = ref(false)
const week = ref<StatsOut | null>(null)
const month = ref<StatsOut | null>(null)
const year = ref<StatsOut | null>(null)

const cards = [
  { key: 'week', title: '本周', pick: () => week.value },
  { key: 'month', title: '本月', pick: () => month.value },
  { key: 'year', title: '本年', pick: () => year.value },
] as const

async function load() {
  const first = !week.value && !month.value && !year.value
  if (first) loading.value = true
  else refreshing.value = true
  error.value = ''
  try {
    const [w, m, y] = await Promise.all([
      fetchStats('week'),
      fetchStats('month'),
      fetchStats('year'),
    ])
    week.value = w
    month.value = m
    year.value = y
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '统计加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

onMounted(load)

const genderLabel: Record<string, string> = {
  male: '男',
  female: '女',
  unknown: '未设置',
}
</script>

<template>
  <div class="panel page-scroll">
    <div class="card profile-head">
      <div class="avatar">
        <img v-if="user?.avatar" :src="user.avatar" alt="" />
        <span v-else>{{ (user?.name || user?.account || '?').slice(0, 1) }}</span>
      </div>
      <div style="flex:1;">
        <div style="font-size:1.2rem;font-weight:700;">{{ user?.name || user?.account }}</div>
        <div class="muted">账号 {{ user?.account }} · {{ genderLabel[user?.gender || 'unknown'] }}</div>
      </div>
      <div class="profile-actions">
        <button
          class="icon-btn"
          type="button"
          aria-label="刷新趋势图"
          :disabled="loading || refreshing"
          @click="load"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" :class="{ spinning: refreshing }">
            <path
              d="M20 12a8 8 0 1 1-2.3-5.6"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
            <path
              d="M20 4v5h-5"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
        <button class="btn ghost" type="button" @click="logout">退出</button>
      </div>
    </div>

    <p v-if="loading && !week" class="muted">加载中…</p>
    <p v-if="error" class="error-text">{{ error }}</p>

    <div
      v-for="(card, index) in cards"
      :key="card.key"
      class="card chart-card chart-rise"
      :style="{ animationDelay: `${index * 90}ms` }"
    >
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <strong>{{ card.title }}</strong>
      </div>
      <LineChart v-if="card.pick()" :points="card.pick()!.points" />
      <div v-if="card.pick()" class="stats-row">
        <div class="stat-box">
          <div class="muted">收入</div>
          <div class="amount income">+{{ card.pick()!.total_income.toFixed(2) }}</div>
        </div>
        <div class="stat-box expense">
          <div class="muted">支出</div>
          <div class="amount expense">-{{ card.pick()!.total_expense.toFixed(2) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
