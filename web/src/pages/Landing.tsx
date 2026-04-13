import { Link } from 'react-router-dom'
import { motion, MotionConfig } from 'framer-motion'
import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, FileText, Layers, Shield } from 'lucide-react'
import { HeroFuturistic } from '@/components/HeroFuturistic'

const EASE = [0.2, 0.8, 0.2, 1] as const
const VIEWPORT = { once: true, margin: '-48px' } as const

export function Landing() {
  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-surface text-on-surface font-body selection:bg-secondary-container selection:text-on-secondary-container">
        <header className="fixed top-0 left-0 z-50 w-full border-b border-white/5 bg-surface/85 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-4 sm:px-6 md:px-12 md:py-6">
            <span className="text-xl font-extrabold tracking-tighter text-primary sm:text-2xl">DocOps Agent</span>
            <nav className="hidden items-center gap-8 md:flex">
              <a className="font-headline font-semibold tracking-tight text-on-surface/70 transition-all duration-300 hover:text-primary" href="#features">
                Funcionalidades
              </a>
              <a className="font-headline font-semibold tracking-tight text-on-surface/70 transition-all duration-300 hover:text-primary" href="#how-it-works">
                Como funciona
              </a>
            </nav>
            <div className="flex items-center gap-2 sm:gap-4">
              <Link to="/login" className="hidden px-4 py-2 font-headline font-semibold text-on-surface transition-transform active:scale-95 sm:inline-flex">
                Entrar
              </Link>
              <Link
                to="/register"
                className="inline-flex rounded-xl bg-primary px-4 py-2 text-sm font-headline font-bold text-on-primary shadow-lg shadow-primary/20 transition-all duration-300 hover:shadow-primary/40 active:scale-95 sm:px-6 sm:text-base"
              >
                Criar conta
              </Link>
            </div>
          </div>
        </header>

        <main className="pb-28 pt-24 sm:pt-28 md:pb-0 md:pt-32">
          <section className="mx-auto mb-20 grid max-w-[1440px] items-center gap-10 px-4 sm:px-6 md:mb-32 md:gap-16 md:px-12 lg:grid-cols-2">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: EASE }}
              className="space-y-7"
            >
              <div className="inline-flex items-center gap-2 rounded-full border-l-4 border-secondary bg-surface-container-high px-3 py-1">
                <Shield className="h-3.5 w-3.5 text-secondary" />
                <span className="font-label text-[11px] font-bold uppercase tracking-widest text-secondary">
                  AGENTE DE DOCUMENTOS COM IA
                </span>
              </div>

              <h1 className="font-headline text-[2.2rem] font-extrabold leading-[1.08] tracking-tight text-on-surface sm:text-5xl md:text-7xl">
                Os documentos tem a resposta. <span className="text-secondary">Com fonte.</span>
              </h1>

              <p className="max-w-xl text-base leading-relaxed text-on-surface-variant sm:text-lg md:text-xl">
                Suba PDFs e textos, pergunte em linguagem natural e receba respostas rastreaveis.
                O DocOps tambem cria planos de estudo e organiza sua agenda no chat.
              </p>

              <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
                <Link
                  to="/register"
                  className="w-full rounded-xl bg-primary px-8 py-4 text-center font-headline text-base font-bold text-on-primary shadow-[0_10px_40px_-10px_rgba(147,197,253,0.3)] transition-all duration-300 hover:-translate-y-1 sm:w-auto sm:text-lg"
                >
                  Criar conta
                </Link>
                <a
                  href="#how-it-works"
                  className="w-full rounded-xl border-b-2 border-outline-variant/30 bg-surface-container-highest px-8 py-4 text-center font-headline text-base font-bold text-on-surface transition-all duration-300 hover:bg-surface-container sm:w-auto sm:text-lg"
                >
                  Ver como funciona
                </a>
              </div>

              <div className="grid max-w-xl grid-cols-3 gap-2 sm:gap-4">
                <div className="rounded-xl border border-outline-variant/20 bg-surface-container-high px-3 py-3 text-center">
                  <p className="font-headline text-lg font-bold text-primary sm:text-xl">+120</p>
                  <p className="text-[11px] text-on-surface-variant sm:text-xs">documentos</p>
                </div>
                <div className="rounded-xl border border-outline-variant/20 bg-surface-container-high px-3 py-3 text-center">
                  <p className="font-headline text-lg font-bold text-primary sm:text-xl">100%</p>
                  <p className="text-[11px] text-on-surface-variant sm:text-xs">com fonte</p>
                </div>
                <div className="rounded-xl border border-outline-variant/20 bg-surface-container-high px-3 py-3 text-center">
                  <p className="font-headline text-lg font-bold text-primary sm:text-xl">24/7</p>
                  <p className="text-[11px] text-on-surface-variant sm:text-xs">assistente</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-4 pt-1 sm:gap-6">
                <div className="flex items-center gap-2 opacity-70">
                  <FileText className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                  <span className="text-sm font-semibold">PDF, Word, texto</span>
                </div>
                <div className="flex items-center gap-2 opacity-70">
                  <Layers className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                  <span className="text-sm font-semibold">Execucao local</span>
                </div>
                <div className="flex items-center gap-2 opacity-70">
                  <CalendarDays className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                  <span className="text-sm font-semibold">Agenda integrada</span>
                </div>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.08, ease: EASE }}
              className="relative h-full min-h-[260px] group sm:min-h-[360px]"
            >
              <div className="absolute -inset-4 rounded-[2rem] bg-primary/10 blur-3xl" />
              <div className="relative h-[260px] w-full sm:h-[420px] lg:h-[620px]">
                <HeroFuturistic className="absolute inset-0" interactive fallbackMode="still" />
                <div className="pointer-events-none absolute inset-0 rounded-[2rem] bg-gradient-to-tr from-primary/5 to-transparent" />
              </div>
            </motion.div>
          </section>

          <section id="how-it-works" className="relative overflow-hidden bg-surface-container px-4 py-20 sm:px-6 md:px-12 md:py-32">
            <div className="absolute top-0 right-0 h-full w-1/3 bg-gradient-to-l from-primary/5 to-transparent" />
            <div className="relative z-10 mx-auto max-w-[1440px]">
              <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="mb-12 md:mb-20">
                <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.3em] text-secondary">Como funciona</h2>
                <h3 className="max-w-2xl font-headline text-3xl font-extrabold text-on-surface md:text-5xl">
                  Do documento a resposta em tres passos
                </h3>
              </motion.div>

              <div className="grid gap-6 md:grid-cols-3 md:gap-10">
                {[
                  { n: '01', title: 'Suba seus documentos', desc: 'PDF, Word ou texto puro em um fluxo seguro e privado.' },
                  { n: '02', title: 'Pergunte em linguagem natural', desc: 'A resposta chega com a fonte exata para voce validar.' },
                  { n: '03', title: 'Planeje e agende', desc: 'Gere plano de estudo e lembretes automaticamente.' },
                ].map((step, idx) => (
                  <motion.div
                    key={step.n}
                    initial={{ opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={VIEWPORT}
                    transition={{ delay: idx * 0.1 }}
                    className="group space-y-4 rounded-2xl border border-outline-variant/20 bg-surface-container-high p-5 md:p-6"
                  >
                    <div className="font-headline text-5xl font-extrabold text-primary/20 transition-colors group-hover:text-primary md:text-6xl">
                      {step.n}
                    </div>
                    <h4 className="font-headline text-xl font-bold text-on-surface md:text-2xl">{step.title}</h4>
                    <p className="text-sm leading-relaxed text-on-surface-variant md:text-base">{step.desc}</p>
                    <div className="h-1 w-12 bg-secondary transition-all duration-500 group-hover:w-full" />
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          <section id="features" className="mx-auto max-w-[1440px] px-4 py-20 sm:px-6 md:px-12 md:py-32">
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="mb-14 text-center md:mb-24">
              <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.3em] text-secondary">Na pratica</h2>
              <h3 className="font-headline text-4xl font-extrabold text-on-surface md:text-5xl">
                O que o agente entrega no dia a dia
              </h3>
            </motion.div>

            <div className="grid items-stretch gap-6 md:gap-8 lg:grid-cols-12">
              <motion.div
                initial={{ opacity: 0, y: 18 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={VIEWPORT}
                className="group flex flex-col justify-between rounded-[2rem] border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm transition-all hover:border-primary/30 md:p-10 lg:col-span-8"
              >
                <div>
                  <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl border border-secondary-container/20 bg-secondary-container/10 transition-transform group-hover:scale-110 md:mb-8 md:h-14 md:w-14">
                    <CheckCircle2 className="h-8 w-8 text-secondary-container" />
                  </div>
                  <h4 className="mb-4 font-headline text-2xl font-bold text-on-surface md:text-3xl">Resposta rastreavel</h4>
                  <p className="max-w-md text-base text-on-surface-variant md:text-lg">
                    Cada resposta e conectada a um trecho real dos seus arquivos.
                  </p>
                </div>

                <div className="mt-8 overflow-hidden rounded-2xl bg-surface-container-highest p-4 md:mt-12 md:p-6">
                  <div className="relative rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4 font-mono text-xs leading-6 text-on-surface shadow-[0_10px_40px_-20px_rgba(0,0,0,0.5)] md:p-6 md:text-sm">
                    <div className="absolute top-4 right-4 h-2 w-2 rounded-full bg-green-500 shadow-[0_0_10px_rgba(74,222,128,0.8)]" />
                    <p>"O prazo de entrega e de 30 dias corridos."</p>
                    <p className="mt-4 text-primary/80">Fonte: Contrato_servicos.pdf · pag. 4</p>
                  </div>
                </div>
              </motion.div>

              <div className="flex flex-col gap-6 md:gap-8 lg:col-span-4">
                <motion.div
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={VIEWPORT}
                  transition={{ delay: 0.1 }}
                  className="relative flex flex-1 flex-col justify-between overflow-hidden rounded-[2rem] border border-outline-variant/10 bg-surface-container-high p-6 md:p-8"
                >
                  <div className="absolute -right-4 -bottom-4 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
                  <div>
                    <CalendarDays className="mb-5 block h-9 w-9 text-secondary-container md:mb-6 md:h-10 md:w-10" />
                    <h4 className="mb-3 font-headline text-xl font-bold text-on-surface md:text-2xl">Agenda</h4>
                    <p className="text-sm text-on-surface-variant">Lembretes extraidos diretamente do contexto.</p>
                  </div>
                  <div className="mt-8 rounded-lg border border-primary/20 bg-primary/5 p-3 font-mono text-[11px]">
                    <span className="text-secondary-container">&gt; </span> Agendando: Revisao (15/10)
                  </div>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={VIEWPORT}
                  transition={{ delay: 0.2 }}
                  className="flex flex-1 flex-col justify-between rounded-[2rem] border border-outline-variant/20 bg-surface-container-highest p-6 md:p-8"
                >
                  <div>
                    <BookOpen className="mb-5 block h-9 w-9 text-primary md:mb-6 md:h-10 md:w-10" />
                    <h4 className="mb-3 font-headline text-xl font-bold text-on-surface md:text-2xl">Plano de estudos</h4>
                    <p className="text-sm text-on-surface-variant">Cronogramas de aprendizado estruturados automaticamente.</p>
                  </div>
                  <div className="mt-8 flex gap-2 overflow-hidden">
                    <div className="rounded-full border border-outline-variant/20 bg-surface-container-low px-3 py-1 text-[10px] font-bold text-on-surface shadow-sm">
                      Semana 1
                    </div>
                    <div className="rounded-full border border-outline-variant/20 bg-surface-container-low px-3 py-1 text-[10px] font-bold text-on-surface shadow-sm">
                      Semana 2
                    </div>
                  </div>
                </motion.div>
              </div>
            </div>
          </section>

          <section className="mx-auto mb-14 max-w-[1440px] px-4 py-8 sm:px-6 md:mb-20 md:px-12 md:py-12">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={VIEWPORT}
              className="relative flex flex-col gap-6 overflow-hidden rounded-[2rem] border border-outline-variant/10 bg-surface-container-high p-7 sm:p-9 lg:flex-row lg:items-end lg:justify-between"
            >
              <div className="pointer-events-none absolute inset-4 bg-primary/5 opacity-30 blur-3xl" />
              <div className="relative z-10 max-w-[36rem]">
                <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-primary">Comece agora</p>
                <h2 className="mt-4 font-headline text-[1.9rem] font-bold leading-[1.05] text-on-surface sm:text-[2.8rem]">
                  Crie a conta e suba seu primeiro documento.
                </h2>
                <p className="mt-4 text-sm leading-7 text-on-surface-variant sm:text-base">
                  Em minutos o agente ja responde perguntas sobre o seu material, com a fonte de cada informacao.
                </p>
              </div>

              <div className="relative z-10 flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
                <Link
                  to="/register"
                  className="flex w-full items-center justify-center rounded-full bg-primary px-7 py-3.5 font-headline font-bold text-on-primary shadow-[0_10px_30px_-5px_rgba(147,197,253,0.3)] transition-transform hover:-translate-y-1 sm:w-auto"
                >
                  Criar conta
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
                <Link
                  to="/login"
                  className="flex w-full items-center justify-center rounded-full px-6 py-3.5 font-headline font-bold text-on-surface transition-colors hover:bg-surface-container-highest sm:w-auto"
                >
                  Entrar
                </Link>
              </div>
            </motion.div>
          </section>
        </main>

        <div className="fixed inset-x-4 bottom-3 z-40 md:hidden">
          <div className="rounded-2xl border border-primary/30 bg-surface/95 p-2 shadow-[0_14px_40px_-14px_rgba(59,130,246,0.45)] backdrop-blur-xl">
            <Link
              to="/register"
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3.5 font-headline font-bold text-on-primary"
            >
              Comecar agora
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <footer className="mt-12 border-t border-outline-variant/10 bg-surface">
          <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-8 text-sm text-on-surface-variant sm:flex-row sm:items-center sm:justify-between sm:px-6 md:px-12">
            <p>© {new Date().getFullYear()} DocOps Agent. Agente de documentos com IA.</p>
            <div className="flex flex-wrap items-center gap-6">
              <a href="https://github.com/DocOps-Agent/DocOps_Agent" className="transition-colors hover:text-primary">
                GitHub
              </a>
              <a href="#" className="transition-colors hover:text-primary">
                Licenca MIT
              </a>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  )
}
