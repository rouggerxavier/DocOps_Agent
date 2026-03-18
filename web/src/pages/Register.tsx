import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { BookOpen, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth/AuthProvider'

export function Register() {
  const { register, login } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name || !email || !password) {
      toast.error('Preencha todos os campos.')
      return
    }
    if (password.length < 8) {
      toast.error('Senha deve ter pelo menos 8 caracteres.')
      return
    }
    setLoading(true)
    try {
      await register(name, email, password)
      // Loga automaticamente após cadastro
      await login(email, password)
      toast.success('Conta criada com sucesso!')
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Erro ao criar conta.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-zinc-950 px-4">
      {/* Background gradient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 h-[500px] w-[500px] rounded-full bg-blue-700/20 blur-[120px]" />
        <div className="absolute -bottom-40 -right-32 h-[400px] w-[400px] rounded-full bg-violet-700/15 blur-[100px]" />
        <div className="absolute top-1/2 left-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-500/5 blur-[80px]" />
      </div>

      {/* Subtle dot grid texture */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'radial-gradient(circle, #a1a1aa 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      />

      <div className="relative w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-600/30">
            <BookOpen className="h-6 w-6 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold text-zinc-100">DocOps Agent</h1>
            <p className="mt-1 text-sm text-zinc-500">Crie sua conta</p>
          </div>
        </div>

        {/* Form card */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6 shadow-xl backdrop-blur-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-zinc-300">Nome</label>
              <Input
                type="text"
                placeholder="Seu nome"
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={loading}
                autoComplete="name"
                required
              />
            </div>
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
              <label className="block text-sm font-medium text-zinc-300">
                Senha <span className="text-zinc-600">(mín. 8 caracteres)</span>
              </label>
              <Input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="new-password"
                required
                minLength={8}
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Criar conta
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-zinc-500">
            Já tem conta?{' '}
            <Link to="/login" className="text-blue-400 hover:underline">
              Entrar
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
