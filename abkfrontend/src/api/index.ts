import { api, streamChat } from './http'
import type { BreakdownOut, ChatMessage, PendingAction, StatsOut, TimelineItem, User } from '../types'

export { streamChat }

export function register(body: {
  account: string
  password: string
  name?: string
  gender?: string
}) {
  return api<{ access_token: string; user: User }>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function login(body: { account: string; password: string }) {
  return api<{ access_token: string; user: User }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchMe() {
  return api<User>('/api/auth/me')
}

export function fetchThread(limit = 20) {
  return api<{
    id: number
    title: string
    messages: ChatMessage[]
    has_more: boolean
    pending: PendingAction | null
  }>(`/api/chat/thread?limit=${limit}`)
}

export function fetchOlderMessages(beforeId: number, limit = 20) {
  return api<{ messages: ChatMessage[]; has_more: boolean }>(
    `/api/chat/thread/messages?before_id=${beforeId}&limit=${limit}`,
  )
}

export function fetchTimeline(limit = 100) {
  return api<TimelineItem[]>(`/api/records/timeline?limit=${limit}`)
}

export function deleteRecordsBatch(ids: number[]) {
  return api<{
    ok: boolean
    deleted: number
    amount_yuan: number
    ids: number[]
  }>('/api/records/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
}

export function fetchStats(period: 'week' | 'month' | 'year') {
  return api<StatsOut>(`/api/records/stats?period=${period}`)
}

export function fetchBreakdown(period: 'week' | 'month' | 'year') {
  return api<BreakdownOut>(`/api/records/breakdown?period=${period}`)
}
