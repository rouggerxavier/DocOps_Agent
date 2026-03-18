import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import {
  BookOpen, Loader2, MessageSquare, Layers, KanbanSquare,
  GraduationCap, Brain, FileText,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth/AuthProvider'

const HIGHLIGHTS = [
  { icon: MessageSquare, color: 'text-blue-400', title: 'Chat com RAG', desc: 'Pergunte aos seus documentos com citações.' },
  { icon: FileText, color: 'text-violet-400', title: 'Resumos Deep', desc: 'Pipeline multi-etapas com grounding semântico.' },
  { icon: Layers, color: 'text-amber-400', title: 'Flashcards', desc: 'Gerados automaticamente com revisão espaçada.' },
  { icon: KanbanSquare, color: 'text-emerald-400', title: 'Kanban de Leitura', desc: 'Organize e acompanhe sua leitura.' },
  { icon: GraduationCap, color: 'text-pink-400', title: 'Plano de Estudos', desc: 'Roadmap personalizado pelos seus materiais.' },
  { icon: Brain, color: 'text-cyan-400', title: 'Pergunta do Dia', desc: 'IA avalia suas respostas em tempo real.' },
]

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
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Credenciais inválidas.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 h-[600px] w-[600px] rounded-full bg-blue-700/20 blur-[140px]" />
        <div className="absolute -bottom-40 -right-32 h-[500px] w-[500px] rounded-full bg-violet-700/15 blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{ backgroundImage: 'radial-gradient(circle, #a1a1aa 1px, transparent 1px)', backgroundSize: '28px 28px' }}
        />
      </div>

      {/* Login section — full viewport height */}
      <div className="relative flex min-h-screen flex-col items-center justify-center px-4 py-16">
        <div className="w-full max-w-sm space-y-8">
          {/* Logo */}
          <div className="flex flex-col items-center gap-3">
            <Link to="/" className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-600/30 hover:bg-blue-500 transition-colors">
              <BookOpen className="h-6 w-6 text-white" />
            </Link>
            <div className="text-center">
              <h1 className="text-xl font-bold text-zinc-100">DocOps Agent</h1>
              <p className="mt-1 text-sm text-zinc-500">Faça login para continuar</p>
            </div>
          </div>

          {/* Form */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6 shadow-xl backdrop-blur-sm">
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
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Entrar
              </Button>
            </form>

            <p className="mt-5 text-center text-sm text-zinc-500">
              Não tem conta?{' '}
              <Link to="/register" className="text-blue-400 hover:underline">
                Criar conta
              </Link>
            </p>
          </div>

          <p className="text-center text-xs text-zinc-700">
            <Link to="/" className="hover:text-zinc-500 transition-colors">← Voltar ao início</Link>
          </p>
        </div>
      </div>

      {/* Features section — below the fold */}
      <div className="relative border-t border-zinc-800/60 bg-zinc-900/30 px-6 py-20">
        <div className="mx-auto max-w-4xl">
          <div className="mb-12 text-center">
            <h2 className="text-2xl font-bold text-zinc-100">O que você encontrará aqui</h2>
            <p className="mt-2 text-sm text-zinc-500">Ferramentas integradas para transformar documentos em conhecimento ativo.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {HIGHLIGHTS.map(h => {
              const Icon = h.icon
              return (
                <div key={h.title} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 shrink-0 ${h.color}`} />
                    <span className="text-sm font-semibold text-zinc-200">{h.title}</span>
                  </div>
                  <p className="text-xs text-zinc-500 leading-relaxed">{h.desc}</p>
                </div>
              )
            })}
          </div>

          <div className="mt-16 rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-6">
            <h3 className="text-sm font-semibold text-zinc-300 mb-4">Como funciona</h3>
            <div className="grid gap-4 sm:grid-cols-3 text-xs text-zinc-500">
              <div className="space-y-1">
                <p className="text-zinc-400 font-medium">1. Insira seus materiais</p>
                <p>PDF, Markdown, texto, planilha, foto com OCR, URL ou vídeo do YouTube — tudo indexado localmente no ChromaDB.</p>
              </div>
              <div className="space-y-1">
                <p className="text-zinc-400 font-medium">2. Converse e estude</p>
                <p>Faça perguntas, peça resumos com citações, gere flashcards e planos de estudo baseados nos seus próprios documentos.</p>
              </div>
              <div className="space-y-1">
                <p className="text-zinc-400 font-medium">3. Acompanhe o aprendizado</p>
                <p>Kanban de leitura, análise de gaps, revisão espaçada e pergunta diária com avaliação por IA mantêm você progredindo.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <footer className="relative border-t border-zinc-800/60 py-6 text-center text-xs text-zinc-700">
        DocOps Agent · RAG Local · Gemini + ChromaDB
      </footer>
    </div>
  )
}
