import { Link } from 'react-router-dom'
import {
  BookOpen, MessageSquare, Layers, ListTodo, KanbanSquare,
  GraduationCap, Zap, FileText, StickyNote, CalendarDays,
  ArrowRight, Brain,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

const FEATURES = [
  {
    icon: MessageSquare,
    color: 'text-blue-400',
    bg: 'bg-blue-500/10 border-blue-500/20',
    title: 'Chat com RAG',
    desc: 'Converse com seus documentos usando recuperação semântica + BM25 híbrido. Respostas com citações rastreáveis.',
  },
  {
    icon: FileText,
    color: 'text-violet-400',
    bg: 'bg-violet-500/10 border-violet-500/20',
    title: 'Resumos Inteligentes',
    desc: 'Resumos breves ou profundos (deep) com pipeline multi-etapas, agrupamento por seção e verificação de grounding.',
  },
  {
    icon: Layers,
    color: 'text-amber-400',
    bg: 'bg-amber-500/10 border-amber-500/20',
    title: 'Flashcards',
    desc: 'Gere flashcards automáticos a partir dos seus documentos. Revisão espaçada integrada com agendamento.',
  },
  {
    icon: KanbanSquare,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10 border-emerald-500/20',
    title: 'Kanban de Leitura',
    desc: 'Organize seus documentos em Para Ler, Lendo e Lido. Análise de gaps identifica tópicos não cobertos.',
  },
  {
    icon: GraduationCap,
    color: 'text-pink-400',
    bg: 'bg-pink-500/10 border-pink-500/20',
    title: 'Plano de Estudos',
    desc: 'Gere um plano de estudos personalizado baseado nos seus documentos e objetivos de aprendizado.',
  },
  {
    icon: Brain,
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10 border-cyan-500/20',
    title: 'Pergunta do Dia',
    desc: 'Uma pergunta diária gerada por IA a partir dos seus documentos, com avaliação de resposta em tempo real.',
  },
  {
    icon: ListTodo,
    color: 'text-orange-400',
    bg: 'bg-orange-500/10 border-orange-500/20',
    title: 'Tarefas & Agenda',
    desc: 'Extraia tarefas acionáveis dos seus documentos automaticamente. Calendário integrado com lembretes.',
  },
  {
    icon: StickyNote,
    color: 'text-teal-400',
    bg: 'bg-teal-500/10 border-teal-500/20',
    title: 'Notas com Preview',
    desc: 'Editor de notas com preview Markdown em tempo real. Vinculadas ao contexto dos seus documentos.',
  },
  {
    icon: CalendarDays,
    color: 'text-indigo-400',
    bg: 'bg-indigo-500/10 border-indigo-500/20',
    title: 'Ingestão Múltipla',
    desc: 'PDF, Markdown, CSV, XLSX, texto colado, foto com OCR, URL de página web ou transcrição de YouTube.',
  },
]

const STEPS = [
  { n: '01', title: 'Insira seus documentos', desc: 'PDF, Markdown, texto, planilhas, fotos, URLs ou vídeos do YouTube são indexados no Chroma com embeddings semânticos.' },
  { n: '02', title: 'Converse e aprenda', desc: 'Faça perguntas, gere resumos, crie flashcards e planos de estudos — tudo fundamentado nos seus próprios materiais.' },
  { n: '03', title: 'Acompanhe o progresso', desc: 'Kanban de leitura, análise de gaps, revisão espaçada e pergunta diária mantêm seu aprendizado ativo e organizado.' },
]

export function Landing() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-60 -left-60 h-[700px] w-[700px] rounded-full bg-blue-700/15 blur-[140px]" />
        <div className="absolute top-1/3 -right-40 h-[500px] w-[500px] rounded-full bg-violet-700/10 blur-[120px]" />
        <div className="absolute -bottom-40 left-1/3 h-[400px] w-[400px] rounded-full bg-blue-500/8 blur-[100px]" />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{ backgroundImage: 'radial-gradient(circle, #a1a1aa 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />
      </div>

      {/* Header */}
      <header className="relative border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 shadow-lg shadow-blue-600/30">
              <BookOpen className="h-4 w-4 text-white" />
            </div>
            <span className="text-sm font-bold text-zinc-100">DocOps Agent</span>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login">
              <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">
                Entrar
              </Button>
            </Link>
            <Link to="/register">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-600/20">
                Criar conta
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24 pt-24 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-blue-800/50 bg-blue-950/40 px-4 py-1.5 text-xs text-blue-300 mb-8">
          <Zap className="h-3 w-3" />
          RAG Local · Gemini + ChromaDB
        </div>
        <h1 className="text-5xl font-extrabold tracking-tight text-zinc-50 sm:text-6xl">
          Seu assistente de
          <br />
          <span className="bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
            documentos local
          </span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-400 leading-relaxed">
          Indexe PDFs, vídeos do YouTube e páginas web. Converse com seu acervo, gere flashcards,
          planos de estudo e acompanhe seu aprendizado — tudo privado, rodando na sua máquina.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link to="/register">
            <Button size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-xl shadow-blue-600/25 gap-2 text-base px-8">
              Começar agora <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-base px-8">
              Já tenho conta
            </Button>
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-zinc-100">Tudo que você precisa para aprender</h2>
          <p className="mt-3 text-zinc-500">Ferramentas integradas que transformam seus documentos em conhecimento ativo.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => {
            const Icon = f.icon
            return (
              <div key={f.title} className={`rounded-xl border p-5 space-y-3 ${f.bg}`}>
                <div className="flex items-center gap-3">
                  <Icon className={`h-5 w-5 shrink-0 ${f.color}`} />
                  <h3 className="font-semibold text-zinc-100 text-sm">{f.title}</h3>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{f.desc}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* How it works */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-zinc-100">Como funciona</h2>
        </div>
        <div className="grid gap-8 md:grid-cols-3">
          {STEPS.map(s => (
            <div key={s.n} className="space-y-3">
              <div className="text-5xl font-black text-zinc-800">{s.n}</div>
              <h3 className="font-semibold text-zinc-100">{s.title}</h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA footer */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <div className="rounded-2xl border border-blue-800/30 bg-gradient-to-r from-blue-950/40 to-violet-950/30 p-12 text-center">
          <h2 className="text-3xl font-bold text-zinc-100 mb-4">Pronto para começar?</h2>
          <p className="text-zinc-400 mb-8 max-w-xl mx-auto">
            Crie sua conta gratuitamente e comece a indexar seus documentos agora mesmo.
          </p>
          <Link to="/register">
            <Button size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-xl shadow-blue-600/25 gap-2 text-base px-10">
              Criar conta grátis <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      <footer className="relative border-t border-zinc-800/60 py-6 text-center text-xs text-zinc-600">
        DocOps Agent · RAG Local · Gemini + ChromaDB
      </footer>
    </div>
  )
}
