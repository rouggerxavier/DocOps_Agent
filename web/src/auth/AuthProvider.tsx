import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

// ── Tipos ──────────────────────────────────────────────────────────────────────

interface AuthUser {
  id: number
  name: string
  email: string
  created_at: string
}

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: (accessToken: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => void
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null)

const TOKEN_KEY = 'docops_token'

// Inicializa o header Authorization imediatamente (antes de qualquer render/fetch)
const _initialToken = localStorage.getItem(TOKEN_KEY)
if (_initialToken) {
  api.defaults.headers.common['Authorization'] = `Bearer ${_initialToken}`
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  // Injeta/remove o header Authorization globalmente
  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete api.defaults.headers.common['Authorization']
    }
  }, [token])

  // Ao montar ou quando o token mudar, busca os dados do usuário
  useEffect(() => {
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    setLoading(true)
    api
      .get<AuthUser>('/api/auth/me')
      .then(r => setUser(r.data))
      .catch(() => {
        // Token inválido ou expirado — limpa estado
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  // Interceptor global: se qualquer chamada retornar 401, desloga
  useEffect(() => {
    const id = api.interceptors.response.use(
      r => r,
      err => {
        if (err?.response?.status === 401) {
          localStorage.removeItem(TOKEN_KEY)
          setToken(null)
          setUser(null)
          queryClient.clear()
        }
        return Promise.reject(err)
      }
    )
    return () => api.interceptors.response.eject(id)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const resp = await api.post<{ access_token: string; token_type: string }>(
      '/api/auth/login',
      { email, password }
    )
    const t = resp.data.access_token
    localStorage.setItem(TOKEN_KEY, t)
    setToken(t)
  }, [])

  const loginWithGoogle = useCallback(async (accessToken: string) => {
    const resp = await api.post<{ access_token: string; token_type: string }>(
      '/api/auth/google',
      { access_token: accessToken }
    )
    const t = resp.data.access_token
    localStorage.setItem(TOKEN_KEY, t)
    setToken(t)
  }, [])

  const register = useCallback(async (name: string, email: string, password: string) => {
    await api.post('/api/auth/register', { name, email, password })
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    queryClient.clear()
  }, [queryClient])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, loginWithGoogle, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>')
  return ctx
}
