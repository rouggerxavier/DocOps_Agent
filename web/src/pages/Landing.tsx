import { Link } from 'react-router-dom'
import { motion, MotionConfig } from 'framer-motion'
import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, FileText, Layers, Shield } from 'lucide-react'
import { HeroFuturistic } from '@/components/HeroFuturistic'

const EASE = [0.2, 0.8, 0.2, 1] as const
const VIEWPORT = { once: true, margin: '-48px' } as const

export function Landing() {
  return (
    <MotionConfig reducedMotion="user">
      <div className="bg-surface text-on-surface font-body selection:bg-secondary-container selection:text-on-secondary-container min-h-screen">
        
        {/* TopNavBar */}
        <header className="fixed top-0 left-0 w-full z-50 bg-surface/80 backdrop-blur-xl border-b border-white/5">
          <div className="flex justify-between items-center px-6 md:px-12 py-6 max-w-[1440px] mx-auto">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-extrabold tracking-tighter text-primary">DocOps Agent</span>
            </div>
            <nav className="hidden md:flex items-center gap-8">
              <a className="text-on-surface/70 font-headline font-semibold tracking-tight hover:text-primary transition-all duration-300" href="#features">Funcionalidades</a>
              <a className="text-on-surface/70 font-headline font-semibold tracking-tight hover:text-primary transition-all duration-300" href="#how-it-works">Como funciona</a>
            </nav>
            <div className="flex items-center gap-4">
              <Link to="/login" className="px-5 py-2 text-on-surface font-semibold font-headline transition-transform active:scale-95">Entrar</Link>
              <Link to="/register" className="px-6 py-2 bg-primary text-on-primary rounded-xl font-headline font-bold shadow-lg shadow-primary/20 hover:shadow-primary/40 transition-all duration-300 active:scale-95">Criar conta</Link>
            </div>
          </div>
        </header>

        <main className="pt-32">
          {/* Hero Section */}
          <section className="px-6 md:px-12 max-w-[1440px] mx-auto mb-32">
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: EASE }} className="space-y-8">
                <div className="inline-flex items-center gap-2 px-3 py-1 bg-surface-container-high rounded-full border-l-4 border-secondary">
                  <Shield className="text-secondary w-4 h-4" />
                  <span className="text-[11px] font-bold tracking-widest text-secondary font-label uppercase">AGENTE DE DOCUMENTOS COM IA</span>
                </div>
                <h1 className="text-5xl md:text-7xl font-extrabold font-headline leading-[1.1] text-on-surface tracking-tight">
                  Os documentos tem a resposta. <span className="text-secondary">Com fonte.</span>
                </h1>
                <p className="text-lg md:text-xl text-on-surface-variant leading-relaxed max-w-xl">
                  Suba PDFs e textos, faça perguntas em linguagem natural e receba respostas rastreáveis. O DocOps Agent ainda cria planos de estudo e gerencia sua agenda pelo chat.
                </p>
                <div className="flex flex-wrap gap-4">
                  <Link to="/register" className="px-8 py-4 bg-primary text-on-primary rounded-xl font-headline font-bold text-lg shadow-[0_10px_40px_-10px_rgba(147,197,253,0.3)] transition-all duration-300 hover:-translate-y-1">Criar conta</Link>
                  <a href="#how-it-works" className="px-8 py-4 bg-surface-container-highest text-on-surface rounded-xl font-headline font-bold text-lg border-b-2 border-outline-variant/30 hover:bg-surface-container transition-all duration-300">Ver como funciona</a>
                </div>
                <div className="flex flex-wrap gap-6 pt-4">
                  <div className="flex items-center gap-2 opacity-70">
                    <FileText className="text-primary w-5 h-5" />
                    <span className="text-sm font-semibold">PDF, Word, texto</span>
                  </div>
                  <div className="flex items-center gap-2 opacity-70">
                    <Layers className="text-primary w-5 h-5" />
                    <span className="text-sm font-semibold">Execução local</span>
                  </div>
                  <div className="flex items-center gap-2 opacity-70">
                    <CalendarDays className="text-primary w-5 h-5" />
                    <span className="text-sm font-semibold">Agenda integrada</span>
                  </div>
                </div>
              </motion.div>
              
              <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.08, ease: EASE }} className="relative group h-full min-h-[400px]">
                <div className="absolute -inset-4 bg-primary/10 rounded-[2rem] blur-3xl"></div>
                <div className="relative w-full h-[400px] sm:h-[500px] lg:h-[620px] bg-surface-container-lowest rounded-[2rem] border border-outline-variant/20 flex items-center justify-center overflow-hidden">
                  <HeroFuturistic className="w-full h-full" interactive fallbackMode="still" />
                  <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 to-transparent pointer-events-none"></div>
                </div>
              </motion.div>
            </div>
          </section>

          {/* Steps Section */}
          <section id="how-it-works" className="bg-surface-container py-32 px-6 md:px-12 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-1/3 h-full bg-gradient-to-l from-primary/5 to-transparent"></div>
            <div className="max-w-[1440px] mx-auto relative z-10">
              <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="mb-20">
                <h2 className="text-sm font-bold text-secondary tracking-[0.3em] uppercase mb-4">Como funciona</h2>
                <h3 className="text-4xl md:text-5xl font-headline font-extrabold text-on-surface max-w-2xl">Do documento à resposta em três passos</h3>
              </motion.div>
              <div className="grid md:grid-cols-3 gap-12">
                {[
                  { n: '01', title: 'Suba seus documentos', desc: 'PDF, Word ou texto puro. Arraste e solte seus arquivos em uma infraestrutura segura e privada.' },
                  { n: '02', title: 'Pergunte em linguagem natural', desc: 'A resposta vem com a fonte exata. Clique na referência para abrir o documento no parágrafo citado.' },
                  { n: '03', title: 'Planeje e agende', desc: 'Peça um plano de estudos ou extraia datas importantes. O DocOps cria cronogramas automaticamente.' },
                ].map((step, idx) => (
                  <motion.div key={step.n} initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} transition={{ delay: idx * 0.1 }} className="space-y-6 group">
                    <div className="text-6xl font-extrabold font-headline text-primary/20 group-hover:text-primary transition-colors">{step.n}</div>
                    <h4 className="text-2xl font-bold font-headline text-on-surface">{step.title}</h4>
                    <p className="text-on-surface-variant leading-relaxed">{step.desc}</p>
                    <div className="h-1 w-12 bg-secondary group-hover:w-full transition-all duration-500"></div>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          {/* Features/Proof Section */}
          <section id="features" className="py-32 px-6 md:px-12 max-w-[1440px] mx-auto">
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="text-center mb-24">
              <h2 className="text-sm font-bold text-secondary tracking-[0.3em] uppercase mb-4">Na prática</h2>
              <h3 className="text-4xl md:text-5xl font-headline font-extrabold text-on-surface">O que o agente entrega no dia a dia</h3>
            </motion.div>
            <div className="grid lg:grid-cols-12 gap-8 items-stretch">
              
              {/* Main Feature: Bento Style */}
              <motion.div initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="lg:col-span-8 bg-surface-container-low p-10 rounded-[2rem] border border-outline-variant/10 shadow-sm flex flex-col justify-between group hover:border-primary/30 transition-all">
                <div>
                  <div className="w-14 h-14 bg-secondary-container/10 border border-secondary-container/20 rounded-2xl flex items-center justify-center mb-8 group-hover:scale-110 transition-transform">
                    <CheckCircle2 className="text-secondary-container w-8 h-8" />
                  </div>
                  <h4 className="text-3xl font-bold font-headline text-on-surface mb-4">Resposta rastreável</h4>
                  <p className="text-on-surface-variant text-lg max-w-md">Chega de alucinações de IA. Cada palavra dita pelo DocOps Agent é vinculada a um fragmento real dos seus arquivos.</p>
                </div>
                <div className="mt-12 bg-surface-container-highest rounded-2xl p-6 overflow-hidden">
                  <div className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-on-surface font-mono text-sm leading-6 relative shadow-[0_10px_40px_-20px_rgba(0,0,0,0.5)]">
                    <div className="absolute top-4 right-4 w-2 h-2 bg-green-500 rounded-full shadow-[0_0_10px_rgba(74,222,128,0.8)]"></div>
                    <p>"O prazo de entrega é de 30 dias corridos."</p>
                    <p className="mt-4 text-primary opacity-80">Fonte: Contrato_servicos.pdf · pag. 4</p>
                  </div>
                </div>
              </motion.div>

              <div className="lg:col-span-4 flex flex-col gap-8">
                {/* Feature Card 1 */}
                <motion.div initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} transition={{ delay: 0.1 }} className="flex-1 bg-surface-container-high p-8 rounded-[2rem] border border-outline-variant/10 flex flex-col justify-between group overflow-hidden relative">
                  <div className="absolute -right-4 -bottom-4 w-32 h-32 bg-primary/10 rounded-full blur-2xl"></div>
                  <div>
                    <CalendarDays className="text-secondary-container w-10 h-10 mb-6 block" />
                    <h4 className="text-2xl font-bold font-headline text-on-surface mb-3">Agenda</h4>
                    <p className="text-on-surface-variant text-sm">Lembretes extraídos diretamente do contexto.</p>
                  </div>
                  <div className="mt-8 bg-primary/5 p-3 rounded-lg text-[11px] font-mono border border-primary/20">
                    <span className="text-secondary-container">&gt; </span> Agendando: Revisão (15/10)
                  </div>
                </motion.div>

                {/* Feature Card 2 */}
                <motion.div initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} transition={{ delay: 0.2 }} className="flex-1 bg-surface-container-highest p-8 rounded-[2rem] flex flex-col justify-between group border border-outline-variant/20">
                  <div>
                    <BookOpen className="text-primary w-10 h-10 mb-6 block" />
                    <h4 className="text-2xl font-bold font-headline text-on-surface mb-3">Plano de estudos</h4>
                    <p className="text-on-surface-variant text-sm">Cronogramas de aprendizado estruturados automaticamente.</p>
                  </div>
                  <div className="mt-8 flex gap-2 overflow-hidden">
                    <div className="px-3 py-1 bg-surface-container-low border border-outline-variant/20 rounded-full text-[10px] font-bold text-on-surface shadow-sm">Semana 1</div>
                    <div className="px-3 py-1 bg-surface-container-low border border-outline-variant/20 rounded-full text-[10px] font-bold text-on-surface shadow-sm">Semana 2</div>
                  </div>
                </motion.div>
              </div>
            </div>
          </section>

          {/* Bottom CTA (Refactored to look horizontal like the old one) */}
          <section className="py-12 px-6 md:px-12 max-w-[1440px] mx-auto mb-20">
            <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={VIEWPORT} className="flex flex-col gap-6 rounded-[2rem] bg-surface-container-high border border-outline-variant/10 p-7 sm:p-9 lg:flex-row lg:items-end lg:justify-between relative overflow-hidden">
              <div className="absolute inset-4 bg-primary/5 blur-3xl opacity-30 pointer-events-none"></div>
              <div className="relative z-10 max-w-[36rem]">
                <p className="text-[11px] uppercase tracking-[0.2em] text-primary font-bold">Comece agora</p>
                <h2 className="mt-4 text-3xl sm:text-[2.8rem] leading-[1.05] font-headline font-bold text-on-surface">
                  Crie a conta e suba seu primeiro documento.
                </h2>
                <p className="mt-4 text-sm leading-7 text-on-surface-variant sm:text-base">
                  Em minutos o agente já responde perguntas sobre o seu material, com a fonte de cada informação.
                </p>
              </div>

              <div className="relative z-10 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Link to="/register" className="px-7 py-3.5 bg-primary text-on-primary rounded-full font-headline font-bold shadow-[0_10px_30px_-5px_rgba(147,197,253,0.3)] hover:-translate-y-1 transition-transform flex items-center justify-center">
                   Criar conta
                   <ArrowRight className="ml-2 w-4 h-4" />
                </Link>
                <Link to="/login" className="px-6 py-3.5 text-on-surface rounded-full font-headline font-bold hover:bg-surface-container-highest transition-colors flex items-center justify-center">
                  Entrar
                </Link>
              </div>
            </motion.div>
          </section>
        </main>

        {/* Footer (Aligned like the old one) */}
        <footer className="border-t border-outline-variant/10 mt-12 bg-surface">
          <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-6 py-8 text-sm text-on-surface-variant sm:flex-row sm:items-center sm:justify-between md:px-12">
            <p>© {new Date().getFullYear()} DocOps Agent. Agente de documentos com IA.</p>
            <div className="flex flex-wrap items-center gap-6">
              <a href="https://github.com/DocOps-Agent/DocOps_Agent" className="hover:text-primary transition-colors">GitHub</a>
              <a href="#" className="hover:text-primary transition-colors">Licença MIT</a>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  )
}
