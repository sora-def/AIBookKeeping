<script setup lang="ts">
import { computed, ref } from 'vue'
import type { BreakdownSlice } from '../types'

const props = withDefaults(
  defineProps<{
    title: string
    total: number
    slices: BreakdownSlice[]
    tone?: 'income' | 'expense'
  }>(),
  { tone: 'expense' },
)

const active = ref(-1)

const INCOME_COLORS = ['#0f7a5a', '#2f9e78', '#57b894', '#7dcfb0', '#a3e0c8', '#3d8b6e', '#1f6b52', '#5aa88a']
const EXPENSE_COLORS = ['#c45c26', '#d4783d', '#e0945a', '#e8ad7c', '#f0c6a0', '#a34828', '#b85f3a', '#dea06f']

const size = 220
const cx = size / 2
const cy = size / 2
const radius = 78
const inner = 46

const arcs = computed(() => {
  const total = props.slices.reduce((sum, item) => sum + item.amount_yuan, 0)
  if (total <= 0) return [] as Array<{
    d: string
    color: string
    slice: BreakdownSlice
    mid: number
  }>
  const colors = props.tone === 'income' ? INCOME_COLORS : EXPENSE_COLORS
  let angle = -Math.PI / 2
  return props.slices.map((slice, index) => {
    const portion = slice.amount_yuan / total
    const sweep = portion * Math.PI * 2
    const start = angle
    const end = angle + sweep
    angle = end
    const large = sweep > Math.PI ? 1 : 0
    const x1 = cx + radius * Math.cos(start)
    const y1 = cy + radius * Math.sin(start)
    const x2 = cx + radius * Math.cos(end)
    const y2 = cy + radius * Math.sin(end)
    const ix1 = cx + inner * Math.cos(end)
    const iy1 = cy + inner * Math.sin(end)
    const ix2 = cx + inner * Math.cos(start)
    const iy2 = cy + inner * Math.sin(start)
    const d = [
      `M ${x1.toFixed(2)} ${y1.toFixed(2)}`,
      `A ${radius} ${radius} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`,
      `L ${ix1.toFixed(2)} ${iy1.toFixed(2)}`,
      `A ${inner} ${inner} 0 ${large} 0 ${ix2.toFixed(2)} ${iy2.toFixed(2)}`,
      'Z',
    ].join(' ')
    return {
      d,
      color: colors[index % colors.length],
      slice,
      mid: start + sweep / 2,
    }
  })
})

function money(value: number) {
  return value.toFixed(2)
}
</script>

<template>
  <div class="pie" :class="tone">
    <div class="pie-head">
      <strong>{{ title }}</strong>
      <span class="pie-total">合计 {{ money(total) }}</span>
    </div>

    <div v-if="!slices.length" class="pie-empty muted">暂无分类数据</div>
    <div v-else class="pie-body">
      <svg class="pie-svg" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="title">
        <path
          v-for="(arc, index) in arcs"
          :key="arc.slice.category_code + index"
          :d="arc.d"
          :fill="arc.color"
          class="pie-arc"
          :class="{ active: active === index }"
          @mouseenter="active = index"
          @mouseleave="active = -1"
        />
        <circle :cx="cx" :cy="cy" :r="inner - 2" fill="#fffdf9" />
        <text :x="cx" :y="cy - 4" text-anchor="middle" class="pie-center-label">
          {{ active >= 0 ? arcs[active].slice.category : (tone === 'income' ? '收入' : '支出') }}
        </text>
        <text :x="cx" :y="cy + 14" text-anchor="middle" class="pie-center-value">
          {{ active >= 0 ? money(arcs[active].slice.amount_yuan) : money(total) }}
        </text>
      </svg>

      <ul class="pie-legend">
        <li
          v-for="(arc, index) in arcs"
          :key="'leg-' + arc.slice.category_code + index"
          :class="{ active: active === index }"
          @mouseenter="active = index"
          @mouseleave="active = -1"
        >
          <i :style="{ background: arc.color }" />
          <div class="pie-leg-text">
            <span>{{ arc.slice.category }}</span>
            <small>{{ arc.slice.count }} 笔 · {{ arc.slice.percent }}%</small>
          </div>
          <em>{{ money(arc.slice.amount_yuan) }}</em>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.pie {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pie-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.pie-total {
  color: #8a8176;
  font-size: 0.82rem;
}

.pie-empty {
  padding: 28px 0;
  text-align: center;
}

.pie-body {
  display: grid;
  grid-template-columns: minmax(140px, 180px) 1fr;
  gap: 12px;
  align-items: center;
}

.pie-svg {
  width: 100%;
  max-width: 180px;
  margin: 0 auto;
}

.pie-arc {
  cursor: pointer;
  transform-origin: center;
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.pie-arc.active {
  filter: brightness(1.05);
  transform: scale(1.02);
}

.pie-center-label {
  fill: #8a8176;
  font-size: 11px;
}

.pie-center-value {
  fill: #3f3a34;
  font-size: 13px;
  font-weight: 600;
}

.pie-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 220px;
  overflow: auto;
}

.pie-legend li {
  display: grid;
  grid-template-columns: 10px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border-radius: 10px;
  cursor: default;
}

.pie-legend li.active {
  background: #f3efe8;
}

.pie-legend i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.pie-leg-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.pie-leg-text span {
  font-size: 0.86rem;
  color: #3f3a34;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pie-leg-text small {
  color: #9a9085;
  font-size: 0.72rem;
}

.pie-legend em {
  font-style: normal;
  font-size: 0.84rem;
  font-weight: 600;
  color: #5a5249;
}

.pie.income .pie-center-value {
  fill: #0f7a5a;
}

.pie.expense .pie-center-value {
  fill: #c45c26;
}

@media (max-width: 560px) {
  .pie-body {
    grid-template-columns: 1fr;
  }

  .pie-svg {
    max-width: 200px;
  }
}
</style>
