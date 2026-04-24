import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  AlertTriangle,
  BookOpen,
  Brain,
  CalendarDays,
  CheckSquare,
  Clock3,
  FileText,
  GraduationCap,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageShell } from '@/components/ui/page-shell'
import { apiClient, type DocItem, type StudyPlanDocResponse, type StudyPlanItem } from '@/api/client'
import { cn } from '@/lib/utils'
import { SectionIntro } from '@/onboarding/SectionIntro'

function formatDate(date: string) {
  const d = new Date(`${date}T00:00:00`)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

function daysUntil(date: string) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const d = new Date(`${date}T00:00:00`)
  const diff = Math.ceil((d.getTime() - today.getTime()) / (24 * 60 * 60 * 1000))
  return diff
}

function PlanTextModal({ titulo, planText, onClose }: { titulo: string; planText: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-1)] shadow-[0_24px_64px_rgba(0,0,0,0.45)]">
        <div className="flex shrink-0 items-center justify-between border-b border-[color:var(--ui-border-soft)] px-6 py-4">
          <div className="min-w-0">
            <p className="app-kicker">Plano Completo</p>
            <h2 className="truncate font-headline text-lg font-bold text-[color:var(--ui-text)]">{titulo}</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} className="text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          <div
            className="prose prose-invert prose-sm max-w-none
              prose-headings:font-headline prose-headings:tracking-tight prose-headings:text-[color:var(--ui-text)]
              prose-p:text-[color:var(--ui-text-dim)] prose-li:text-[color:var(--ui-text-dim)]
              prose-strong:text-[color:var(--ui-text)] prose-em:text-[color:var(--ui-text-meta)]
              prose-hr:border-[color:var(--ui-border-soft)]"
          >
            <ReactMarkdown>{planText}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}

function CreateStudyPlanDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [selectedDoc, setSelectedDoc] = useState('')
  const [hoursPerDay, setHoursPerDay] = useState(2)
  const [deadline, setDeadline] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return d.toISOString().slice(0, 10)
  })
  const [genFlashcards, setGenFlashcards] = useState(true)
  const [numCards, setNumCards] = useState(15)
  const [preferredTime, setPreferredTime] = useState('20:00')
  const [result, setResult] = useState<StudyPlanDocResponse | null>(null)
  const [expandPlan, setExpandPlan] = useState(false)
  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })
  const createMut = useMutation({
    mutationFn: () => apiClient.createStudyPlanFromDoc(selectedDoc, hoursPerDay, deadline, genFlashcards, numCards, preferredTime),
    onSuccess: data => {
      setResult(data)
      onCreated()
      toast.success('Plano de estudos criado com sucesso.')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao criar plano'),
  })
  const today = new Date().toISOString().slice(0, 10)
  const estimatedSessions = Math.max(1, daysUntil(deadline))
  return (
    <>
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
        <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-bg)] shadow-[0_24px_64px_rgba(0,0,0,0.45)]">
          <div className="flex shrink-0 items-center justify-between border-b border-[color:var(--ui-border-soft)] px-6 py-5">
            <div>
              <p className="app-kicker">Research {'>'} Novo Plano</p>
              <h2 className="font-headline text-xl font-bold text-[color:var(--ui-text)]">Novo Plano de Estudos</h2>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} className="text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-8">
            {!result && !createMut.isPending && (
              <div className="mb-8">
                <h3 className="font-headline text-4xl font-extrabold tracking-tight text-[color:var(--ui-text)]">Novo Plano de Estudos</h3>
                <p className="mt-3 max-w-3xl text-lg text-[color:var(--ui-text-dim)]">
                  Defina os parametros do seu agente de aprendizado para sintetizar documentos complexos em um cronograma de execucao otimizado.
                </p>
              </div>
            )}
            <div className="grid grid-cols-12 gap-6">
              <div className="col-span-12 lg:col-span-8">
                <div className="space-y-5">
                  {!result && !createMut.isPending && (
                    <>
                      <section className="relative overflow-hidden rounded-xl bg-[color:var(--ui-surface-1)] p-6 sm:p-8">
                        <div className="absolute -right-24 -top-24 h-56 w-56 rounded-full bg-[color:var(--ui-accent)]/8 blur-3xl" />
                        <div className="relative z-10 grid grid-cols-1 gap-6 md:grid-cols-2">
                          <div className="md:col-span-2">
                            <label className="mb-3 block text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Documento Fonte</label>
                            <select
                              value={selectedDoc}
                              onChange={e => setSelectedDoc(e.target.value)}
                              className="w-full rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-bg)] px-4 py-3.5 text-sm font-medium text-[color:var(--ui-text)] outline-none transition-colors focus:border-[color:var(--ui-accent)]"
                            >
                              <option value="">Selecione um documento indexado</option>
                              {(docs ?? []).map(d => (
                                <option key={d.file_name} value={d.file_name}>
                                  {d.file_name}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="md:col-span-1">
                            <div className="mb-4 flex items-end justify-between">
                              <label className="block text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Horas de estudo por dia</label>
                              <span className="font-headline text-3xl font-extrabold text-[color:var(--ui-accent)]">{hoursPerDay}h</span>
                            </div>
                            <input
                              type="range"
                              min={1}
                              max={12}
                              step={0.5}
                              value={hoursPerDay}
                              onChange={e => setHoursPerDay(Number(e.target.value))}
                              className="w-full accent-sky-400"
                            />
                            <div className="mt-2 flex justify-between text-[10px] font-mono text-[color:var(--ui-text-meta)]/60">
                              <span>1H</span>
                              <span>6H</span>
                              <span>12H</span>
                            </div>
                          </div>
                          <div className="md:col-span-1">
                            <label className="mb-3 block text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Horario preferido</label>
                            <input
                              type="time"
                              value={preferredTime}
                              onChange={e => setPreferredTime(e.target.value)}
                              className="w-full rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-bg)] px-4 py-3.5 text-sm font-medium text-[color:var(--ui-text)] outline-none transition-colors focus:border-[color:var(--ui-accent)]"
                            />
                          </div>
                          <div className="md:col-span-2">
                            <label className="mb-3 block text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Prazo final desejado</label>
                            <input
                              type="date"
                              value={deadline}
                              min={today}
                              onChange={e => setDeadline(e.target.value)}
                              className="w-full rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-bg)] px-4 py-3.5 text-sm font-medium text-[color:var(--ui-text)] outline-none transition-colors focus:border-[color:var(--ui-accent)]"
                            />
                          </div>
                        </div>
                      </section>
                      <div className="flex flex-wrap items-center justify-between gap-4 p-2">
                        <div className="flex items-center gap-2.5 text-xs text-[color:var(--ui-text-meta)]">
                          <span className="h-2 w-2 rounded-full bg-amber-300 shadow-[0_0_8px_rgba(255,217,174,0.7)]" />
                          Agente pronto para processamento heuristico
                        </div>
                        <Button
                          onClick={() => createMut.mutate()}
                          disabled={!selectedDoc || !deadline}
                          className="bg-gradient-to-br from-[color:var(--ui-accent)] to-[#90caf9] px-8 py-6 text-lg font-bold text-[color:var(--ui-bg)] hover:brightness-110"
                        >
                          Criar Plano de Estudos
                          <Plus className="ml-2 h-4 w-4" />
                        </Button>
                      </div>
                    </>
                  )}
                  {createMut.isPending && (
                    <div className="flex flex-col items-center justify-center gap-3 py-16">
                      <div className="relative">
                        <div className="h-10 w-10 animate-ping rounded-full bg-amber-300/25" />
                        <div className="absolute inset-0 flex items-center justify-center">
                          <Brain className="h-5 w-5 text-amber-300" />
                        </div>
                      </div>
                      <p className="font-headline text-base font-semibold text-[color:var(--ui-text)]">Gerando plano personalizado...</p>
                      <p className="text-sm text-[color:var(--ui-text-meta)]">Criando sessoes, tarefas e flashcards.</p>
                    </div>
                  )}
                  {result && (
                    <div className="space-y-4 rounded-xl bg-[color:var(--ui-surface-1)] p-5">
                      <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-xl bg-emerald-500/10 p-3 text-center">
                          <p className="text-[11px] text-emerald-300">Tarefas</p>
                          <p className="text-xl font-bold text-emerald-200">{result.tasks_created}</p>
                        </div>
                        <div className="rounded-xl bg-sky-500/10 p-3 text-center">
                          <p className="text-[11px] text-sky-300">Sessoes</p>
                          <p className="text-xl font-bold text-sky-200">{result.sessions_count}</p>
                        </div>
                        <div className="rounded-xl bg-violet-500/10 p-3 text-center">
                          <p className="text-[11px] text-violet-300">Flashcards</p>
                          <p className="text-xl font-bold text-violet-200">{result.deck_id ? numCards : '-'}</p>
                        </div>
                      </div>
                      {result.conflicts?.length > 0 && (
                        <div className="space-y-2 rounded-xl bg-amber-500/10 p-3">
                          <p className="flex items-center gap-1 text-xs font-semibold text-amber-300">
                            <AlertTriangle className="h-3 w-3" />
                            {result.conflicts.length} conflito(s) detectado(s)
                          </p>
                          {result.conflicts.map((c, i) => (
                            <p key={i} className="text-xs text-[color:var(--ui-text-dim)]">
                              {c.date} - {c.session_time} conflita com <strong className="text-amber-300">{c.conflicting_with}</strong> ({c.conflicting_time})
                            </p>
                          ))}
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2 text-xs">
                        <a href="/tasks" className="rounded-full bg-[color:var(--ui-surface-2)] px-3 py-1 text-emerald-300 hover:bg-[color:var(--ui-surface-3)]">
                          Ver Tarefas
                        </a>
                        <a href="/schedule" className="rounded-full bg-[color:var(--ui-surface-2)] px-3 py-1 text-sky-300 hover:bg-[color:var(--ui-surface-3)]">
                          Ver Calendario
                        </a>
                        {result.deck_id && (
                          <a href="/flashcards" className="rounded-full bg-[color:var(--ui-surface-2)] px-3 py-1 text-violet-300 hover:bg-[color:var(--ui-surface-3)]">
                            Ver Flashcards
                          </a>
                        )}
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => setExpandPlan(true)}
                        className="w-full border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-surface-3)]"
                      >
                        <FileText className="mr-2 h-4 w-4" />
                        Ver Plano Completo
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              <div className="col-span-12 space-y-6 lg:col-span-4">
                {!result && !createMut.isPending && (
                  <>
                    <div className="rounded-xl border border-[color:var(--ui-border-soft)]/30 bg-[color:var(--ui-surface-2)] p-6">
                      <div className="mb-8 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckSquare className="h-4 w-4 text-[color:var(--ui-accent)]" />
                          <span className="font-headline text-base font-bold text-[color:var(--ui-text)]">Gerar Flashcards</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setGenFlashcards(v => !v)}
                          className={cn(
                            'relative h-6 w-12 rounded-full transition-colors',
                            genFlashcards ? 'bg-[color:var(--ui-accent)]/35' : 'bg-[color:var(--ui-bg)]'
                          )}
                        >
                          <span
                            className={cn(
                              'absolute top-[2px] h-5 w-5 rounded-full transition-transform',
                              genFlashcards ? 'left-[26px] bg-[color:var(--ui-accent)]' : 'left-[2px] bg-[color:var(--ui-text-meta)]'
                            )}
                          />
                        </button>
                      </div>
                      <div className="space-y-6">
                        <div>
                          <div className="mb-2 flex items-center justify-between">
                            <span className="text-xs font-bold uppercase tracking-[0.12em] text-[color:var(--ui-text-meta)]">Quantidade</span>
                            <span className="font-mono text-sm text-[color:var(--ui-text)]">{numCards} cards</span>
                          </div>
                          <input
                            type="range"
                            min={10}
                            max={100}
                            step={2}
                            value={numCards}
                            disabled={!genFlashcards}
                            onChange={e => setNumCards(Number(e.target.value))}
                            className="w-full accent-sky-400 disabled:opacity-40"
                          />
                        </div>
                        <div className="rounded-lg bg-[color:var(--ui-bg)] p-4">
                          <p className="text-xs leading-relaxed text-[color:var(--ui-text-dim)]">
                            <span className="font-bold text-[color:var(--ui-accent)]">Dica:</span> o agente utilizara repeticao espacada (SRS) para otimizar a retencao dos cards baseados no documento.
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-6">
                      <h4 className="mb-3 text-[10px] font-bold uppercase tracking-[0.2em] text-[color:var(--ui-text-meta)]/70">Resumo da Estrategia</h4>
                      <div className="space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[color:var(--ui-surface-2)]">
                            <Sparkles className="h-4 w-4 text-amber-300" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-[color:var(--ui-text)]">Carga Cognitiva</p>
                            <p className="text-xs text-[color:var(--ui-text-meta)]">Otimizada para {hoursPerDay}h/dia</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[color:var(--ui-surface-2)]">
                            <CalendarDays className="h-4 w-4 text-[color:var(--ui-accent)]" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-[color:var(--ui-text)]">Iteracoes</p>
                            <p className="text-xs text-[color:var(--ui-text-meta)]">{estimatedSessions} sessoes previstas</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      {expandPlan && result && <PlanTextModal titulo={result.titulo ?? 'Plano de Estudos'} planText={result.plan_text} onClose={() => setExpandPlan(false)} />}
    </>
  )
}

function PlanCard({ plan, onDelete }: { plan: StudyPlanItem; onDelete: (id: number) => void }) {
  const [showPlan, setShowPlan] = useState(false)
  const deadlineDiff = daysUntil(plan.deadline_date)
  const isExpired = deadlineDiff < 0
  const urgencyClass = isExpired ? 'text-rose-300' : deadlineDiff <= 3 ? 'text-amber-300' : 'text-emerald-300'

  return (
    <>
      <Card className="rounded-2xl border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] shadow-none transition-colors hover:border-[color:var(--ui-border-strong)]">
        <CardContent className="space-y-4 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-headline text-base font-bold text-[color:var(--ui-text)]">{plan.titulo}</p>
              <p className="mt-1 text-xs text-[color:var(--ui-text-meta)]">
                <BookOpen className="mr-1 inline h-3 w-3" />
                {plan.doc_name}
              </p>
            </div>
            <button
              onClick={() => onDelete(plan.id)}
              className="rounded-lg p-2 text-[color:var(--ui-text-meta)] transition-colors hover:bg-rose-500/15 hover:text-rose-300"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>

          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className={cn('rounded-full bg-[color:var(--ui-surface-2)] px-2.5 py-1 font-medium', urgencyClass)}>
              <Clock3 className="mr-1 inline h-3 w-3" />
              {isExpired ? 'Prazo expirado' : `${deadlineDiff} dia(s) restantes`}
            </span>
            <span className="rounded-full bg-[color:var(--ui-surface-2)] px-2.5 py-1 text-[color:var(--ui-text-dim)]">{formatDate(plan.deadline_date)}</span>
            <span className="rounded-full bg-[color:var(--ui-surface-2)] px-2.5 py-1 text-[color:var(--ui-text-dim)]">{plan.hours_per_day}h/dia</span>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-xl bg-emerald-500/10 p-2">
              <p className="font-semibold text-emerald-200">{plan.tasks_created}</p>
              <p className="text-emerald-300/80">tarefas</p>
            </div>
            <div className="rounded-xl bg-sky-500/10 p-2">
              <p className="font-semibold text-sky-200">{plan.sessions_count}</p>
              <p className="text-sky-300/80">sessões</p>
            </div>
            <div className="rounded-xl bg-violet-500/10 p-2">
              <p className="font-semibold text-violet-200">{plan.deck_id ? 'sim' : 'não'}</p>
              <p className="text-violet-300/80">deck</p>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowPlan(true)}
            className="w-full border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-surface-3)]"
          >
            <FileText className="mr-2 h-3.5 w-3.5" />
            Ver Plano Completo
          </Button>
        </CardContent>
      </Card>
      {showPlan && <PlanTextModal titulo={plan.titulo} planText={plan.plan_text} onClose={() => setShowPlan(false)} />}
    </>
  )
}

export function StudyPlan() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)

  const { data: plans, isLoading, error } = useQuery<StudyPlanItem[]>({
    queryKey: ['study-plans'],
    queryFn: apiClient.listStudyPlans,
    retry: 1,
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteStudyPlan(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['study-plans'] })
      toast.success('Plano removido.')
    },
    onError: () => toast.error('Erro ao remover plano.'),
  })

  function handleDelete(id: number) {
    if (confirm('Remover este plano de estudos?')) deleteMut.mutate(id)
  }

  const stats = useMemo(() => {
    const items = plans ?? []
    return {
      totalPlans: items.length,
      totalTasks: items.reduce((acc, item) => acc + item.tasks_created, 0),
      totalSessions: items.reduce((acc, item) => acc + item.sessions_count, 0),
      withDeck: items.filter(item => item.deck_id).length,
    }
  }, [plans])

  return (
    <PageShell className="space-y-6">
      <SectionIntro sectionId="study" />
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="app-kicker">Sovereign Architect</p>
          <h1 className="font-headline text-3xl font-extrabold tracking-tight text-[color:var(--ui-text)]">Plano de Estudos</h1>
          <p className="mt-1 text-sm text-[color:var(--ui-text-dim)]">Transforme seus documentos em trilhas de aprendizado acionáveis.</p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="bg-gradient-to-r from-[color:var(--ui-accent)] to-[#73b2f3] text-[color:var(--ui-bg)] hover:brightness-110">
          <Plus className="mr-2 h-4 w-4" />
          Novo Plano
        </Button>
      </header>

      {error && <div className="rounded-xl bg-rose-500/15 px-4 py-3 text-sm text-rose-300">Erro ao carregar planos.</div>}

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl bg-[color:var(--ui-surface-2)]" />
          ))}
        </div>
      )}

      {!isLoading && (!plans || plans.length === 0) && !error && (
        <section className="relative overflow-hidden rounded-2xl bg-[color:var(--ui-bg)]">
          <div className="grid grid-cols-1 items-center gap-10 p-6 lg:grid-cols-12 lg:p-10">
            <div className="relative aspect-square lg:col-span-5">
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-[color:var(--ui-accent)]/10 to-transparent" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="relative flex h-64 w-64 rotate-12 items-center justify-center overflow-hidden rounded-3xl bg-[color:var(--ui-surface-1)] shadow-[0_24px_50px_rgba(0,0,0,0.42)]">
                  <div
                    className="absolute inset-0 opacity-20"
                    style={{
                      backgroundImage: 'radial-gradient(rgba(197,227,255,0.95) 0.5px, transparent 0.5px)',
                      backgroundSize: '10px 10px',
                    }}
                  />
                  <div className="-rotate-12 text-center">
                    <GraduationCap className="mx-auto h-14 w-14 text-[color:var(--ui-accent)]/50" />
                    <div className="mt-6 flex justify-center gap-1">
                      <span className="h-1 w-10 rounded-full bg-[color:var(--ui-accent)]" />
                      <span className="h-1 w-14 rounded-full bg-[color:var(--ui-border-strong)]" />
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute left-1/2 top-1/2">
                <div className="absolute -left-2 -top-2 h-4 w-4 animate-ping rounded-full bg-amber-300/25" />
                <div className="h-2 w-2 rounded-full bg-amber-300" />
              </div>
            </div>

            <div className="space-y-6 lg:col-span-7">
              <span className="inline-flex rounded-full bg-[color:var(--ui-surface-2)] px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[color:var(--ui-accent)]">
                Sovereign Architect
              </span>
              <h2 className="font-headline text-4xl font-extrabold leading-[1.1] tracking-tight text-[color:var(--ui-text)]">
                Estruture seu
                <br />
                <span className="text-[color:var(--ui-accent)]">legado intelectual.</span>
              </h2>
              <p className="max-w-xl text-base leading-relaxed text-[color:var(--ui-text-dim)]">
                O DocOps Agent cria roteiros de estudo com tarefas, sessões em calendário e flashcards, tudo conectado aos seus documentos indexados.
              </p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-4">
                  <p className="font-headline text-sm font-bold text-[color:var(--ui-text)]">Mapeamento IA</p>
                  <p className="mt-1 text-xs text-[color:var(--ui-text-meta)]">Análise de tópicos e lacunas para priorizar estudo.</p>
                </div>
                <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-4">
                  <p className="font-headline text-sm font-bold text-[color:var(--ui-text)]">Ritmo Adaptativo</p>
                  <p className="mt-1 text-xs text-[color:var(--ui-text-meta)]">Carga diária calibrada por prazo e disponibilidade.</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button onClick={() => setShowCreate(true)} className="bg-gradient-to-r from-[color:var(--ui-accent)] to-[#73b2f3] text-[color:var(--ui-bg)] hover:brightness-110">
                  <Plus className="mr-2 h-4 w-4" />
                  Criar Novo Plano
                </Button>
                <a
                  href="/docs"
                  className="inline-flex items-center rounded-lg bg-[color:var(--ui-surface-2)] px-4 py-2 text-sm font-medium text-[color:var(--ui-text)] transition-colors hover:bg-[color:var(--ui-surface-3)]"
                >
                  Ver Documentos
                </a>
              </div>
            </div>
          </div>
        </section>
      )}

      {!isLoading && plans && plans.length > 0 && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-3">
              <p className="text-[11px] text-[color:var(--ui-text-meta)]">Planos Ativos</p>
              <p className="mt-1 font-headline text-2xl font-bold text-[color:var(--ui-text)]">{stats.totalPlans}</p>
            </div>
            <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-3">
              <p className="text-[11px] text-[color:var(--ui-text-meta)]">Tarefas</p>
              <p className="mt-1 font-headline text-2xl font-bold text-emerald-300">{stats.totalTasks}</p>
            </div>
            <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-3">
              <p className="text-[11px] text-[color:var(--ui-text-meta)]">Sessões</p>
              <p className="mt-1 font-headline text-2xl font-bold text-sky-300">{stats.totalSessions}</p>
            </div>
            <div className="rounded-xl bg-[color:var(--ui-surface-1)] p-3">
              <p className="text-[11px] text-[color:var(--ui-text-meta)]">Com Flashcards</p>
              <p className="mt-1 font-headline text-2xl font-bold text-violet-300">{stats.withDeck}</p>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {plans.map(plan => (
              <PlanCard key={plan.id} plan={plan} onDelete={handleDelete} />
            ))}
          </section>
        </>
      )}

      {showCreate && (
        <CreateStudyPlanDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => qc.invalidateQueries({ queryKey: ['study-plans'] })}
        />
      )}

      {!isLoading && (
        <footer className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--ui-surface-1)] px-4 py-3">
          <div className="flex flex-wrap gap-6">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Atividade</p>
              <p className="text-xs text-[color:var(--ui-text-dim)]">{plans && plans.length > 0 ? 'Pipeline ativo' : 'Sistemas em standby'}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Planos</p>
              <p className="text-xs text-[color:var(--ui-text-dim)]">{stats.totalPlans}/10 Premium</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-[color:var(--ui-text-meta)]">
            <span className="h-2 w-2 rounded-full bg-[color:var(--ui-accent)]" />
            Neural Engine Syncing
          </div>
        </footer>
      )}
    </PageShell>
  )
}

