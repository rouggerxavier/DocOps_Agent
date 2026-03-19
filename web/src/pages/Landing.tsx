import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BookOpen, MessageSquare, Layers, ListTodo, KanbanSquare,
  GraduationCap, Zap, FileText, StickyNote, CalendarDays,
  ArrowRight, Brain, Play, Loader2, CheckCircle2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BackgroundWrapper } from '@/components/BackgroundWrapper'
import { ParticlesBackground } from '@/components/ParticlesBackground'
import { useAI, type AICategory } from '@/hooks/useAI'

// ── Animation language ────────────────────────────────────────────────────────
// Expo-out spring — same curve used by Linear, Vercel, Apple.
// Fast start, ultra-smooth settle. Applied globally for consistency.
const EASE = [0.16, 1, 0.3, 1] as const

// Shared viewport config for all whileInView triggers
const VIEWPORT = { once: true, margin: '-60px' } as const

// ── Data ─────────────────────────────────────────────────────────────────────

const CARD_STYLES: Record<AICategory, { icon: typeof ListTodo; color: string; border: string; bg: string }> = {
  tasks:       { icon: ListTodo,    color: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  flashcards:  { icon: Layers,      color: 'text-amber-400',  border: 'border-amber-500/30',  bg: 'bg-amber-500/10'  },
  schedule:    { icon: CalendarDays, color: 'text-indigo-400', border: 'border-indigo-500/30', bg: 'bg-indigo-500/10' },
  summary:     { icon: FileText,    color: 'text-violet-400', border: 'border-violet-500/30', bg: 'bg-violet-500/10' },
  suggestions: { icon: Zap,         color: 'text-cyan-400',   border: 'border-cyan-500/30',   bg: 'bg-cyan-500/10'   },
  general:     { icon: Brain,       color: 'text-blue-400',   border: 'border-blue-500/30',   bg: 'bg-blue-500/10'   },
}

const FEATURES = [
  { icon: MessageSquare, color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/20',    title: 'Chat com RAG',         desc: 'Converse com seus documentos usando recuperação semântica + BM25 híbrido. Respostas com citações rastreáveis.' },
  { icon: FileText,      color: 'text-violet-400',  bg: 'bg-violet-500/10 border-violet-500/20', title: 'Resumos Inteligentes', desc: 'Resumos breves ou profundos (deep) com pipeline multi-etapas, agrupamento por seção e verificação de grounding.' },
  { icon: Layers,        color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20',  title: 'Flashcards',           desc: 'Gere flashcards automáticos a partir dos seus documentos. Revisão espaçada integrada com agendamento.' },
  { icon: KanbanSquare,  color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', title: 'Kanban de Leitura',  desc: 'Organize seus documentos em Para Ler, Lendo e Lido. Análise de gaps identifica tópicos não cobertos.' },
  { icon: GraduationCap, color: 'text-pink-400',    bg: 'bg-pink-500/10 border-pink-500/20',    title: 'Plano de Estudos',     desc: 'Gere um plano de estudos personalizado baseado nos seus documentos e objetivos de aprendizado.' },
  { icon: Brain,         color: 'text-cyan-400',    bg: 'bg-cyan-500/10 border-cyan-500/20',    title: 'Pergunta do Dia',      desc: 'Uma pergunta diária gerada por IA a partir dos seus documentos, com avaliação de resposta em tempo real.' },
  { icon: ListTodo,      color: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/20', title: 'Tarefas & Agenda',    desc: 'Extraia tarefas acionáveis dos seus documentos automaticamente. Calendário integrado com lembretes.' },
  { icon: StickyNote,    color: 'text-teal-400',    bg: 'bg-teal-500/10 border-teal-500/20',    title: 'Notas com Preview',    desc: 'Editor de notas com preview Markdown em tempo real. Vinculadas ao contexto dos seus documentos.' },
  { icon: CalendarDays,  color: 'text-indigo-400',  bg: 'bg-indigo-500/10 border-indigo-500/20', title: 'Ingestão Múltipla',   desc: 'PDF, Markdown, CSV, XLSX, texto colado, foto com OCR, URL de página web ou transcrição de YouTube.' },
]

const STEPS = [
  { n: '01', title: 'Insira seus documentos', desc: 'PDF, Markdown, texto, planilhas, fotos, URLs ou vídeos do YouTube são indexados no Chroma com embeddings semânticos.' },
  { n: '02', title: 'Converse e aprenda',      desc: 'Faça perguntas, gere resumos, crie flashcards e planos de estudos — tudo fundamentado nos seus próprios materiais.' },
  { n: '03', title: 'Acompanhe o progresso',  desc: 'Kanban de leitura, análise de gaps, revisão espaçada e pergunta diária mantêm seu aprendizado ativo e organizado.' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export function Landing() {
  const [demoInput, setDemoInput] = useState('Organize meu estudo de Machine Learning')
  const ai = useAI()
  const demoState = ai.loading ? 'loading' : ai.result ? 'done' : 'idle'

  return (
    <BackgroundWrapper animatedLayer={<ParticlesBackground />}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
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
              <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">Entrar</Button>
            </Link>
            <Link to="/register">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-600/20">Criar conta</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-32 pt-28 text-center">

        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: EASE }}
          className="inline-flex items-center gap-2 rounded-full border border-blue-700/40 bg-blue-950/50 px-4 py-1.5 text-xs text-blue-300 mb-10 shadow-inner shadow-blue-900/30"
        >
          <Zap className="h-3 w-3" />
          RAG Local · Gemini + ChromaDB
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.85, delay: 0.1, ease: EASE }}
          className="text-6xl font-black tracking-tight text-zinc-50 sm:text-7xl lg:text-8xl leading-[1.05]"
        >
          Transforme documentos
          <br />
          <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            em conhecimento
          </span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.85, delay: 0.22, ease: EASE }}
          className="mx-auto mt-8 max-w-2xl text-xl text-zinc-400 leading-relaxed"
        >
          Indexe PDFs, vídeos do YouTube e páginas web. Converse com seu acervo, gere flashcards,
          planos de estudo e acompanhe seu aprendizado — tudo privado, rodando na sua máquina.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75, delay: 0.38, ease: EASE }}
          className="mt-12 flex flex-wrap items-center justify-center gap-4"
        >
          <Link to="/register">
            <Button size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-2xl shadow-blue-600/30 gap-2 text-base px-10 h-12">
              Começar agora <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800/80 hover:border-zinc-600 text-base px-10 h-12">
              Já tenho conta
            </Button>
          </Link>
        </motion.div>
      </section>

      {/* ── Features ────────────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 className="text-3xl font-bold text-zinc-100">Tudo que você precisa para aprender</h2>
          <p className="mt-3 text-zinc-500">Ferramentas integradas que transformam seus documentos em conhecimento ativo.</p>
        </motion.div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => {
            const Icon = f.icon
            // Diagonal stagger: row step 0.08 + column step 0.035 — wave from top-left to bottom-right
            const row = Math.floor(i / 3)
            const col = i % 3
            return (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 28 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.65, delay: row * 0.08 + col * 0.035, ease: EASE }}
                whileHover={{ scale: 1.025, transition: { duration: 0.4, ease: EASE } }}
                className={`rounded-xl border p-5 space-y-3 cursor-pointer backdrop-blur-sm ${f.bg} transition-shadow duration-300 hover:shadow-lg hover:shadow-black/40`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`h-5 w-5 shrink-0 ${f.color}`} />
                  <h3 className="font-semibold text-zinc-100 text-sm">{f.title}</h3>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{f.desc}</p>
              </motion.div>
            )
          })}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 className="text-3xl font-bold text-zinc-100">Como funciona</h2>
        </motion.div>

        <div className="grid gap-8 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.7, delay: i * 0.1, ease: EASE }}
              className="space-y-3"
            >
              <div className="text-5xl font-black text-zinc-800">{s.n}</div>
              <h3 className="font-semibold text-zinc-100">{s.title}</h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── IA em ação ──────────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-28">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 className="text-3xl font-bold text-zinc-100">IA em ação</h2>
          <p className="mt-3 text-zinc-500">Veja como a IA transforma um comando simples em ações concretas.</p>
        </motion.div>

        {/* Input + button */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.65, delay: 0.12, ease: EASE }}
          className="mx-auto flex max-w-2xl items-center gap-3"
        >
          <input
            type="text"
            value={demoInput}
            onChange={e => { setDemoInput(e.target.value); if (ai.result) ai.reset() }}
            placeholder="Ex: Organize meu estudo de Machine Learning"
            className="flex-1 rounded-xl border border-zinc-700/60 bg-zinc-900/80 px-5 py-3.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none backdrop-blur-sm transition-colors focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30"
            disabled={demoState === 'loading'}
          />
          <Button
            onClick={() => ai.run(demoInput)}
            disabled={demoState === 'loading' || !demoInput.trim()}
            className="h-[50px] gap-2 rounded-xl bg-blue-600 px-6 text-sm font-medium shadow-lg shadow-blue-600/20 hover:bg-blue-500 disabled:opacity-50"
          >
            {demoState === 'loading' ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Processando...</>
            ) : demoState === 'done' ? (
              <><CheckCircle2 className="h-4 w-4" /> Concluído</>
            ) : (
              <><Play className="h-4 w-4" /> Executar</>
            )}
          </Button>
        </motion.div>

        {/* Result cards */}
        <div className="mx-auto mt-10 grid max-w-4xl gap-5 md:grid-cols-3">
          <AnimatePresence>
            {ai.result?.cards.map((card, i) => {
              const style = CARD_STYLES[card.category]
              const Icon = style.icon
              return (
                <motion.div
                  key={`card-${i}`}
                  initial={{ opacity: 0, y: 32, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.98, transition: { duration: 0.25, ease: EASE } }}
                  transition={{ duration: 0.6, delay: i * 0.1, ease: EASE }}
                  className={`rounded-xl border ${style.border} ${style.bg} p-5 backdrop-blur-sm`}
                >
                  <div className="mb-3 flex items-center gap-2.5">
                    <Icon className={`h-5 w-5 ${style.color}`} />
                    <h4 className="text-sm font-semibold text-zinc-100">{card.title}</h4>
                  </div>
                  <ul className="space-y-2">
                    {card.items.map((item, j) => (
                      <motion.li
                        key={item}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.45, delay: i * 0.1 + j * 0.06 + 0.18, ease: EASE }}
                        className="flex items-start gap-2 text-xs text-zinc-400 leading-relaxed"
                      >
                        <CheckCircle2 className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${style.color}`} />
                        {item}
                      </motion.li>
                    ))}
                  </ul>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>

        {demoState === 'done' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.55, ease: EASE }}
            className="mt-6 text-center"
          >
            <button onClick={ai.reset} className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">
              Resetar demonstração
            </button>
          </motion.div>
        )}
      </section>

      {/* ── CTA footer ──────────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.75, ease: EASE }}
          className="rounded-2xl border border-blue-800/30 bg-gradient-to-r from-blue-950/40 to-violet-950/30 p-12 text-center"
        >
          <h2 className="text-3xl font-bold text-zinc-100 mb-4">Pronto para começar?</h2>
          <p className="text-zinc-400 mb-8 max-w-xl mx-auto">
            Crie sua conta gratuitamente e comece a indexar seus documentos agora mesmo.
          </p>
          <Link to="/register">
            <Button size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-xl shadow-blue-600/25 gap-2 text-base px-10">
              Criar conta grátis <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </motion.div>
      </section>

      <footer className="relative border-t border-zinc-800/60 py-6 text-center text-xs text-zinc-600">
        DocOps Agent · RAG Local · Gemini + ChromaDB
      </footer>
    </BackgroundWrapper>
  )
}
