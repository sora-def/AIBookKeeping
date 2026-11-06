<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import type { StatsPoint } from '../types'

const props = defineProps<{ points: StatsPoint[] }>()

const width = 640
const height = 236
const padLeft = 52
const padRight = 16
const padTop = 16
const padBottom = 36
const baseY = height - padBottom
const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
const active = ref(-1)

interface Dot {
  x: number
  yIncome: number
  yExpense: number
  label: string
  income: number
  expense: number
}

interface Tick {
  y: number
  text: string
}

const model = computed(() => {
  const pts = props.points
  if (!pts.length) {
    return { dots: [] as Dot[], ticks: [] as Tick[], income: '', expense: '', incomeArea: '', expenseArea: '', crowded: false }
  }
  const maxY = Math.max(1, ...pts.flatMap((p) => [p.income, p.expense])) * 1.08
  const stepX = pts.length === 1 ? 0 : (width - padLeft - padRight) / (pts.length - 1)
  const dots: Dot[] = pts.map((p, i) => ({
    x: padLeft + i * stepX,
    yIncome: baseY - (p.income / maxY) * (baseY - padTop),
    yExpense: baseY - (p.expense / maxY) * (baseY - padTop),
    label: p.label,
    income: p.income,
    expense: p.expense,
  }))
  const ticks: Tick[] = [0, 0.5, 1].map((ratio) => ({
    y: baseY - ratio * (baseY - padTop),
    text: formatAxis(maxY * ratio),
  }))

  function curve(key: 'yIncome' | 'yExpense') {
    if (dots.length === 1) return `M ${dots[0].x} ${dots[0][key]}`
    let d = `M ${dots[0].x.toFixed(1)} ${dots[0][key].toFixed(1)}`
    for (let i = 0; i < dots.length - 1; i += 1) {
      const a = dots[i]
      const b = dots[i + 1]
      const cx = (a.x + b.x) / 2
      d += ` C ${cx.toFixed(1)} ${a[key].toFixed(1)}, ${cx.toFixed(1)} ${b[key].toFixed(1)}, ${b.x.toFixed(1)} ${b[key].toFixed(1)}`
    }
    return d
  }

  function area(key: 'yIncome' | 'yExpense') {
    const line = curve(key)
    const last = dots[dots.length - 1]
    const first = dots[0]
    return `${line} L ${last.x.toFixed(1)} ${baseY} L ${first.x.toFixed(1)} ${baseY} Z`
  }

  return {
    dots,
    ticks,
    income: curve('yIncome'),
    expense: curve('yExpense'),
    incomeArea: area('yIncome'),
    expenseArea: area('yExpense'),
    crowded: dots.length > 10,
  }
})

function formatAxis(value: number) {
  if (value >= 10000) {
    const wan = value / 10000
    return `${wan >= 10 ? wan.toFixed(0) : wan.toFixed(1)}万`
  }
  if (value >= 1000) return `${Math.round(value / 100) / 10}k`
  return String(Math.round(value))
}

const tip = computed(() => {
  const dot = model.value.dots[active.value]
  if (!dot) return null
  const left = Math.min(Math.max(dot.x / width, 0.12), 0.88)
  return { dot, left: `${left * 100}%` }
})

function money(value: number) {
  return value.toFixed(2)
}

function move(event: MouseEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !model.value.dots.length) return
  const x = ((event.clientX - rect.left) / rect.width) * width
  let best = 0
  let bestDist = Infinity
  model.value.dots.forEach((dot, index) => {
    const dist = Math.abs(dot.x - x)
    if (dist < bestDist) {
      bestDist = dist
      best = index
    }
  })
  active.value = best
}
</script>

<template>
  <div class="trend">
    <svg
      class="chart-svg trend-svg"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      aria-label="收支趋势"
      @mousemove="move"
      @mouseleave="active = -1"
    >
      <defs>
        <linearGradient :id="`${uid}-in`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0f7a5a" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#0f7a5a" stop-opacity="0.02" />
        </linearGradient>
        <linearGradient :id="`${uid}-out`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#c45c26" stop-opacity="0.26" />
          <stop offset="100%" stop-color="#c45c26" stop-opacity="0.02" />
        </linearGradient>
      </defs>

      <g v-for="(tick, i) in model.ticks" :key="'tick' + i">
        <line :x1="padLeft" :y1="tick.y" :x2="width - padRight" :y2="tick.y" stroke="#e7ece8" />
        <text :x="padLeft - 8" :y="tick.y + 4" text-anchor="end" font-size="11" fill="#8a938d">
          {{ tick.text }}
        </text>
      </g>
      <line :x1="padLeft" :y1="baseY" :x2="width - padRight" :y2="baseY" stroke="#d5ddd8" />
      <path v-if="model.incomeArea" class="trend-area" :d="model.incomeArea" :fill="`url(#${uid}-in)`" />
      <path v-if="model.expenseArea" class="trend-area trend-area-late" :d="model.expenseArea" :fill="`url(#${uid}-out)`" />
      <path v-if="model.income" class="trend-line" pathLength="1" :d="model.income" fill="none" stroke="#0f7a5a" stroke-width="2.6" />
      <path v-if="model.expense" class="trend-line trend-line-late" pathLength="1" :d="model.expense" fill="none" stroke="#c45c26" stroke-width="2.6" />

      <line
        v-if="tip"
        :x1="tip.dot.x"
        :y1="padTop"
        :x2="tip.dot.x"
        :y2="baseY"
        stroke="#c5d0ca"
        stroke-dasharray="3 3"
      />
      <circle
        v-for="(dot, i) in model.dots"
        :key="'in-dot' + i"
        :cx="dot.x"
        :cy="dot.yIncome"
        :r="active === i ? 5.5 : 3.4"
        fill="#0f7a5a"
        stroke="#fff"
        stroke-width="1.6"
      />
      <circle
        v-for="(dot, i) in model.dots"
        :key="'out-dot' + i"
        :cx="dot.x"
        :cy="dot.yExpense"
        :r="active === i ? 5.5 : 3.4"
        fill="#c45c26"
        stroke="#fff"
        stroke-width="1.6"
      />

      <g v-for="(dot, i) in model.dots" :key="dot.label + i">
        <text
          :x="dot.x"
          :y="height - 8"
          text-anchor="middle"
          :font-size="model.crowded ? 10 : 11"
          fill="#66756d"
          :transform="model.crowded ? `rotate(-50 ${dot.x} ${height - 8})` : undefined"
        >
          {{ dot.label }}
        </text>
      </g>
    </svg>

    <div v-if="tip" class="trend-tip" :style="{ left: tip.left }">
      <div class="trend-tip-title">{{ tip.dot.label }}</div>
      <div class="trend-tip-row income">收入 {{ money(tip.dot.income) }}</div>
      <div class="trend-tip-row expense">支出 {{ money(tip.dot.expense) }}</div>
    </div>
  </div>
</template>

<style scoped>
.trend {
  position: relative;
}

.trend-svg {
  cursor: crosshair;
}

.trend-line {
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: trend-draw 0.9s ease forwards;
}

.trend-line-late {
  animation-delay: 0.12s;
}

.trend-area {
  opacity: 0;
  animation: trend-fade 0.55s ease 0.35s forwards;
}

.trend-area-late {
  animation-delay: 0.48s;
}

.trend-tip {
  position: absolute;
  top: 6px;
  transform: translateX(-50%);
  min-width: 132px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(28, 36, 32, 0.92);
  color: #fff;
  font-size: 0.78rem;
  line-height: 1.45;
  pointer-events: none;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.16);
  animation: trend-pop 0.16s ease;
}

.trend-tip-title {
  margin-bottom: 2px;
  color: rgba(255, 255, 255, 0.72);
}

.trend-tip-row.income {
  color: #8ddeb8;
}

.trend-tip-row.expense {
  color: #f0b089;
}

@keyframes trend-draw {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes trend-fade {
  to {
    opacity: 1;
  }
}

@keyframes trend-pop {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}
</style>
