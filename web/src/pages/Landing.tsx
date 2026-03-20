import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence, MotionConfig } from 'framer-motion'
import {
  BookOpen, MessageSquare, Layers, ListTodo, KanbanSquare,
  GraduationCap, Zap, FileText, CalendarDays,
  ArrowRight, Brain, Play, Loader2, CheckCircle2,
  Shield, Clock, FileStack, Lock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BackgroundWrapper } from '@/components/BackgroundWrapper'
import { ParticlesBackground } from '@/components/ParticlesBackground'
import { useAI, type AICard, type AICategory } from '@/hooks/useAI'
import { getDynamicDelay, useDynamicDelay } from '@/lib/stagger'

// ── Animation constants ───────────────────────────────────────────────────────

const EASE     = [0.16, 1, 0.3, 1] as const  // expo-out spring — used globally
const VIEWPORT = { once: true, margin: '-60px' } as const

// ── Static data ───────────────────────────────────────────────────────────────

const CARD_STYLES: Record<AICategory, { icon: typeof ListTodo; color: string; border: string; bg: string }> = {
  tasks:       { icon: ListTodo,    color: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  flashcards:  { icon: Layers,      color: 'text-amber-400',  border: 'border-amber-500/30',  bg: 'bg-amber-500/10'  },
  schedule:    { icon: CalendarDays, color: 'text-indigo-400', border: 'border-indigo-500/30', bg: 'bg-indigo-500/10' },
  summary:     { icon: FileText,    color: 'text-violet-400', border: 'border-violet-500/30', bg: 'bg-violet-500/10' },
  suggestions: { icon: Zap,         color: 'text-cyan-400',   border: 'border-cyan-500/30',   bg: 'bg-cyan-500/10'   },
  general:     { icon: Brain,       color: 'text-blue-400',   border: 'border-blue-500/30',   bg: 'bg-blue-500/10'   },
}

const FEATURES = [
  { icon: MessageSquare, color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/20',     title: 'Chat com Documentos',  desc: 'Faça perguntas sobre qualquer documento e receba respostas precisas com citações. A IA encontra a informação — você só pergunta.' },
  { icon: FileText,      color: 'text-violet-400',  bg: 'bg-violet-500/10 border-violet-500/20',  title: 'Resumos Inteligentes',desc: 'Gere resumos breves ou aprofundados de qualquer documento. A IA analisa seção por seção e entrega uma visão estruturada.' },
  { icon: Layers,        color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20',   title: 'Flashcards & Revisão', desc: 'Flashcards gerados automaticamente a partir dos seus materiais. Revisão espaçada com agendamento para fixar o conteúdo.' },
  { icon: GraduationCap, color: 'text-pink-400',    bg: 'bg-pink-500/10 border-pink-500/20',     title: 'Plano de Estudos',     desc: 'Plano personalizado com sessões diárias, tarefas por tópico e cronograma no calendário. Estude no seu ritmo.' },
  { icon: KanbanSquare,  color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20',title: 'Kanban de Leitura',   desc: 'Organize seus documentos em Para Ler, Lendo e Lido. Veja quais tópicos você já cobriu e o que falta estudar.' },
  { icon: CalendarDays,  color: 'text-indigo-400',  bg: 'bg-indigo-500/10 border-indigo-500/20', title: 'Qualquer Formato',     desc: 'PDF, Markdown, planilhas, texto colado, foto com OCR, URL de página web ou vídeo do YouTube. Tudo vira material de estudo.' },
]

const STEPS = [
  { n: '01', title: 'Envie seus materiais',   desc: 'Faça upload de PDFs, planilhas, textos, fotos, URLs ou vídeos do YouTube. A IA lê e organiza tudo automaticamente.' },
  { n: '02', title: 'Pergunte e aprenda',      desc: 'Converse com seus documentos, gere resumos, crie flashcards e planos de estudo — cada resposta cita a fonte original.' },
  { n: '03', title: 'Acompanhe seu progresso', desc: 'Quadro de leitura, revisão espaçada e identificação de lacunas mantêm seu aprendizado ativo e organizado.' },
]

const METRICS = [
  { icon: FileStack, value: '10+',  label: 'formatos aceitos',        desc: 'PDF, Markdown, CSV, XLSX, imagens, URLs, YouTube' },
  { icon: Clock,     value: '< 2s', label: 'tempo de resposta',       desc: 'Busca inteligente que cruza seus documentos em segundos' },
  { icon: Shield,    value: '100%', label: 'privado e local',         desc: 'Seus dados nunca saem da sua máquina' },
]

const FOOTER_LINKS = {
  Produto: [
    { label: 'Chat com Documentos', href: '#recursos' },
    { label: 'Resumos Inteligentes', href: '#recursos' },
    { label: 'Plano de Estudos', href: '#recursos' },
    { label: 'Kanban de Leitura', href: '#recursos' },
  ],
  Recursos: [
    { label: 'Como funciona', href: '#como-funciona' },
    { label: 'Demo interativa', href: '#demo' },
    { label: 'Documentação', href: 'https://github.com/DocOps-Agent/DocOps_Agent', external: true },
  ],
  Legal: [
    { label: 'Termos de uso', href: '#' },
    { label: 'Privacidade', href: '#' },
    { label: 'Licença MIT', href: 'https://github.com/DocOps-Agent/DocOps_Agent/blob/main/LICENSE', external: true },
  ],
}

function scrollToSection(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Sub-components (needed so useDynamicDelay can be called per-element) ──────

function FeatureCard({ feature, index }: { feature: typeof FEATURES[0]; index: number }) {
  const [ref, delay] = useDynamicDelay(index)
  const Icon = feature.icon
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.65, delay, ease: EASE }}
      className={`group rounded-xl border p-5 space-y-3 backdrop-blur-sm ${feature.bg} transition-all duration-300 hover:shadow-lg hover:shadow-black/30 hover:border-opacity-60 hover:-translate-y-0.5`}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-800/80 transition-colors duration-300 group-hover:bg-zinc-700/80">
          <Icon className={`h-4 w-4 shrink-0 ${feature.color}`} aria-hidden="true" />
        </div>
        <h3 className="font-semibold text-zinc-100 text-sm">{feature.title}</h3>
      </div>
      <p className="text-[13px] text-zinc-400 leading-relaxed">{feature.desc}</p>
    </motion.div>
  )
}

function StepItem({ step, index }: { step: typeof STEPS[0]; index: number }) {
  const [ref, delay] = useDynamicDelay(index)
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.7, delay, ease: EASE }}
      className="space-y-3"
    >
      <div className="text-5xl font-black bg-gradient-to-b from-zinc-600 to-zinc-800 bg-clip-text text-transparent">{step.n}</div>
      <h3 className="font-semibold text-zinc-100">{step.title}</h3>
      <p className="text-sm text-zinc-400 leading-relaxed">{step.desc}</p>
    </motion.div>
  )
}

function ResultCard({ card, index }: { card: AICard; index: number }) {
  const [ref, cardDelay] = useDynamicDelay(index)
  const style = CARD_STYLES[card.category]
  const Icon = style.icon
  return (
    <motion.div
      ref={ref}
      key={`card-${index}`}
      initial={{ opacity: 0, y: 32, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.98, transition: { duration: 0.25, ease: EASE } }}
      transition={{ duration: 0.6, delay: cardDelay, ease: EASE }}
      className={`rounded-xl border ${style.border} ${style.bg} p-5 backdrop-blur-sm`}
    >
      <div className="mb-3 flex items-center gap-2.5">
        <Icon className={`h-5 w-5 ${style.color}`} aria-hidden="true" />
        <h3 className="text-sm font-semibold text-zinc-100">{card.title}</h3>
      </div>
      <ul className="space-y-2">
        {card.items.map((item, j) => (
          <motion.li
            key={item}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            // Items stagger after their card's entrance — cardDelay anchors the sequence
            transition={{ duration: 0.45, delay: cardDelay + getDynamicDelay(j) * 0.6 + 0.1, ease: EASE }}
            className="flex items-start gap-2 text-xs text-zinc-400 leading-relaxed"
          >
            <CheckCircle2 className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${style.color}`} aria-hidden="true" />
            {item}
          </motion.li>
        ))}
      </ul>
    </motion.div>
  )
}

// ── Page component ────────────────────────────────────────────────────────────

export function Landing() {
  const [demoInput, setDemoInput] = useState('Organize meu estudo de Machine Learning')
  const ai = useAI()
  const demoState = ai.loading ? 'loading' : ai.result ? 'done' : 'idle'

  // Auto-populate demo with mock results so visitors see value immediately
  const autoTriggered = useCallback(() => {
    if (!ai.result && !ai.loading) ai.run(demoInput)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { autoTriggered() }, [autoTriggered])

  return (
    <MotionConfig reducedMotion="user">
    <BackgroundWrapper animatedLayer={<ParticlesBackground />}>

      {/* ── Skip to content (a11y) ────────────────────────────────────────── */}
      <a href="#content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-sm focus:text-white focus:outline-none">
        Pular para o conteúdo
      </a>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <header className="relative border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 shadow-lg shadow-blue-600/30">
              <BookOpen className="h-4 w-4 text-white" aria-hidden="true" />
            </div>
            <span className="text-sm font-bold text-zinc-100">DocOps Agent</span>
          </div>
          <nav className="hidden items-center gap-6 sm:flex" aria-label="Navegação principal">
            {(['recursos', 'como-funciona', 'demo'] as const).map((id) => (
              <button
                key={id}
                onClick={() => scrollToSection(id)}
                className="relative text-sm text-zinc-400 transition-colors hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:rounded-sm after:absolute after:bottom-[-4px] after:left-0 after:h-[1.5px] after:w-0 after:bg-blue-400 after:transition-all after:duration-300 hover:after:w-full"
              >
                {id === 'recursos' ? 'Recursos' : id === 'como-funciona' ? 'Como funciona' : 'Demo'}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Button asChild variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">
              <Link to="/login">Entrar</Link>
            </Button>
            <Button asChild size="sm" className="bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-600/20">
              <Link to="/register">Criar conta</Link>
            </Button>
          </div>
        </div>
      </header>

      <main id="content">

      {/* ── Hero ─────────────────────────────────────────────────────────────
          Above the fold — uses getDynamicDelay(i) directly (no DOM measurement
          needed; Y position is always ~0). Sub-linear spacing means Badge→H1
          has the largest gap, creating impact before the content arrives. */}
      <section className="relative mx-auto max-w-6xl px-6 pb-32 pt-28 text-center" aria-label="Hero">

        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: getDynamicDelay(0), ease: EASE }}
          className="inline-flex items-center gap-2 rounded-full border border-amber-600/30 bg-amber-950/40 px-4 py-1.5 text-xs text-amber-300 mb-10 shadow-inner shadow-amber-900/20"
        >
          <Shield className="h-3 w-3" aria-hidden="true" />
          Assistente de estudos com IA · Privado e local
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.85, delay: getDynamicDelay(1), ease: EASE }}
          className="text-[2.75rem] font-black tracking-tight text-zinc-50 sm:text-6xl lg:text-7xl xl:text-8xl leading-[1.08]"
        >
          Seus documentos
          <br />
          <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            já têm as respostas
          </span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.85, delay: getDynamicDelay(2), ease: EASE }}
          className="mx-auto mt-8 max-w-2xl text-lg sm:text-xl text-zinc-300 leading-relaxed"
        >
          Envie PDFs, vídeos ou páginas web e converse com eles. Resumos, flashcards
          e planos de estudo gerados pela IA — tudo rodando na sua máquina, 100% privado.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75, delay: getDynamicDelay(3), ease: EASE }}
          className="mt-12 flex flex-wrap items-center justify-center gap-4"
        >
          <Button asChild size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-2xl shadow-blue-600/30 gap-2 text-base px-10 h-12 transition-all duration-300 hover:shadow-blue-500/40 hover:scale-[1.02]">
            <Link to="/register">
              Criar conta grátis <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800/80 hover:border-zinc-600 text-base px-10 h-12 transition-all duration-300 hover:scale-[1.02]">
            <Link to="/login">
              Já tenho conta
            </Link>
          </Button>
        </motion.div>

        {/* Product mockup */}
        <motion.div
          initial={{ opacity: 0, y: 50, rotateX: 8, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, rotateX: 0, scale: 1 }}
          transition={{ duration: 1.2, delay: getDynamicDelay(4) + 0.15, ease: EASE }}
          className="mx-auto mt-20 max-w-5xl"
          style={{ perspective: 1200 }}
        >
          <div className="rounded-xl border border-zinc-700/40 bg-zinc-900/60 shadow-[0_20px_80px_-20px_rgba(59,130,246,0.15),0_8px_32px_-8px_rgba(0,0,0,0.6)] backdrop-blur-sm overflow-hidden">
            {/* Browser chrome */}
            <div className="flex items-center gap-2 border-b border-zinc-800/60 px-4 py-2.5">
              <div className="flex gap-1.5">
                <div className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
                <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/60" />
                <div className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
              </div>
              <div className="ml-3 flex-1 rounded-md bg-zinc-800/80 px-3 py-1 text-[11px] text-zinc-500 font-mono">
                docops-agent.vercel.app/dashboard
              </div>
            </div>
            {/* Screenshot */}
            <img
              src="/dashboard-preview.png"
              alt="Captura de tela do painel do DocOps Agent mostrando documentos, chat e ferramentas de estudo"
              className="w-full"
              loading="lazy"
              decoding="async"
              width={1440}
              height={900}
            />
          </div>
        </motion.div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────────────
          Each FeatureCard measures its own offsetTop so Y-deeper cards get
          a slightly longer delay — matches the natural scan order. */}
      <section id="recursos" className="relative mx-auto max-w-6xl px-6 pb-24 scroll-mt-20" aria-labelledby="recursos-heading">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 id="recursos-heading" className="text-3xl font-bold text-zinc-100">Um assistente completo de estudos</h2>
          <p className="mt-3 text-zinc-500">Da leitura à revisão — cada ferramenta trabalha com os seus materiais.</p>
        </motion.div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => <FeatureCard key={f.title} feature={f} index={i} />)}
        </div>
      </section>

      {/* ── Social proof — product metrics ──────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24" aria-label="Métricas do produto">
        <div className="grid gap-6 sm:grid-cols-3">
          {METRICS.map((m, i) => {
            const Icon = m.icon
            return (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.65, delay: getDynamicDelay(i), ease: EASE }}
                className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-6 text-center backdrop-blur-sm transition-colors duration-300 hover:border-zinc-700/60"
              >
                <Icon className="mx-auto mb-3 h-5 w-5 text-zinc-400" aria-hidden="true" />
                <div className="text-3xl font-black text-amber-400">{m.value}</div>
                <div className="mt-1 text-sm font-semibold text-zinc-200">{m.label}</div>
                <p className="mt-2 text-xs text-zinc-500 leading-relaxed">{m.desc}</p>
              </motion.div>
            )
          })}
        </div>
      </section>

      {/* ── Section divider ──────────────────────────────────────────────── */}
      <div className="mx-auto max-w-xs">
        <div className="h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent" />
      </div>

      {/* ── How it works ──────────────────────────────────────────────────── */}
      <section id="como-funciona" className="relative mx-auto max-w-6xl px-6 pb-24 pt-24 scroll-mt-20" aria-labelledby="como-funciona-heading">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 id="como-funciona-heading" className="text-3xl font-bold text-zinc-100">Como funciona</h2>
        </motion.div>

        <div className="grid gap-8 md:grid-cols-3">
          {STEPS.map((s, i) => <StepItem key={s.n} step={s} index={i} />)}
        </div>
      </section>

      {/* ── Section divider ──────────────────────────────────────────────── */}
      <div className="mx-auto max-w-xs">
        <div className="h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent" />
      </div>

      {/* ── IA em ação ────────────────────────────────────────────────────── */}
      <section id="demo" className="relative mx-auto max-w-6xl px-6 pb-28 pt-24 scroll-mt-20" aria-labelledby="demo-heading">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.7, ease: EASE }}
          className="mb-12 text-center"
        >
          <h2 id="demo-heading" className="text-3xl font-bold text-zinc-100">Veja funcionando</h2>
          <p className="mt-3 text-zinc-500">Digite um objetivo de estudo e veja o que a IA gera em segundos.</p>
        </motion.div>

        {/* Input + button */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.65, delay: getDynamicDelay(0), ease: EASE }}
          className="mx-auto flex max-w-2xl items-center gap-3"
        >
          <input
            type="text"
            value={demoInput}
            onChange={e => { setDemoInput(e.target.value); if (ai.result) ai.reset() }}
            placeholder="Ex: Organize meu estudo de Machine Learning"
            aria-label="Comando para a demonstração de IA"
            className="flex-1 rounded-xl border border-zinc-700/60 bg-zinc-900/80 px-5 py-3.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none backdrop-blur-sm transition-colors focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30"
            disabled={demoState === 'loading'}
          />
          <Button
            onClick={() => ai.run(demoInput)}
            disabled={demoState === 'loading' || !demoInput.trim()}
            className="h-[50px] gap-2 rounded-xl bg-blue-600 px-6 text-sm font-medium shadow-lg shadow-blue-600/20 hover:bg-blue-500 disabled:opacity-50"
          >
            {demoState === 'loading' ? (
              <><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Processando...</>
            ) : demoState === 'done' ? (
              <><CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Concluído</>
            ) : (
              <><Play className="h-4 w-4" aria-hidden="true" /> Executar</>
            )}
          </Button>
        </motion.div>

        {/* Result cards — each measures its own Y at mount */}
        <div className="mx-auto mt-10 grid max-w-4xl gap-5 md:grid-cols-3">
          <AnimatePresence>
            {ai.result?.cards.map((card, i) => (
              <ResultCard key={`card-${i}`} card={card} index={i} />
            ))}
          </AnimatePresence>
        </div>

        {demoState === 'done' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.55, ease: EASE }}
            className="mt-6 text-center"
          >
            <button onClick={ai.reset} className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:rounded-sm">
              Resetar demonstração
            </button>
          </motion.div>
        )}
      </section>

      {/* ── CTA footer ───────────────────────────────────────────────────── */}
      <section className="relative mx-auto max-w-6xl px-6 pb-24" aria-label="Chamada para ação">
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={VIEWPORT}
          transition={{ duration: 0.75, ease: EASE }}
          className="rounded-2xl border border-blue-700/40 bg-gradient-to-br from-blue-950/60 via-indigo-950/40 to-violet-950/50 p-12 text-center shadow-2xl shadow-blue-950/40"
        >
          <h2 className="text-3xl font-bold text-zinc-100 mb-4">Comece a estudar de verdade</h2>
          <p className="text-zinc-400 mb-8 max-w-xl mx-auto">
            Crie sua conta, envie seus materiais e deixe a IA organizar o resto. Em minutos, não em horas.
          </p>
          <Button asChild size="lg" className="bg-blue-600 hover:bg-blue-500 shadow-xl shadow-blue-500/30 gap-2 text-base px-10 h-12 transition-all duration-300 hover:shadow-blue-500/40 hover:scale-[1.02]">
            <Link to="/register">
              Criar conta grátis <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-zinc-500">
            <Lock className="h-3 w-3" aria-hidden="true" /> Gratuito · Sem cartão de crédito
          </p>
        </motion.div>
      </section>

      </main>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="relative border-t border-zinc-800/60 bg-zinc-950/80" role="contentinfo">
        <div className="mx-auto max-w-6xl px-6 py-12">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {/* Brand column */}
            <div className="space-y-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
                  <BookOpen className="h-3.5 w-3.5 text-white" aria-hidden="true" />
                </div>
                <span className="text-sm font-bold text-zinc-100">DocOps Agent</span>
              </div>
              <p className="text-xs text-zinc-500 leading-relaxed max-w-[220px]">
                Seus documentos, organizados e prontos para estudo — com IA local e privada.
              </p>
            </div>

            {/* Link columns */}
            {Object.entries(FOOTER_LINKS).map(([title, links]) => (
              <div key={title}>
                <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">{title}</h4>
                <ul className="space-y-2">
                  {links.map((link) => (
                    <li key={link.label}>
                      {'external' in link && link.external ? (
                        <a href={link.href} target="_blank" rel="noopener noreferrer" className="text-xs text-zinc-500 transition-colors hover:text-zinc-300">
                          {link.label}
                        </a>
                      ) : link.href.startsWith('#') ? (
                        <button
                          onClick={() => scrollToSection(link.href.slice(1))}
                          className="text-xs text-zinc-500 transition-colors hover:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:rounded-sm"
                        >
                          {link.label}
                        </button>
                      ) : (
                        <a href={link.href} className="text-xs text-zinc-500 transition-colors hover:text-zinc-300">
                          {link.label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Bottom bar */}
          <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-zinc-800/60 pt-6 sm:flex-row">
            <p className="text-xs text-zinc-600">&copy; {new Date().getFullYear()} DocOps Agent. Todos os direitos reservados.</p>
            <p className="text-xs text-zinc-700">Feito com IA local · Busca semântica + vetorial</p>
          </div>
        </div>
      </footer>
    </BackgroundWrapper>
    </MotionConfig>
  )
}
