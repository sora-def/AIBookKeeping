<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { deleteRecordsBatch, fetchTimeline } from '../api'
import type { TimelineItem } from '../types'

const emit = defineEmits<{ compose: [] }>()

const items = ref<TimelineItem[]>([])
const loading = ref(false)
const refreshing = ref(false)
const selecting = ref(false)
const selected = ref<Set<number>>(new Set())
const deleting = ref(false)
const error = ref('')
const scrollEl = ref<HTMLElement | null>(null)
const focusKey = ref('')

const ICONS: Record<string, { bg: string; mark: string }> = {
  工资: { bg: '#e2a31a', mark: '¥' },
  兼职: { bg: '#e25b86', mark: '⚙' },
  奖金: { bg: '#f0a020', mark: '✦' },
  红包: { bg: '#e23b3b', mark: '礼' },
  报销: { bg: '#3d8b6e', mark: '报' },
  投资: { bg: '#2f6fad', mark: '投' },
  一般: { bg: '#e6b325', mark: '普' },
  用餐: { bg: '#ef7d32', mark: '餐' },
  交通: { bg: '#3d7ea6', mark: '车' },
  服饰: { bg: '#7a5af8', mark: '衣' },
  数码: { bg: '#3b6ea5', mark: '数' },
  住房: { bg: '#8a6a3b', mark: '房' },
  医疗: { bg: '#d4536a', mark: '医' },
  旅游: { bg: '#2aa39a', mark: '旅' },
  学习: { bg: '#5b6ee1', mark: '学' },
  零食: { bg: '#e07a3d', mark: '零' },
  酒水: { bg: '#a33b3b', mark: '酒' },
  日用品: { bg: '#6a8f71', mark: '用' },
  娱乐: { bg: '#c45c9a', mark: '乐' },
  通讯: { bg: '#4c7ea8', mark: '讯' },
  家居: { bg: '#8d6b4a', mark: '家' },
  人情: { bg: '#c45c4a', mark: '情' },
  食材: { bg: '#6a9a4a', mark: '菜' },
}

interface DayGroup {
  date: string
  ym: string
  monthStart: boolean
  incomes: TimelineItem[]
  expenses: TimelineItem[]
}

const days = computed<DayGroup[]>(() => {
  const map = new Map<string, DayGroup>()
  for (const item of items.value) {
    const key = String(item.record_date)
    if (!map.has(key)) {
      const ym = key.slice(0, 7)
      map.set(key, { date: key, ym, monthStart: false, incomes: [], expenses: [] })
    }
    const group = map.get(key)!
    if (item.record_type === 'income') group.incomes.push(item)
    else group.expenses.push(item)
  }
  const groups = [...map.values()]
  let lastYm = ''
  for (const group of groups) {
    group.monthStart = group.ym !== lastYm
    lastYm = group.ym
  }
  return groups
})

const monthTotals = computed(() => {
  const map = new Map<string, { income: number; expense: number }>()
  for (const row of items.value) {
    const key = String(row.record_date).slice(0, 7)
    if (!map.has(key)) map.set(key, { income: 0, expense: 0 })
    const bucket = map.get(key)!
    if (row.record_type === 'income') bucket.income += row.amount_yuan
    else bucket.expense += row.amount_yuan
  }
  return map
})

const activeKey = computed(() => {
  if (focusKey.value && monthTotals.value.has(focusKey.value)) return focusKey.value
  const first = items.value[0]
  if (first) return String(first.record_date).slice(0, 7)
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
})

const monthLabel = computed(() => {
  const [year, month] = activeKey.value.split('-')
  return `${year}年${Number(month)}月`
})

const monthIncome = computed(() => monthTotals.value.get(activeKey.value)?.income ?? 0)
const monthExpense = computed(() => monthTotals.value.get(activeKey.value)?.expense ?? 0)

const monthItems = computed(() =>
  items.value.filter((row) => String(row.record_date).slice(0, 7) === activeKey.value),
)

const selectedCount = computed(() => selected.value.size)

const selectedAmount = computed(() => {
  let total = 0
  for (const row of items.value) {
    if (selected.value.has(row.id)) total += row.amount_yuan
  }
  return total
})

let monthMarks: { ym: string; top: number }[] = []
let scrollRaf = 0
let resizeObserver: ResizeObserver | null = null

function measureMonthMarks() {
  const root = scrollEl.value
  if (!root) {
    monthMarks = []
    return
  }
  monthMarks = [...root.querySelectorAll<HTMLElement>('[data-month-start]')].map((mark) => ({
    ym: mark.dataset.ym || '',
    top: mark.offsetTop,
  }))
}

function applyFocusMonth() {
  scrollRaf = 0
  const root = scrollEl.value
  if (!root || !monthMarks.length) return
  const y = root.scrollTop + 16
  let current = monthMarks[0].ym
  for (const mark of monthMarks) {
    if (!mark.ym) continue
    if (mark.top <= y) current = mark.ym
    else break
  }
  if (current && current !== focusKey.value) focusKey.value = current
}

function onTimelineScroll() {
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(applyFocusMonth)
}

function bindMonthWatch() {
  const root = scrollEl.value
  if (!root) return
  measureMonthMarks()
  applyFocusMonth()
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(() => {
    measureMonthMarks()
    applyFocusMonth()
  })
  resizeObserver.observe(root)
}

function unbindMonthWatch() {
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = 0
  resizeObserver?.disconnect()
  resizeObserver = null
}

function money(value: number) {
  return value.toFixed(2)
}

function dateLabel(raw: string) {
  const parts = String(raw).split('-')
  if (parts.length < 3) return raw
  return `${Number(parts[1])}月${Number(parts[2])}日`
}

function iconOf(name: string) {
  return ICONS[name] || { bg: '#8a8175', mark: (name || '记').slice(0, 1) }
}

function isSelected(id: number) {
  return selected.value.has(id)
}

function toggleSelect(id: number) {
  if (!selecting.value) return
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function startSelect() {
  selecting.value = true
  selected.value = new Set()
  error.value = ''
}

function cancelSelect() {
  selecting.value = false
  selected.value = new Set()
}

function selectAllMonth(recordType?: 'income' | 'expense') {
  const next = new Set(selected.value)
  for (const row of monthItems.value) {
    if (!recordType || row.record_type === recordType) next.add(row.id)
  }
  selected.value = next
  if (!selecting.value) selecting.value = true
}

watch(days, () => {
  void nextTick(bindMonthWatch)
})

watch(activeKey, () => {
  if (!selecting.value) return
  // 换月后去掉不在列表里的选中项
  const valid = new Set(items.value.map((row) => row.id))
  selected.value = new Set([...selected.value].filter((id) => valid.has(id)))
})

onMounted(load)
onActivated(() => {
  void nextTick(bindMonthWatch)
})
onDeactivated(unbindMonthWatch)
onBeforeUnmount(unbindMonthWatch)

async function load(refresh = false) {
  if (refresh) refreshing.value = true
  else loading.value = true
  error.value = ''
  try {
    items.value = await fetchTimeline(500)
    if (!refresh) {
      focusKey.value = items.value[0] ? String(items.value[0].record_date).slice(0, 7) : ''
    }
    const valid = new Set(items.value.map((row) => row.id))
    selected.value = new Set([...selected.value].filter((id) => valid.has(id)))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function reload() {
  if (loading.value || refreshing.value || deleting.value) return
  await load(true)
}

async function deleteSelected() {
  if (!selectedCount.value || deleting.value) return
  const ok = window.confirm(
    `确定删除选中的 ${selectedCount.value} 笔吗？\n合计 ${money(selectedAmount.value)} 元，此操作不可撤销。`,
  )
  if (!ok) return
  deleting.value = true
  error.value = ''
  try {
    const result = await deleteRecordsBatch([...selected.value])
    selected.value = new Set()
    selecting.value = false
    await load(true)
    if (result.deleted === 0) error.value = '没有删除任何记录'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '删除失败'
  } finally {
    deleting.value = false
  }
}

defineExpose({ reload })
</script>

<template>
  <div class="panel tl" :class="{ 'tl-selecting': selecting }">
    <header class="tl-hero">
      <button
        class="tl-refresh"
        type="button"
        aria-label="刷新时间线"
        :disabled="loading || refreshing || deleting"
        @click="reload"
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
    </header>

    <div class="tl-summary">
      <div class="tl-sum">
        <span>{{ monthLabel }}收入</span>
        <strong :key="activeKey + '-in'" class="tl-figure">{{ money(monthIncome) }}</strong>
      </div>
      <button class="tl-plus" type="button" aria-label="去 AI 记账" @click="emit('compose')">+</button>
      <div class="tl-sum right">
        <span>{{ monthLabel }}支出</span>
        <strong :key="activeKey + '-out'" class="tl-figure">{{ money(monthExpense) }}</strong>
      </div>
    </div>

    <div class="tl-manage">
      <template v-if="!selecting">
        <button
          class="tl-clear"
          type="button"
          :disabled="loading || refreshing || !items.length"
          @click="startSelect"
        >
          选择清除
        </button>
      </template>
      <template v-else>
        <button class="tl-clear ghost" type="button" :disabled="deleting" @click="selectAllMonth('income')">
          选本月收入
        </button>
        <button class="tl-clear ghost" type="button" :disabled="deleting" @click="selectAllMonth('expense')">
          选本月支出
        </button>
        <button
          class="tl-clear"
          type="button"
          :disabled="deleting || selectedCount === 0"
          @click="deleteSelected"
        >
          {{ deleting ? '删除中…' : `删除所选(${selectedCount})` }}
        </button>
        <button class="tl-clear ghost" type="button" :disabled="deleting" @click="cancelSelect">
          取消
        </button>
      </template>
    </div>

    <div ref="scrollEl" class="tl-scroll" @scroll.passive="onTimelineScroll">
      <p v-if="loading && !days.length" class="muted" style="text-align:center;">加载中…</p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <div v-if="!loading && !days.length" class="empty">还没有记录。点上方 + 去记一笔。</div>
      <p v-if="selecting && days.length" class="tl-select-hint muted">点条目勾选要清除的收入/支出，可跨日期选择。</p>

      <div
        v-for="day in days"
        :key="day.date"
        class="tl-row"
        :data-ym="day.monthStart ? day.ym : undefined"
        :data-month-start="day.monthStart ? '' : undefined"
      >
        <div class="tl-side left">
          <button
            v-for="row in day.incomes"
            :key="row.id"
            class="tl-entry"
            :class="{ selectable: selecting, selected: isSelected(row.id) }"
            type="button"
            @click="selecting ? toggleSelect(row.id) : undefined"
          >
            <span v-if="selecting" class="tl-check" aria-hidden="true">{{ isSelected(row.id) ? '✓' : '' }}</span>
            <div class="tl-amount">{{ money(row.amount_yuan) }}</div>
            <div class="tl-meta">
              <span>{{ row.category_name_zh || '一般' }}</span>
              <i class="tl-badge" :style="{ background: iconOf(row.category_name_zh).bg }">
                {{ iconOf(row.category_name_zh).mark }}
              </i>
            </div>
            <div v-if="row.note" class="tl-note">{{ row.note }}</div>
          </button>
        </div>
        <div class="tl-spine">
          <span>{{ dateLabel(day.date) }}</span>
          <b />
        </div>
        <div class="tl-side right">
          <button
            v-for="row in day.expenses"
            :key="row.id"
            class="tl-entry"
            :class="{ selectable: selecting, selected: isSelected(row.id) }"
            type="button"
            @click="selecting ? toggleSelect(row.id) : undefined"
          >
            <span v-if="selecting" class="tl-check" aria-hidden="true">{{ isSelected(row.id) ? '✓' : '' }}</span>
            <div class="tl-meta expense-meta">
              <i class="tl-badge" :style="{ background: iconOf(row.category_name_zh).bg }">
                {{ iconOf(row.category_name_zh).mark }}
              </i>
              <span>{{ row.category_name_zh || '一般' }}</span>
            </div>
            <div class="tl-amount">{{ money(row.amount_yuan) }}</div>
            <div v-if="row.note" class="tl-note">{{ row.note }}</div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
