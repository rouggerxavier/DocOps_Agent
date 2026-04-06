import { Link } from 'react-router-dom'
import { motion, MotionConfig } from 'framer-motion'
import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, FileText, Layers, Shield } from 'lucide-react'
import { HeroFuturistic } from '@/components/HeroFuturistic'
import { BackgroundWrapper } from '@/components/BackgroundWrapper'
import { Button } from '@/components/ui/button'

const EASE = [0.2, 0.8, 0.2, 1] as const
const VIEWPORT = { once: true, margin: '-48px' } as const
const FOCUS_VISIBLE =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--ui-bg)]'

type LandingIcon = typeof BookOpen

type ProofChip = {
  icon: LandingIcon
  label: string
}

type Pillar = {
  n: string
  icon: LandingIcon
  title: string
  description: string
}

type EvidenceCard = {
  icon: LandingIcon
  eyebrow: string
  title: string
  description: string
  lines: string[]
}

const PROOF_CHIPS: ProofChip[] = [
  { icon: FileText, label: 'PDF, Word, texto' },
  { icon: Shield, label: 'Execução local' },
  { icon: CalendarDays, label: 'Agenda integrada' },
]

const PILLARS: Pillar[] = [
  {
    n: '01',
    icon: FileText,
    title: 'Suba seus documentos',
    description: 'PDF, Word ou texto puro. O agente indexa, fragmenta e mantém tudo pronto para consulta.',
  },
  {
    n: '02',
    icon: CheckCircle2,
    title: 'Pergunte em linguagem natural',
    description: 'A resposta vem com a fonte exata — página e documento — para você conferir antes de agir.',
  },
  {
    n: '03',
    icon: CalendarDays,
    title: 'Planeje e agende',
    description: 'Peça um plano de estudos ou crie lembretes. O agente organiza na sua agenda direto pelo chat.',
  },
]

const EVIDENCE_CARDS: EvidenceCard[] = [
  {
    icon: FileText,
    eyebrow: 'Resposta rastreável',
    title: 'Fonte junto da resposta',
    description: 'Cada resposta indica o documento e o trecho exato que a sustenta.',
    lines: ['"O prazo de entrega é de 30 dias corridos após assinatura."', 'Contrato_servicos.pdf · pág. 4'],
  },
  {
    icon: CalendarDays,
    eyebrow: 'Agenda',
    title: 'Lembretes pelo chat',
    description: 'Crie, edite e consulte eventos sem sair da conversa.',
    lines: ['Criar lembrete para amanhã às 9h', '→ Lembrete criado: Revisão de contrato · seg 09:00'],
  },
  {
    icon: Layers,
    eyebrow: 'Plano de estudos',
    title: 'Material vira cronograma',
    description: 'O agente distribui o conteúdo dos seus documentos em sessões de estudo com prazo definido.',
    lines: ['Seg · Cap. 1 — Fundamentos (2h)', 'Qua · Cap. 2 — Aplicações (2h)', 'Sex · Revisão geral (1h)'],
  },
]

const FOOTER_LINKS = [
  { label: 'GitHub', href: 'https://github.com/DocOps-Agent/DocOps_Agent' },
  { label: 'Licença MIT', href: 'https://github.com/DocOps-Agent/DocOps_Agent/blob/main/LICENSE' },
] as const

function scrollToSection(id: string) {
  const element = document.getElementById(id)
  if (!element) return

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  element.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' })
}

function ProofChip({ chip, index }: { chip: ProofChip; index: number }) {
  const Icon = chip.icon

  return (
    <motion.li
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, delay: index * 0.06, ease: EASE }}
      className="inline-flex items-center gap-2 rounded-full border border-[color:var(--ui-border)] bg-[rgba(255,255,255,0.03)] px-4 py-2 text-sm text-[color:var(--ui-text-dim)] backdrop-blur"
    >
      <Icon className="h-4 w-4 text-[color:var(--ui-accent)]" aria-hidden="true" />
      <span>{chip.label}</span>
    </motion.li>
  )
}

function PillarCard({ pillar, index }: { pillar: Pillar; index: number }) {
  const Icon = pillar.icon

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.4, delay: index * 0.08, ease: EASE }}
      className="rounded-[1.75rem] border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6 shadow-[0_18px_48px_rgba(0,0,0,0.22)]"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-meta text-[11px] tracking-[0.18em] text-[color:var(--ui-text-meta)]">{pillar.n}</span>
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)]">
          <Icon className="h-4 w-4 text-[color:var(--ui-accent)]" aria-hidden="true" />
        </div>
      </div>
      <h3 className="mt-8 text-2xl font-semibold text-[color:var(--ui-text)]">{pillar.title}</h3>
      <p className="mt-3 max-w-[28ch] text-sm leading-7 text-[color:var(--ui-text-dim)]">{pillar.description}</p>
    </motion.article>
  )
}

function EvidenceCard({ card, index }: { card: EvidenceCard; index: number }) {
  const Icon = card.icon

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.42, delay: index * 0.08, ease: EASE }}
      className="rounded-[1.75rem] border border-[color:var(--ui-border)] bg-[rgba(255,255,255,0.02)] p-6"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)]">
          <Icon className="h-4 w-4 text-[color:var(--ui-accent)]" aria-hidden="true" />
        </div>
        <p className="font-meta text-[11px] tracking-[0.16em] text-[color:var(--ui-text-meta)]">{card.eyebrow}</p>
      </div>
      <h3 className="mt-6 text-xl font-semibold text-[color:var(--ui-text)]">{card.title}</h3>
      <p className="mt-3 text-sm leading-7 text-[color:var(--ui-text-dim)]">{card.description}</p>
      <div className="mt-6 rounded-[1.4rem] border border-[color:var(--ui-border)] bg-[rgba(0,0,0,0.18)] p-4">
        <div className="space-y-3 text-sm leading-6 text-[color:var(--ui-text)]">
          {card.lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      </div>
    </motion.article>
  )
}

export function Landing() {
  return (
    <MotionConfig reducedMotion="user">
      <BackgroundWrapper>
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-[color:var(--ui-accent)] focus:px-4 focus:py-2 focus:text-sm focus:text-[#0e1012] focus:outline-none"
        >
          Pular para conteúdo
        </a>

        <header className="sticky top-0 z-30 border-b border-[color:var(--ui-border)] bg-[rgba(14,16,18,0.78)] backdrop-blur-xl">
          <div className="mx-auto flex h-18 max-w-[1280px] items-center justify-between px-6 sm:px-8 lg:px-10">
            <Link to="/" className={`flex items-center gap-3 text-[color:var(--ui-text)] ${FOCUS_VISIBLE} rounded-full`}>
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--ui-accent)] text-[#0e1012] shadow-[0_10px_30px_rgba(201,139,94,0.24)]">
                <BookOpen className="h-4 w-4" aria-hidden="true" />
              </div>
              <span className="text-sm font-semibold tracking-[0.08em]">DocOps Agent</span>
            </Link>

            <div className="flex items-center gap-2 sm:gap-3">
              <Button asChild variant="ghost" size="sm" className="rounded-full px-4 text-[color:var(--ui-text-dim)]">
                <Link to="/login">Entrar</Link>
              </Button>
              <Button
                asChild
                size="sm"
                className="rounded-full border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)] px-5 text-[#0e1012] hover:border-[color:var(--ui-accent-strong)] hover:bg-[color:var(--ui-accent-strong)]"
              >
                <Link to="/register">Criar conta</Link>
              </Button>
            </div>
          </div>
        </header>

        <main id="content">
          <section className="mx-auto flex max-w-[1280px] items-start px-6 py-6 sm:px-8 sm:py-10 lg:min-h-[calc(100svh-73px)] lg:items-center lg:px-10 lg:py-16">
            <div className="grid w-full items-start gap-6 sm:gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(420px,0.95fr)] lg:items-center lg:gap-14">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: EASE }}
                className="max-w-[38rem] pt-3 sm:pt-4 lg:pt-0"
              >
                <p className="font-meta text-[11px] uppercase tracking-[0.22em] text-[color:var(--ui-accent)]">
                  Agente de documentos com IA
                </p>
                <h1 className="font-display mt-4 text-[2.65rem] leading-[0.95] text-[color:var(--ui-text)] sm:mt-5 sm:text-[4.5rem] lg:text-[5.5rem]">
                  Seus documentos respondem. Com fonte.
                </h1>
                <p className="mt-5 max-w-[34rem] text-[0.98rem] leading-7 text-[color:var(--ui-text-dim)] sm:mt-6 sm:text-[1.08rem] sm:leading-8">
                  Suba PDFs e textos, faça perguntas em linguagem natural e receba respostas rastreáveis. O DocOps Agent ainda cria planos de estudo e gerencia sua agenda pelo chat.
                </p>

                <div className="mt-6 flex flex-col gap-3 sm:mt-8 sm:flex-row sm:items-center">
                  <Button
                    asChild
                    size="lg"
                    className="rounded-full border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)] px-7 text-[#0e1012] hover:border-[color:var(--ui-accent-strong)] hover:bg-[color:var(--ui-accent-strong)]"
                  >
                    <Link to="/register">
                      Criar conta
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="lg"
                    onClick={() => scrollToSection('prova')}
                    className="rounded-full border-[color:var(--ui-border-strong)] px-7"
                  >
                    Ver como funciona
                  </Button>
                </div>

                <ul className="mt-6 flex flex-wrap gap-2.5 sm:mt-8 sm:gap-3">
                  {PROOF_CHIPS.map((chip, index) => (
                    <ProofChip key={chip.label} chip={chip} index={index} />
                  ))}
                </ul>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.08, ease: EASE }}
                className="order-last mt-1 lg:order-none lg:mt-0"
              >
                <HeroFuturistic className="h-[260px] sm:h-[380px] lg:h-[620px]" interactive fallbackMode="still" />
              </motion.div>
            </div>
          </section>

          <section id="valor" className="mx-auto max-w-[1280px] scroll-mt-28 px-6 py-8 sm:px-8 sm:py-12 lg:px-10 lg:py-16" aria-labelledby="valor-heading">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.44, ease: EASE }}
              className="mb-8 max-w-[38rem] sm:mb-10"
            >
              <p className="font-meta text-[11px] uppercase tracking-[0.2em] text-[color:var(--ui-text-meta)]">Como funciona</p>
              <h2 id="valor-heading" className="font-display mt-4 text-[2.7rem] leading-[0.96] text-[color:var(--ui-text)] sm:text-[3.4rem]">
                Do documento à resposta em três passos.
              </h2>
            </motion.div>

            <div className="grid gap-5 lg:grid-cols-3">
              {PILLARS.map((pillar, index) => (
                <PillarCard key={pillar.title} pillar={pillar} index={index} />
              ))}
            </div>
          </section>

          <section id="prova" className="mx-auto max-w-[1280px] scroll-mt-28 px-6 py-8 sm:px-8 sm:py-12 lg:px-10 lg:py-16" aria-labelledby="prova-heading">
            <div className="rounded-[2rem] border border-[color:var(--ui-border)] bg-[linear-gradient(180deg,rgba(21,24,27,0.9),rgba(16,18,20,0.96))] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.3)] sm:p-8 lg:p-10">
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                transition={{ duration: 0.44, ease: EASE }}
                className="mb-8 max-w-[40rem]"
              >
                <p className="font-meta text-[11px] uppercase tracking-[0.2em] text-[color:var(--ui-accent)]">Na prática</p>
                <h2 id="prova-heading" className="font-display mt-4 text-[2.7rem] leading-[0.98] text-[color:var(--ui-text)] sm:text-[3.4rem]">
                  O que o agente entrega no dia a dia.
                </h2>
                <p className="mt-4 max-w-[36rem] text-sm leading-7 text-[color:var(--ui-text-dim)] sm:text-base">
                  Respostas com fonte, agenda pelo chat e planos de estudo gerados direto do seu material.
                </p>
              </motion.div>

              <div className="grid gap-5 lg:grid-cols-3">
                {EVIDENCE_CARDS.map((card, index) => (
                  <EvidenceCard key={card.title} card={card} index={index} />
                ))}
              </div>
            </div>
          </section>

          <section className="mx-auto max-w-[1280px] px-6 py-10 sm:px-8 sm:py-14 lg:px-10 lg:py-18" aria-labelledby="cta-heading">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              transition={{ duration: 0.44, ease: EASE }}
              className="flex flex-col gap-6 rounded-[2rem] border border-[color:var(--ui-border)] bg-[rgba(255,255,255,0.03)] p-7 sm:p-9 lg:flex-row lg:items-end lg:justify-between"
            >
              <div className="max-w-[36rem]">
                <p className="font-meta text-[11px] uppercase tracking-[0.2em] text-[color:var(--ui-text-meta)]">Comece agora</p>
                <h2 id="cta-heading" className="font-display mt-4 text-[2.5rem] leading-[0.98] text-[color:var(--ui-text)] sm:text-[3.2rem]">
                  Crie a conta e suba seu primeiro documento.
                </h2>
                <p className="mt-4 text-sm leading-7 text-[color:var(--ui-text-dim)] sm:text-base">
                  Em minutos o agente já responde perguntas sobre o seu material, com a fonte de cada informação.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  asChild
                  size="lg"
                  className="rounded-full border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)] px-7 text-[#0e1012] hover:border-[color:var(--ui-accent-strong)] hover:bg-[color:var(--ui-accent-strong)]"
                >
                  <Link to="/register">
                    Criar conta
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
                <Button asChild variant="ghost" size="lg" className="rounded-full px-6 text-[color:var(--ui-text)]">
                  <Link to="/login">Entrar</Link>
                </Button>
              </div>
            </motion.div>
          </section>
        </main>

        <footer className="border-t border-[color:var(--ui-border)]" role="contentinfo">
          <div className="mx-auto flex max-w-[1280px] flex-col gap-4 px-6 py-6 text-sm text-[color:var(--ui-text-dim)] sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-10">
            <p>© {new Date().getFullYear()} DocOps Agent. Agente de documentos com IA.</p>
            <div className="flex flex-wrap items-center gap-4">
              {FOOTER_LINKS.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer noopener"
                  className={`transition-colors hover:text-[color:var(--ui-text)] ${FOCUS_VISIBLE} rounded-full`}
                >
                  {link.label}
                </a>
              ))}
            </div>
          </div>
        </footer>
      </BackgroundWrapper>
    </MotionConfig>
  )
}
