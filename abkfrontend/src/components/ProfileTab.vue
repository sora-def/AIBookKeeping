<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { fetchBreakdown, fetchStats } from '../api'
import { useAuth } from '../composables/useAuth'
import type { BreakdownOut, StatsOut } from '../types'
import LineChart from './LineChart.vue'
import PieChart from './PieChart.vue'

const { user, logout } = useAuth()
const error = ref('')
const loading = ref(false)
const refreshing = ref(false)
const week = ref<StatsOut | null>(null)
const month = ref<StatsOut | null>(null)
const year = ref<StatsOut | null>(null)
const dashPeriod = ref<'week' | 'month' | 'year'>('month')
const breakdown = ref<BreakdownOut | null>(null)

const cards = [
  { key: 'week', title: '本周', pick: () => week.value },
  { key: 'month', title: '本月', pick: () => month.value },
  { key: 'year', title: '本年', pick: () => year.value },
] as const

const periodTabs = [
  { key: 'week' as const, label: '本周' },
  { key: 'month' as const, label: '本月' },
  { key: 'year' as const, label: '本年' },
]

const dashLabel = computed(() => breakdown.value?.label || '本月')

async function loadBreakdown() {
  breakdown.value = await fetchBreakdown(dashPeriod.value)
}

async function load() {
  const first = !week.value && !month.value && !year.value
  if (first) loading.value = true
  else refreshing.value = true
  error.value = ''
  try {
    const [w, m, y, b] = await Promise.all([
      fetchStats('week'),
      fetchStats('month'),
      fetchStats('year'),
      fetchBreakdown(dashPeriod.value),
    ])
    week.value = w
    month.value = m
    year.value = y
    breakdown.value = b
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '统计加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

watch(dashPeriod, async () => {
  try {
    await loadBreakdown()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '仪表盘加载失败'
  }
})

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

    <div class="card chart-card chart-rise dash-card">
      <div class="dash-head">
        <div>
          <strong>分类仪表盘</strong>
          <div class="muted" style="margin-top:4px;">{{ dashLabel }}各项目占比</div>
        </div>
        <div class="dash-tabs" role="tablist" aria-label="仪表盘周期">
          <button
            v-for="tab in periodTabs"
            :key="tab.key"
            class="dash-tab"
            type="button"
            role="tab"
            :aria-selected="dashPeriod === tab.key"
            :class="{ active: dashPeriod === tab.key }"
            @click="dashPeriod = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <div v-if="breakdown" class="dash-grid">
        <PieChart
          title="收入构成"
          tone="income"
          :total="breakdown.total_income"
          :slices="breakdown.income"
        />
        <PieChart
          title="支出构成"
          tone="expense"
          :total="breakdown.total_expense"
          :slices="breakdown.expense"
        />
      </div>
    </div>

    <div
      v-for="(card, index) in cards"
      :key="card.key"
      class="card chart-card chart-rise"
      :style="{ animationDelay: `${(index + 1) * 90}ms` }"
    >
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <strong>{{ card.title }}趋势</strong>
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
