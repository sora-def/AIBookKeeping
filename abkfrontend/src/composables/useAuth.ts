import { computed, ref } from 'vue'
import { clearToken, getToken, setToken } from '../api/http'
import { fetchMe, login as apiLogin, register as apiRegister } from '../api'
import type { User } from '../types'

const user = ref<User | null>(null)
const ready = ref(false)
const error = ref('')

export function useAuth() {
  const isLoggedIn = computed(() => !!user.value)

  async function bootstrap() {
    error.value = ''
    if (!getToken()) {
      ready.value = true
      return
    }
    try {
      user.value = await fetchMe()
    } catch {
      clearToken()
      user.value = null
    } finally {
      ready.value = true
    }
  }

  async function login(account: string, password: string) {
    error.value = ''
    const res = await apiLogin({ account, password })
    setToken(res.access_token)
    user.value = res.user
  }

  async function register(account: string, password: string, name: string, gender: string) {
    error.value = ''
    const res = await apiRegister({ account, password, name, gender })
    setToken(res.access_token)
    user.value = res.user
  }

  function logout() {
    clearToken()
    user.value = null
  }

  return { user, ready, error, isLoggedIn, bootstrap, login, register, logout }
}
