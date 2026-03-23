import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence, MotionConfig } from 'framer-motion'
import {
  BookOpen,
  MessageSquare,
  Layers,
  ListTodo,
  KanbanSquare,
  GraduationCap,
  Zap,
  FileText,
  CalendarDays,
  ArrowRight,
  Brain,
  Play,
  Loader2,
  CheckCircle2,
  Shield,
  Clock,
  FileStack,
  Lock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BackgroundWrapper } from '@/components/BackgroundWrapper'
import { useAI, type AICard, type AICategory } from '@/hooks/useAI'
import { getDynamicDelay, useDynamicDelay } from '@/lib/stagger'

const EASE = [0.2, 0.8, 0.2, 1] as const
const VIEWPORT = { once: true, margin: '-40px' } as const

const CARD_STYLES: Record<AICategory, { icon: typeof ListTodo; label: string }> = {
  tasks: { icon: ListTodo, label: 'Plano de execução' },
  flashcards: { icon: Layers, label: 'Revisão ativa' },
  schedule: { icon: CalendarDays, label: 'Rotina recomendada' },
  summary: { icon: FileText, label: 'Resumo rastreável' },
  suggestions: { icon: Zap, label: 'Ajustes sugeridos' },
  general: { icon: Brain, label: 'Contexto geral' },
}

type LandingFeature = {
  code: string
  icon: typeof MessageSquare
  title: string
  desc: string
  evidence: string
}

type FeatureVariant = 'primary' | 'secondary'

type LandingStep = {
  n: string
  title: string
  desc: string
}

const FEATURES: LandingFeature[] = [
  {
    code: 'R01',
    icon: MessageSquare,
    title: 'Perguntas com fonte explícita',
    desc: 'Cada resposta aponta o trecho usado. Você valida rapidamente sem depender de memória ou intuição.',
    evidence: 'Rastreabilidade por citação de origem',
  },
  {
    code: 'R02',
    icon: FileText,
    title: 'Resumos com estrutura útil',
    desc: 'Resumo breve ou aprofundado com organização por seções para facilitar estudo, revisão e consulta.',
    evidence: 'Contexto consolidado por seção',
  },
  {
    code: 'R03',
    icon: Layers,
    title: 'Flashcards e revisão contínua',
    desc: 'Gera cards a partir dos seus materiais e organiza revisões para manter retenção sem sobrecarga.',
    evidence: 'Ciclo de revisão orientado por conteúdo',
  },
  {
    code: 'R04',
    icon: GraduationCap,
    title: 'Plano de estudo acionável',
    desc: 'Transforma matéria extensa em blocos diários com prioridades claras e progresso visível.',
    evidence: 'Planejamento por meta e tempo',
  },
  {
    code: 'R05',
    icon: KanbanSquare,
    title: 'Leitura com estado rastreado',
    desc: 'Organiza o que está pendente, em andamento e concluído, com visão objetiva do seu acervo.',
    evidence: 'Status operacional de documentos',
  },
  {
    code: 'R06',
    icon: CalendarDays,
    title: 'Multiformato sem fricção',
    desc: 'PDF, markdown, planilha, imagem com OCR, URL e vídeo. Tudo entra no mesmo fluxo de estudo.',
    evidence: 'Ingestão unificada de formatos',
  },
]

const STEPS: LandingStep[] = [
  {
    n: '01',
    title: 'Ingestão do material',
    desc: 'Envie arquivos, links ou textos. O DocOps organiza e indexa automaticamente.',
  },
  {
    n: '02',
    title: 'Consulta com prova',
    desc: 'Pergunte em linguagem natural e receba resposta com referência direta ao conteúdo original.',
  },
  {
    n: '03',
    title: 'Estudo em ciclo contínuo',
    desc: 'Resumo, tarefas, flashcards e agenda trabalham em conjunto para manter constância.',
  },
]

const METRICS = [
  {
    icon: FileStack,
    value: '10+',
    label: 'formatos suportados',
    desc: 'PDF, Markdown, CSV, XLSX, imagem, URL e vídeo',
  },
  {
    icon: Clock,
    value: '< 2s',
    label: 'resposta média',
    desc: 'Busca híbrida com foco em rapidez e consistência',
  },
  {
    icon: Shield,
    value: '100%',
    label: 'execução local',
    desc: 'Dados do usuário permanecem no próprio ambiente',
  },
] as const

const FOOTER_LINKS = {
  Produto: [
    { label: 'Chat com documentos', href: '#recursos' },
    { label: 'Plano de estudo', href: '#recursos' },
    { label: 'Revisão e flashcards', href: '#recursos' },
  ],
  Recursos: [
    { label: 'Como funciona', href: '#como-funciona' },
    { label: 'Demo', href: '#demo' },
    { label: 'Repositório', href: 'https://github.com/DocOps-Agent/DocOps_Agent', external: true },
  ],
  Legal: [
    { label: 'Termos', href: '#' },
    { label: 'Privacidade', href: '#' },
    { label: 'Licença MIT', href: 'https://github.com/DocOps-Agent/DocOps_Agent/blob/main/LICENSE', external: true },
  ],
}

const NAV_ITEMS = [
  { id: 'recursos', label: 'Recursos' },
  { id: 'como-funciona', label: 'Como funciona' },
  { id: 'demo', label: 'Demo' },
] as const

const FOCUS_VISIBLE =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2F6BFF] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0E12]'

function scrollToSection(id: string) {
  const el = document.getElementById(id)
  if (!el) return

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' })
}

function FeatureCard({
  feature,
  index,
  variant,
}: {
  feature: LandingFeature
  index: number
  variant: FeatureVariant
}) {
  const [ref, delay] = useDynamicDelay(index)
  const Icon = feature.icon
  const isPrimary = variant === 'primary'

  return (
    <motion.article
      ref={ref}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.45, delay, ease: EASE }}
      className={[
        'group relative rounded-sm border p-5 shadow-[0_1px_0_rgba(243,241,235,0.02)] transition-all duration-200',
        'hover:-translate-y-0.5 hover:border-[#4B5970]',
        isPrimary
          ? 'border-[#324057] bg-[linear-gradient(180deg,rgba(18,24,33,0.96),rgba(14,22,34,0.94))] sm:p-6'
          : 'border-[#27303A] bg-[#121821]/88 sm:p-5',
      ].join(' ')}
    >
      <span className={`absolute inset-y-0 left-0 ${isPrimary ? 'w-[3px]' : 'w-[2px]'} bg-[#2F6BFF]`} />
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-meta text-[11px] font-medium tracking-[0.14em] text-[#93A0B2]">{feature.code}</p>
          <h3 className={`mt-2 ${isPrimary ? 'text-[1.38rem] leading-tight' : 'text-lg'} font-semibold text-[#F3F1EB]`}>
            {feature.title}
          </h3>
        </div>
        <div
          className={`flex ${isPrimary ? 'h-10 w-10' : 'h-9 w-9'} items-center justify-center rounded-sm border border-[#324057] bg-[#0E141E] text-[#AAB3BF]`}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>
      </div>
      <p className={`mt-4 ${isPrimary ? 'text-[16px]' : 'text-[15px]'} leading-relaxed text-[#B6C0CD]`}>{feature.desc}</p>
      <div className="mt-5 border-t border-[#2E3847] pt-3">
        <p className="font-meta text-[11px] tracking-[0.12em] text-[#8A96A9]">Evidência operacional</p>
        <p className="mt-1 text-xs leading-relaxed text-[#AAB3BF]">{feature.evidence}</p>
      </div>
    </motion.article>
  )
}

function StepItem({ step, index }: { step: LandingStep; index: number }) {
  const [ref, delay] = useDynamicDelay(index)

  return (
    <motion.article
      ref={ref}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.45, delay, ease: EASE }}
      className="relative rounded-sm border border-[#324057] bg-[#101823]/90 p-5 sm:p-6"
    >
      <div className="flex items-center gap-3 border-b border-[#2D3747] pb-3">
        <span className="font-meta flex h-6 w-6 items-center justify-center rounded-sm border border-[#35507E] bg-[#121E31] text-[11px] tracking-[0.06em] text-[#D7E2F4]">
          {step.n}
        </span>
        <p className="font-meta text-[11px] tracking-[0.12em] text-[#8A96A9]">Etapa sequencial</p>
      </div>
      <h3 className="mt-4 text-lg font-semibold text-[#F3F1EB]">{step.title}</h3>
      <p className="mt-3 text-[15px] leading-relaxed text-[#B1BBC8]">{step.desc}</p>
    </motion.article>
  )
}

function ResultCard({ card, index }: { card: AICard; index: number }) {
  const [ref, cardDelay] = useDynamicDelay(index)
  const style = CARD_STYLES[card.category]
  const Icon = style.icon
  const isLead = index === 0

  return (
    <motion.article
      ref={ref}
      key={`card-${index}`}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8, transition: { duration: 0.22, ease: EASE } }}
      transition={{ duration: 0.38, delay: cardDelay, ease: EASE }}
      className={[
        'rounded-sm border p-4 sm:p-5',
        isLead ? 'border-[#35507E] bg-[#121C2A]' : 'border-[#2E3847] bg-[#111926]',
      ].join(' ')}
    >
      <div className={`flex items-center gap-2.5 border-b ${isLead ? 'border-[#33445F]' : 'border-[#2D3747]'} pb-3`}>
        <Icon className="h-4 w-4 text-[#9DB0CC]" aria-hidden="true" />
        <div>
          <p className="font-meta text-[10px] tracking-[0.1em] text-[#8D9BB0]">{style.label}</p>
          <h3 className="mt-0.5 text-sm font-semibold text-[#F3F1EB]">{card.title}</h3>
        </div>
      </div>
      <ul className="mt-4 space-y-2.5">
        {card.items.map((item, j) => (
          <motion.li
            key={item}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.28, delay: cardDelay + getDynamicDelay(j) * 0.4 + 0.06, ease: EASE }}
            className="flex items-start gap-2 text-xs leading-relaxed text-[#AAB3BF]"
          >
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#2F6BFF]" aria-hidden="true" />
            {item}
          </motion.li>
        ))}
      </ul>
    </motion.article>
  )
}

export function Landing() {
  const [demoInput, setDemoInput] = useState('Organize meu estudo de machine learning')
  const [activeSection, setActiveSection] = useState<(typeof NAV_ITEMS)[number]['id']>('recursos')
  const ai = useAI()
  const demoState = ai.loading ? 'loading' : ai.result ? 'done' : 'idle'

  const autoTriggered = useCallback(() => {
    if (!ai.result && !ai.loading) ai.run(demoInput)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    autoTriggered()
  }, [autoTriggered])

  useEffect(() => {
    const handler = () => {
      const threshold = window.innerHeight * 0.34
      let current: (typeof NAV_ITEMS)[number]['id'] = 'recursos'

      NAV_ITEMS.forEach((item) => {
        const node = document.getElementById(item.id)
        if (!node) return
        const top = node.getBoundingClientRect().top
        if (top <= threshold) current = item.id
      })

      setActiveSection(current)
    }

    handler()
    window.addEventListener('scroll', handler, { passive: true })
    window.addEventListener('resize', handler)
    return () => {
      window.removeEventListener('scroll', handler)
      window.removeEventListener('resize', handler)
    }
  }, [])

  const primaryFeatures = FEATURES.slice(0, 2)
  const secondaryFeatures = FEATURES.slice(2)

  return (
    <MotionConfig reducedMotion="user">
      <BackgroundWrapper>
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-[#2457D6] focus:px-4 focus:py-2 focus:text-sm focus:text-white focus:outline-none"
        >
          Pular para conteúdo
        </a>

        <header className="relative border-b border-[#27303A]/90 bg-[#0B0E12]/95">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-[#2457D6]">
                <BookOpen className="h-4 w-4 text-white" aria-hidden="true" />
              </div>
              <span className="text-sm font-semibold tracking-wide text-[#F3F1EB]">DocOps Agent</span>
            </div>
            <nav className="hidden items-center gap-6 sm:flex" aria-label="Navegação principal">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToSection(item.id)}
                  aria-current={activeSection === item.id ? 'page' : undefined}
                  className={`relative pb-1 text-sm transition-colors ${FOCUS_VISIBLE} ${
                    activeSection === item.id ? 'text-[#F3F1EB]' : 'text-[#AAB3BF] hover:text-[#F3F1EB]'
                  }`}
                >
                  {item.label}
                  <span
                    aria-hidden="true"
                    className={`absolute -bottom-2 left-0 right-0 h-px bg-[#2F6BFF] transition-opacity ${
                      activeSection === item.id ? 'opacity-100' : 'opacity-0'
                    }`}
                  />
                </button>
              ))}
            </nav>
            <div className="flex items-center gap-3">
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="border border-transparent text-[#AAB3BF] hover:border-[#27303A] hover:bg-[#121821] hover:text-[#F3F1EB]"
              >
                <Link to="/login">Entrar</Link>
              </Button>
              <Button asChild size="sm" className="bg-[#2457D6] text-white hover:bg-[#1F4FC8]">
                <Link to="/register">Criar conta</Link>
              </Button>
            </div>
          </div>
        </header>

        <main id="content">
          <section className="mx-auto max-w-6xl px-6 pb-14 pt-14 sm:pb-20 sm:pt-16" aria-label="Hero">
            <div className="rounded-sm border border-[#2C3645] bg-[linear-gradient(165deg,rgba(15,20,27,0.94),rgba(12,18,26,0.96))] px-5 py-8 sm:px-7 lg:px-9 lg:py-10">
              <div className="grid items-start gap-10 lg:grid-cols-12">
              <div className="lg:col-span-7">
                <motion.p
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: getDynamicDelay(0), ease: EASE }}
                  className="inline-flex items-center gap-2 rounded-sm border border-[#324057] bg-[#111A27] px-3 py-1.5 font-meta text-[11px] tracking-[0.1em] text-[#B6C4D8]"
                >
                  <Shield className="h-3 w-3" aria-hidden="true" />
                  Evidência antes de efeito
                </motion.p>

                <motion.h1
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.48, delay: getDynamicDelay(1), ease: EASE }}
                  className="font-display mt-6 text-[2.35rem] leading-[1.06] text-[#F3F1EB] sm:text-6xl lg:text-[4.25rem]"
                >
                  Respostas confiáveis
                  <br />
                  para cada documento.
                </motion.h1>

                <motion.p
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.44, delay: getDynamicDelay(2), ease: EASE }}
                  className="mt-6 max-w-2xl text-lg leading-relaxed text-[#B0BBC9]"
                >
                  O DocOps Agent transforma arquivos e links em uma base consultável com citações explícitas, fluxo de
                  estudo e operação local. Menos suposição, mais verificação.
                </motion.p>

                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.36, delay: getDynamicDelay(3), ease: EASE }}
                  className="mt-10 flex flex-wrap items-center gap-4"
                >
                  <Button asChild size="lg" className="h-12 rounded-sm bg-[#2457D6] px-8 text-base text-white hover:bg-[#1F4FC8]">
                    <Link to="/register">
                      Criar conta grátis <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  <button
                    type="button"
                    onClick={() => scrollToSection('demo')}
                    className={`h-12 rounded-sm border border-[#334057] bg-[#121A26] px-6 text-sm font-semibold text-[#F3F1EB] transition-colors hover:border-[#4B5970] hover:bg-[#152033] hover:text-[#F3F1EB] ${FOCUS_VISIBLE}`}
                  >
                    Ver demonstração
                  </button>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.32, delay: getDynamicDelay(4), ease: EASE }}
                  className="mt-6 flex flex-wrap items-center gap-3 font-meta text-[11px] tracking-[0.1em] text-[#8896AA]"
                >
                  <span className="rounded-sm border border-[#31415A] bg-[#101823] px-2 py-1">Fontes citadas</span>
                  <span className="rounded-sm border border-[#31415A] bg-[#101823] px-2 py-1">Execução local</span>
                  <span className="rounded-sm border border-[#31415A] bg-[#101823] px-2 py-1">Busca híbrida</span>
                </motion.div>
              </div>

              <motion.aside
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: getDynamicDelay(2) + 0.06, ease: EASE }}
                className="relative rounded-sm border border-[#35507E] bg-[linear-gradient(170deg,rgba(17,26,39,0.96),rgba(15,22,33,0.98))] lg:col-span-5"
                aria-label="Painel de evidência"
              >
                <div className="border-b border-[#31405A] px-5 py-4">
                  <p className="font-meta text-[11px] tracking-[0.1em] text-[#9CB0CD]">Prova explícita</p>
                  <h2 className="mt-2 text-xl font-semibold text-[#F3F1EB]">Resposta verificável acima da dobra</h2>
                </div>
                <div className="space-y-3 p-5">
                  <div className="rounded-sm border border-[#30405A] bg-[#0F1724] p-3">
                    <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Pergunta</p>
                    <p className="mt-1 text-[15px] font-semibold text-[#F3F1EB]">Quais tópicos devo revisar hoje para manter o ritmo?</p>
                  </div>
                  <div className="rounded-sm border border-[#324057] bg-[#121C2A] p-3">
                    <p className="font-meta text-[10px] tracking-[0.1em] text-[#9AB0CF]">Resposta</p>
                    <p className="mt-1 text-sm leading-relaxed text-[#F3F1EB]">
                      Priorize os capítulos 3 e 4, depois execute uma revisão curta com 12 flashcards e conclua com checklist de
                      tarefas.
                    </p>
                  </div>
                  <div className="rounded-sm border border-[#30405A] bg-[#0F1724] p-3">
                    <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Fonte citada</p>
                    <p className="mt-1 font-meta text-xs text-[#C0CBDA]">Manual_ML.pdf - seção 3.2 - linhas 114-139</p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-sm border border-[#31405A] bg-[#101823] px-3 py-2">
                      <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Privacidade</p>
                      <p className="mt-1 text-xs text-[#F3F1EB]">Processamento local</p>
                    </div>
                    <div className="rounded-sm border border-[#31405A] bg-[#101823] px-3 py-2">
                      <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Latência</p>
                      <p className="mt-1 text-xs text-[#F3F1EB]">Resposta média abaixo de 2s</p>
                    </div>
                  </div>
                </div>
              </motion.aside>
              </div>
            </div>
          </section>

          <section className="mx-auto max-w-6xl px-6 pb-14 sm:pb-16" aria-label="Ponte de confiança">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.36, ease: EASE }}
              className="rounded-sm border border-[#2D3948] bg-[#0F141C]/90 px-5 py-4 sm:px-6"
            >
              <div className="grid gap-3 sm:grid-cols-3 sm:gap-5">
                <div className="border-l-2 border-[#35507E] pl-3">
                  <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Rastreabilidade</p>
                  <p className="mt-1 text-sm text-[#C8D2DF]">Resposta sempre ligada a um trecho verificável.</p>
                </div>
                <div className="border-l-2 border-[#35507E] pl-3">
                  <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Privacidade operacional</p>
                  <p className="mt-1 text-sm text-[#C8D2DF]">Processamento local e controle total do acervo.</p>
                </div>
                <div className="border-l-2 border-[#35507E] pl-3">
                  <p className="font-meta text-[10px] tracking-[0.1em] text-[#8EA2BF]">Ato seguinte</p>
                  <p className="mt-1 text-sm text-[#C8D2DF]">Abaixo, recursos organizados por impacto operacional.</p>
                </div>
              </div>
            </motion.div>
          </section>

          <section id="recursos" className="mx-auto max-w-6xl px-6 pb-14 scroll-mt-20 sm:pb-18" aria-labelledby="recursos-heading">
            <div className="rounded-sm border border-[#2B3544] bg-[#0F151E]/88 px-5 py-6 sm:px-7 sm:py-7">
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.42, ease: EASE }}
                className="mb-8"
              >
                <p className="font-meta text-[11px] tracking-[0.12em] text-[#8A96A9]">Capacidades principais</p>
                <h2 id="recursos-heading" className="font-display mt-3 text-[2.05rem] leading-tight text-[#F3F1EB] sm:text-4xl">
                  Funcionalidades tratadas como evidência operacional
                </h2>
              </motion.div>

              <div className="grid gap-5 lg:grid-cols-2">
                {primaryFeatures.map((feature, i) => (
                  <FeatureCard key={feature.code} feature={feature} index={i} variant="primary" />
                ))}
              </div>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {secondaryFeatures.map((feature, i) => (
                  <FeatureCard key={feature.code} feature={feature} index={i + primaryFeatures.length} variant="secondary" />
                ))}
              </div>
            </div>
          </section>

          <section className="mx-auto max-w-6xl px-6 pb-14 sm:pb-18" aria-label="Métricas do produto">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.38, ease: EASE }}
              className="rounded-sm border border-[#2F3A4B] bg-[#111925]/90 p-4 sm:p-5"
            >
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-[#2E3949] pb-3">
                <p className="font-meta text-[11px] tracking-[0.12em] text-[#8A96A9]">Indicadores operacionais</p>
                <p className="font-meta text-[11px] tracking-[0.1em] text-[#7E8896]">Recorte da experiência principal</p>
              </div>
              <div className="grid gap-0 sm:grid-cols-3">
                {METRICS.map((metric, i) => {
                  const Icon = metric.icon
                  return (
                    <motion.article
                      key={metric.label}
                      initial={{ opacity: 0, y: 10 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={VIEWPORT}
                      transition={{ duration: 0.34, delay: getDynamicDelay(i), ease: EASE }}
                      className={`px-4 py-4 sm:px-5 ${i > 0 ? 'border-t border-[#2E3949] sm:border-l sm:border-t-0' : ''}`}
                    >
                      <div className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-[#9AB0CF]" aria-hidden="true" />
                        <p className="font-meta text-[11px] tracking-[0.1em] text-[#8795A8]">Sinal</p>
                      </div>
                      <p className="mt-3 text-4xl font-semibold text-[#F3F1EB]">{metric.value}</p>
                      <p className="mt-1 text-sm font-semibold text-[#E9EDF3]">{metric.label}</p>
                      <p className="mt-2 text-xs leading-relaxed text-[#AEB8C6]">{metric.desc}</p>
                    </motion.article>
                  )
                })}
              </div>
            </motion.div>
          </section>

          <section id="como-funciona" className="mx-auto max-w-6xl px-6 pb-14 scroll-mt-20 sm:pb-18" aria-labelledby="como-funciona-heading">
            <div className="rounded-sm border border-[#2D3948] bg-[#101722]/86 px-5 py-6 sm:px-7 sm:py-7">
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.42, ease: EASE }}
                className="mb-8"
              >
                <p className="font-meta text-[11px] tracking-[0.12em] text-[#8A96A9]">Fluxo de trabalho</p>
                <h2 id="como-funciona-heading" className="font-display mt-3 text-[2.05rem] leading-tight text-[#F3F1EB] sm:text-4xl">
                  Método simples, verificável e contínuo
                </h2>
              </motion.div>
              <div className="relative">
                <div className="pointer-events-none absolute left-[12%] right-[12%] top-8 hidden h-px bg-[linear-gradient(90deg,transparent,rgba(53,80,126,0.68)_15%,rgba(53,80,126,0.68)_85%,transparent)] md:block" />
                <div className="grid gap-4 md:grid-cols-3 md:gap-5">
                  {STEPS.map((step, i) => (
                    <StepItem key={step.n} step={step} index={i} />
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section id="demo" className="mx-auto max-w-6xl px-6 pb-18 scroll-mt-20 sm:pb-24" aria-labelledby="demo-heading">
            <div className="rounded-sm border border-[#31405A] bg-[#0E151F]/92 px-5 py-6 sm:px-7 sm:py-7">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.42, ease: EASE }}
                className="mb-7"
              >
                <p className="font-meta text-[11px] tracking-[0.12em] text-[#8EA2BF]">Demo funcional</p>
                <h2 id="demo-heading" className="font-display mt-3 text-[2.05rem] leading-tight text-[#F3F1EB] sm:text-4xl">
                  Teste uma consulta e veja o retorno estruturado
                </h2>
              </motion.div>

              <motion.form
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.35, delay: getDynamicDelay(0), ease: EASE }}
                className="rounded-sm border border-[#2F3B4E] bg-[#101A27] p-4"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (!demoInput.trim() || demoState === 'loading') return
                  ai.run(demoInput)
                }}
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[#2F3B4E] pb-3">
                  <p className="font-meta text-[11px] tracking-[0.1em] text-[#8EA2BF]">Entrada de comando</p>
                  <p className="font-meta text-[11px] tracking-[0.1em] text-[#7E8896]">Saída estruturada em tarefas, revisão e agenda</p>
                </div>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Input
                    type="text"
                    value={demoInput}
                    onChange={(event) => {
                      setDemoInput(event.target.value)
                      if (ai.result) ai.reset()
                    }}
                    placeholder="Ex: organizar revisão para prova de algoritmos"
                    aria-label="Comando para a demonstração de IA"
                    className="h-12 rounded-sm border-[#38465C] bg-[#111C2B] px-4 text-sm text-[#F3F1EB] placeholder:text-[#7E8896] focus-visible:border-[#2F6BFF] focus-visible:ring-[#2F6BFF]"
                    disabled={demoState === 'loading'}
                  />
                  <Button
                    type="submit"
                    disabled={demoState === 'loading' || !demoInput.trim()}
                    className="h-12 w-full rounded-sm bg-[#2457D6] px-6 text-sm text-white hover:bg-[#1F4FC8] disabled:opacity-50 sm:w-auto"
                  >
                    {demoState === 'loading' ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Processando
                      </>
                    ) : demoState === 'done' ? (
                      <>
                        <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Concluído
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4" aria-hidden="true" /> Executar
                      </>
                    )}
                  </Button>
                </div>
              </motion.form>

              <div className="mt-6" role="status" aria-live="polite" aria-atomic="true" aria-busy={demoState === 'loading'}>
                <AnimatePresence mode="wait">
                  {demoState === 'loading' ? (
                    <motion.div
                      key="loading"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.25, ease: EASE }}
                      className="rounded-sm border border-[#2F3B4E] bg-[#111A27] p-5 text-sm text-[#B8C2D1]"
                    >
                      Processando sua solicitação...
                    </motion.div>
                  ) : ai.result ? (
                    <motion.div
                      key="result"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.25, ease: EASE }}
                    >
                      <div className="rounded-sm border border-[#2F3B4E] bg-[#0F1723] p-3">
                        <p className="font-meta mb-3 text-[11px] tracking-[0.1em] text-[#8EA2BF]">Resultado operacional</p>
                        <div className="grid gap-4 md:grid-cols-3">
                          <AnimatePresence>
                            {ai.result.cards.map((card, i) => (
                              <ResultCard key={`card-${i}`} card={card} index={i} />
                            ))}
                          </AnimatePresence>
                        </div>
                      </div>
                      <div className="mt-5">
                        <button
                          type="button"
                          onClick={ai.reset}
                          className={`font-meta text-[11px] tracking-[0.1em] text-[#8B97AA] transition-colors hover:text-[#F3F1EB] ${FOCUS_VISIBLE} focus-visible:rounded-sm`}
                        >
                          Resetar demonstração
                        </button>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.25, ease: EASE }}
                      className="rounded-sm border border-dashed border-[#33445C] bg-[#111A27] p-5"
                    >
                      <p className="text-sm font-semibold text-[#F3F1EB]">Nenhum resultado ainda.</p>
                      <p className="mt-1 text-sm text-[#AAB3BF]">Digite um objetivo de estudo e execute a consulta.</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </section>

          <section className="mx-auto max-w-6xl px-6 pb-20 sm:pb-24" aria-label="Chamada para ação">
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.42, ease: EASE }}
              className="rounded-sm border border-[#3A4A61] bg-[linear-gradient(165deg,rgba(16,24,36,0.97),rgba(13,20,31,0.98))] p-8 text-[#F3F1EB] sm:p-10"
            >
              <div className="mb-7 h-px bg-[linear-gradient(90deg,rgba(47,107,255,0.9),rgba(47,107,255,0.12)_48%,transparent)]" />
              <p className="font-meta text-[11px] tracking-[0.12em] text-[#AFC0D8]">Início rápido</p>
              <h2 className="font-display mt-3 text-[2.35rem] leading-tight sm:text-4xl">Transforme seus documentos em um sistema de estudo confiável</h2>
              <p className="mt-4 max-w-2xl text-sm leading-relaxed text-[#B5C0CF]">
                Crie a conta, envie o material e valide respostas com fonte citada. Operação técnica sem ruído visual.
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-4">
                <Button asChild size="lg" className="h-11 rounded-sm bg-[#2457D6] px-7 text-sm text-white hover:bg-[#1F4FC8]">
                  <Link to="/register">
                    Criar conta grátis <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
                <Button
                  asChild
                  variant="ghost"
                  size="lg"
                  className="h-11 rounded-sm border border-[#44556D] px-6 text-sm text-[#F3F1EB] hover:bg-[#1A2637]"
                >
                  <Link to="/login">Entrar</Link>
                </Button>
              </div>
              <p className="mt-4 flex items-center gap-1.5 text-xs text-[#8A96A9]">
                <Lock className="h-3 w-3" aria-hidden="true" /> Sem cartão de crédito
              </p>
            </motion.div>
          </section>
        </main>

        <footer className="relative border-t border-[#27303A]/90 bg-[#0F141B]" role="contentinfo">
          <div className="mx-auto max-w-6xl px-6 py-12">
            <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-4">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-[#2457D6]">
                    <BookOpen className="h-3.5 w-3.5 text-white" aria-hidden="true" />
                  </div>
                  <span className="text-sm font-semibold text-[#F3F1EB]">DocOps Agent</span>
                </div>
                <p className="max-w-[240px] text-sm leading-relaxed text-[#AAB3BF]">
                  Plataforma de documentos com respostas rastreáveis, estudo guiado e operação local.
                </p>
              </div>

              {Object.entries(FOOTER_LINKS).map(([title, links]) => (
                <div key={title}>
                  <h4 className="font-meta mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-[#7E8896]">{title}</h4>
                  <ul className="space-y-2">
                    {links.map((link) => (
                      <li key={link.label}>
                        {'external' in link && link.external ? (
                          <a
                            href={link.href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`text-sm text-[#AAB3BF] transition-colors hover:text-[#F3F1EB] ${FOCUS_VISIBLE} focus-visible:rounded-sm`}
                          >
                            {link.label}
                          </a>
                        ) : link.href.startsWith('#') ? (
                          <button
                            type="button"
                            onClick={() => scrollToSection(link.href.slice(1))}
                            className={`text-sm text-[#AAB3BF] transition-colors hover:text-[#F3F1EB] ${FOCUS_VISIBLE} focus-visible:rounded-sm`}
                          >
                            {link.label}
                          </button>
                        ) : (
                          <a href={link.href} className={`text-sm text-[#AAB3BF] transition-colors hover:text-[#F3F1EB] ${FOCUS_VISIBLE} focus-visible:rounded-sm`}>
                            {link.label}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-[#27303A] pt-6 sm:flex-row">
              <p className="text-xs text-[#AAB3BF]">&copy; {new Date().getFullYear()} DocOps Agent. Todos os direitos reservados.</p>
              <p className="font-meta text-[11px] uppercase tracking-[0.12em] text-[#7E8896]">IA local - busca semântica + vetorial</p>
            </div>
          </div>
        </footer>
      </BackgroundWrapper>
    </MotionConfig>
  )
}

