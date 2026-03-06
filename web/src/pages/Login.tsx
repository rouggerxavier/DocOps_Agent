import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { BookOpen, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth/AuthProvider'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !password) {
      toast.error('Preencha e-mail e senha.')
      return
    }
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Credenciais inválidas.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600">
            <BookOpen className="h-6 w-6 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold text-zinc-100">DocOps Agent</h1>
            <p className="mt-1 text-sm text-zinc-500">Faça login para continuar</p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-zinc-300">E-mail</label>
            <Input
              type="email"
              placeholder="voce@exemplo.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              disabled={loading}
              autoComplete="email"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium text-zinc-300">Senha</label>
            <Input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
              required
            />
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Entrar
          </Button>
        </form>

        <p className="text-center text-sm text-zinc-500">
          Não tem conta?{' '}
          <Link to="/register" className="text-blue-400 hover:underline">
            Criar conta
          </Link>
        </p>
      </div>
    </div>
  )
}
