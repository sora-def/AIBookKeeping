export interface User {
  id: number
  account: string
  name: string
  gender: string
  avatar: string
  created_at: string
}

export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  streaming?: boolean
  toolHint?: string
  showConfirmActions?: boolean
}

export interface PendingAction {
  active: boolean
  id?: number
  action_type?: string
  summary?: string
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface TimelineItem {
  id: number
  record_date: string
  record_type: 'income' | 'expense' | string
  category_code: string
  category_name_zh: string
  amount_yuan: number
  note: string
}

export interface StatsPoint {
  label: string
  income: number
  expense: number
}

export interface StatsOut {
  period: 'week' | 'month' | 'year'
  points: StatsPoint[]
  total_income: number
  total_expense: number
}

export interface BreakdownSlice {
  category_code: string
  category: string
  count: number
  amount_yuan: number
  percent: number
}

export interface BreakdownOut {
  period: 'week' | 'month' | 'year'
  label: string
  start_date: string
  end_date: string
  total_income: number
  total_expense: number
  income: BreakdownSlice[]
  expense: BreakdownSlice[]
}
