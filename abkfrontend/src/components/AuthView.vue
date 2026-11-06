<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '../composables/useAuth'

const { login, register } = useAuth()
const mode = ref<'login' | 'register'>('login')
const account = ref('')
const password = ref('')
const name = ref('')
const gender = ref('unknown')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await login(account.value.trim(), password.value)
    } else {
      await register(account.value.trim(), password.value, name.value.trim(), gender.value)
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="card auth-card">
      <h1>AI 记账</h1>
      <p class="muted">轻语一笔账，收支随口记</p>
      <form @submit.prevent="submit">
        <input v-model="account" class="input" placeholder="账号" autocomplete="username" required />
        <input
          v-model="password"
          class="input"
          type="password"
          placeholder="密码（至少 6 位）"
          autocomplete="current-password"
          required
        />
        <template v-if="mode === 'register'">
          <input v-model="name" class="input" placeholder="姓名（可选）" />
          <select v-model="gender" class="input">
            <option value="unknown">性别：未设置</option>
            <option value="male">男</option>
            <option value="female">女</option>
          </select>
        </template>
        <p v-if="error" class="error-text">{{ error }}</p>
        <button class="btn" type="submit" :disabled="loading">
          {{ loading ? '请稍候…' : mode === 'login' ? '登录' : '注册并进入' }}
        </button>
      </form>
      <div class="auth-switch">
        <button type="button" @click="mode = mode === 'login' ? 'register' : 'login'">
          {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
        </button>
      </div>
    </div>
  </div>
</template>
