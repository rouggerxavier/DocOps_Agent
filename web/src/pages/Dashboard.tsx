import { useEffect, useState } from 'react'
import type { ComponentType, ReactNode } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  Clock3,
  FileText,
  Layers,
  MessageSquare,
  NotebookPen,
  RefreshCw,
  ScrollText,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  apiClient,
  type ArtifactItem,
  type BriefingResponse,
  type CalendarOverview,
  type DailyQuestionResponse,
  type DocItem,
  type EvaluateAnswerResponse,
} from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { cn } from '@/lib/utils'
import { PageShell } from '@/components/ui/page-shell'

type IconType = ComponentType<{ className?: string }>

const SCORE_STYLE: Record<string, string> = {
  excelente: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  bom: 'border-[color:var(--ui-accent)]/40 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
  parcial: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  incorreto: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  sem_resposta: 'border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-dim)]',
}

const SCORE_LABEL: Record<string, string> = {
  excelente: 'Excelente',
  bom: 'Bom',
  parcial: 'Parcial',
  incorreto: 'Incorreto',
  sem_resposta: 'Sem resposta',
}

function SurfaceCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <Card className={cn(
      'rounded-[1.15rem] border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] shadow-none',
      className,
    )}>
      <CardContent className="p-5">{children}</CardContent>
    </Card>
  )
}

function MetricCard({
  title,
  value,
  icon: Icon,
  description,
  loading,
  tone = 'primary',
}: {
  title: string
  value: string | number
  icon: IconType
  description: string
  loading?: boolean
  tone?: 'primary' | 'tertiary' | 'neutral'
}) {
  const toneMap: Record<string, string> = {
    primary: 'text-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)]',
    tertiary: 'text-amber-300 bg-amber-500/10',
    neutral: 'text-[color:var(--ui-text-dim)] bg-[color:var(--ui-surface-2)]',
  }

  return (
    <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className={cn('flex h-11 w-11 items-center justify-center rounded-xl', toneMap[tone])}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">{title}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20 rounded-md" />
      ) : (
        <p className="mt-2 font-headline text-4xl font-bold leading-none text-[color:var(--ui-text)]">{value}</p>
      )}
      <p className="mt-3 text-xs text-[color:var(--ui-text-dim)]">{description}</p>
    </SurfaceCard>
  )
}

function QuickActionTile({
  to,
  icon: Icon,
  label,
  tone = 'primary',
}: {
  to: string
  icon: IconType
  label: string
  tone?: 'primary' | 'tertiary' | 'neutral'
}) {
  const toneClasses: Record<string, string> = {
    primary: 'text-[color:var(--ui-accent)]',
    tertiary: 'text-amber-300',
    neutral: 'text-[color:var(--ui-text-dim)]',
  }

  return (
    <Link
      to={to}
      className="group cursor-pointer rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] p-4 transition-colors duration-200 hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-3)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)]"
    >
      <Icon className={cn('h-5 w-5 transition-transform duration-200 group-hover:scale-110', toneClasses[tone])} />
      <p className="mt-2 text-sm font-semibold text-[color:var(--ui-text)]">{label}</p>
    </Link>
  )
}

function OnboardingSteps() {
  const steps = [
    { n: 1, label: 'Inserir documento', sub: 'PDF, markdown ou TXT', to: '/ingest', cta: 'Inserir' },
    { n: 2, label: 'Conversar no chat', sub: 'Perguntas com grounding', to: '/chat', cta: 'Abrir chat' },
    { n: 3, label: 'Salvar artefatos', sub: 'Resumo, checklist e notas', to: '/artifacts', cta: 'Ver artefatos' },
  ]

  return (
    <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
      <div className="mb-6 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[color:var(--ui-accent)]" />
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">Primeiros passos</p>
      </div>
      <div className="space-y-4">
        {steps.map((step) => (
          <div key={step.n} className="flex items-center gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--ui-surface-3)] text-xs font-semibold text-[color:var(--ui-text-dim)]">
              {step.n}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[color:var(--ui-text)]">{step.label}</p>
              <p className="text-xs text-[color:var(--ui-text-meta)]">{step.sub}</p>
            </div>
            <Button variant="ghost" size="sm" asChild className="h-8 px-2 text-xs text-[color:var(--ui-accent)]">
              <Link to={step.to}>
                {step.cta}
                <ChevronRight className="h-3 w-3" />
              </Link>
            </Button>
          </div>
        ))}
      </div>
    </SurfaceCard>
  )
}

function DailyQuestionPanel({
  data,
  loading,
}: {
  data: DailyQuestionResponse | undefined
  loading: boolean
}) {
  const [showHint, setShowHint] = useState(false)
  const [userAnswer, setUserAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<EvaluateAnswerResponse | null>(null)

  const evaluateMutation = useMutation({
    mutationFn: () => apiClient.evaluateAnswer(data!.question!, userAnswer, data?.answer_hint ?? ''),
    onSuccess: (result) => setEvaluation(result),
  })

  if (loading) {
    return <Skeleton className="h-56 w-full rounded-[1.15rem]" />
  }

  if (!data?.question) {
    return null
  }

  return (
    <SurfaceCard className="relative overflow-hidden bg-[color:var(--ui-surface)]">
      <div className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-[color:var(--ui-accent-soft)] blur-3xl" />
      <div className="relative z-10">
        <div className="mb-5 flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-300" />
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-300">Pergunta do dia</p>
          {data.doc_name ? (
            <span className="truncate text-xs text-[color:var(--ui-text-meta)]">- {data.doc_name}</span>
          ) : null}
        </div>

        <p className="font-headline text-2xl font-bold leading-tight text-[color:var(--ui-text)]">
          {data.question}
        </p>

        {!evaluation ? (
          <div className="mt-6 space-y-3">
            <textarea
              value={userAnswer}
              onChange={(event) => setUserAnswer(event.target.value)}
              placeholder="Articule sua resposta aqui..."
              rows={4}
              className="w-full resize-none rounded-xl border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)] px-4 py-3 text-sm text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)] outline-none transition-colors focus:border-[color:var(--ui-accent)]"
            />
            <div className="flex justify-end">
              <Button
                onClick={() => evaluateMutation.mutate()}
                disabled={userAnswer.trim().length < 3 || evaluateMutation.isPending}
                className="bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
              >
                {evaluateMutation.isPending ? 'Avaliando...' : 'Avaliar resposta'}
              </Button>
            </div>
          </div>
        ) : (
          <div className={cn('mt-6 rounded-xl border p-4', SCORE_STYLE[evaluation.score] ?? SCORE_STYLE.parcial)}>
            <div className="mb-2 flex items-center justify-between gap-4">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em]">
                {SCORE_LABEL[evaluation.score] ?? evaluation.score}
              </span>
              <button
                type="button"
                onClick={() => {
                  setEvaluation(null)
                  setUserAnswer('')
                }}
                className="text-xs text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text)]"
              >
                Tentar novamente
              </button>
            </div>
            <p className="text-sm leading-relaxed">{evaluation.feedback}</p>
          </div>
        )}

        {data.answer_hint ? (
          <div className="mt-4">
            <button
              type="button"
              onClick={() => setShowHint((current) => !current)}
              className="flex items-center gap-1 text-xs text-[color:var(--ui-accent)] transition-colors hover:text-[color:var(--ui-accent-strong)]"
            >
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showHint && 'rotate-180')} />
              {showHint ? 'Ocultar dica' : 'Ver dica'}
            </button>
            {showHint ? (
              <p className="mt-2 rounded-lg bg-[color:var(--ui-surface-2)] px-3 py-2 text-xs leading-relaxed text-[color:var(--ui-text-dim)]">
                {data.answer_hint}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </SurfaceCard>
  )
}

export function Dashboard() {
  const { user } = useAuth()
  const [now, setNow] = useState(() => new Date())
  const [isSyncing, setIsSyncing] = useState(false)

  const { data: docs, isLoading: isDocsLoading, error: docsError } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const { data: artifacts, isLoading: isArtifactsLoading } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts'],
    queryFn: () => apiClient.listArtifacts(),
    retry: 1,
  })

  const {
    data: calendar,
    isLoading: isCalendarLoading,
    refetch: refetchCalendar,
  } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    retry: 1,
  })

  const {
    data: briefing,
    isLoading: isBriefingLoading,
    refetch: refetchBriefing,
  } = useQuery<BriefingResponse>({
    queryKey: ['briefing'],
    queryFn: apiClient.getBriefing,
    staleTime: 60_000,
    retry: 1,
  })

  const hasDocuments = !isDocsLoading && !!docs && docs.length > 0

  const { data: dailyQuestion, isLoading: isDailyQuestionLoading } = useQuery<DailyQuestionResponse>({
    queryKey: ['daily-question'],
    queryFn: apiClient.getDailyQuestion,
    staleTime: 12 * 60 * 60 * 1000,
    retry: false,
    enabled: hasDocuments,
  })

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  const firstName = user?.name?.trim().split(/\s+/)[0] || 'arquiteto'
  const todayLabel = now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })
  const currentTimeLabel = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const greeting = briefing?.greeting ?? 'Boa noite'
  const apiStatusLabel = docsError ? 'API offline' : 'API online'

  const overdueCount = briefing?.overdue_tasks.length ?? 0
  const heroSignalText = overdueCount
    ? overdueCount === 1
      ? '1 pendência atrasada requer atenção.'
      : `${overdueCount} pendências atrasadas requerem atenção.`
    : 'Workspace sincronizado com agenda e artefatos.'

  const todaySchedule = calendar?.today_schedule ?? []
  const todayReminders = calendar?.today_reminders ?? []

  const liveMomentLabel = calendar?.current_schedule_item
    ? `Agora: ${calendar.current_schedule_item.title} (${calendar.current_schedule_item.start_time} às ${calendar.current_schedule_item.end_time})`
    : calendar?.next_schedule_item
      ? `Próxima atividade: ${calendar.next_schedule_item.title} às ${calendar.next_schedule_item.start_time}`
      : todayReminders[0]
        ? `Próximo lembrete: ${todayReminders[0].title}`
        : 'Sem atividade ativa neste momento.'

  async function handleSyncNow() {
    if (isSyncing) return
    setIsSyncing(true)
    try {
      await Promise.all([refetchBriefing(), refetchCalendar()])
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <PageShell className="space-y-6">
      <section className="relative overflow-hidden rounded-[1.5rem] border border-[color:var(--ui-border-soft)] bg-[linear-gradient(120deg,rgba(15,20,28,0.98)_0%,rgba(19,26,36,0.95)_58%,rgba(27,36,48,0.88)_100%)] p-6 sm:p-8">
        <div className="pointer-events-none absolute -top-20 right-8 h-52 w-52 rounded-full bg-[color:var(--ui-accent-soft)] blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 left-0 h-24 w-full bg-[linear-gradient(180deg,transparent_0%,rgba(0,0,0,0.18)_100%)]" />

        <div className="relative z-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ui-text-meta)]">{todayLabel} - {currentTimeLabel}</p>
            <h1 className="mt-2 font-headline text-4xl font-extrabold tracking-tight text-[color:var(--ui-text)]">
              {greeting}, {firstName}.
            </h1>
            <p className="mt-2 max-w-xl text-sm text-[color:var(--ui-text-dim)]">
              Painel operacional com foco em contexto, ritmo diário e consolidação dos seus artefatos.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--ui-surface-3)] px-3 py-1 text-xs font-medium text-[color:var(--ui-text-dim)]">
                <span className={cn('h-1.5 w-1.5 rounded-full', docsError ? 'bg-rose-400' : 'bg-emerald-400')} />
                {apiStatusLabel}
              </span>
              <span className="text-xs text-[color:var(--ui-text-meta)]">{heroSignalText}</span>
            </div>
          </div>

          <div className="rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-4 py-3">
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">Agora no workspace</p>
              {isBriefingLoading || isCalendarLoading ? (
                <Skeleton className="h-7 w-56 rounded-md" />
              ) : (
                <p className="text-sm font-medium text-[color:var(--ui-text)]">{liveMomentLabel}</p>
              )}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleSyncNow}
                disabled={isSyncing}
                className="h-8 gap-1 px-2 text-xs"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', isSyncing && 'animate-spin')} />
                {isSyncing ? 'Atualizando...' : 'Atualizar agora'}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {docsError ? (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          Não foi possível conectar com a API. Inicie o backend com{' '}
          <code className="font-mono">python -m docops serve</code>.
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          title="Documentos"
          value={docs?.length ?? 0}
          icon={FileText}
          description="Base indexada para consulta"
          loading={isDocsLoading}
          tone="primary"
        />
        <MetricCard
          title="Artefatos"
          value={artifacts?.length ?? 0}
          icon={ScrollText}
          description="Resumos, checklists e saídas"
          loading={isArtifactsLoading}
          tone="tertiary"
        />
        <MetricCard
          title="Lembretes hoje"
          value={todayReminders.length}
          icon={CalendarClock}
          description="Itens de calendário para executar"
          loading={isCalendarLoading}
          tone={todayReminders.length ? 'primary' : 'neutral'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-6">
          <DailyQuestionPanel data={dailyQuestion} loading={isDailyQuestionLoading} />

          <SurfaceCard className="overflow-hidden bg-[color:var(--ui-surface-2)] p-0">
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="font-headline text-xl font-bold text-[color:var(--ui-text)]">Documentos recentes</h2>
              {hasDocuments ? (
                <Button variant="ghost" size="sm" asChild className="h-8 px-2 text-xs text-[color:var(--ui-accent)]">
                  <Link to="/docs">
                    Ver todos
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              ) : null}
            </div>

            {isDocsLoading ? (
              <div className="space-y-2 px-5 pb-5">
                {[1, 2, 3].map((item) => (
                  <Skeleton key={item} className="h-16 w-full rounded-xl" />
                ))}
              </div>
            ) : null}

            {!isDocsLoading && !hasDocuments ? (
              <div className="px-5 pb-5">
                <OnboardingSteps />
              </div>
            ) : null}

            {hasDocuments ? (
              <div className="space-y-2 px-5 pb-5">
                {docs.slice(0, 5).map((doc) => (
                  <div
                    key={doc.doc_id}
                    className="group flex items-center justify-between gap-4 rounded-xl bg-[color:var(--ui-surface-1)] px-4 py-3 transition-colors hover:bg-[color:var(--ui-surface-3)]"
                  >
                    <div className="min-w-0 flex items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ui-accent-soft)]">
                        <FileText className="h-4 w-4 text-[color:var(--ui-accent)]" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-[color:var(--ui-text)]">{doc.file_name}</p>
                        <p className="text-xs text-[color:var(--ui-text-meta)]">Fonte: {doc.source || 'local'}</p>
                      </div>
                    </div>
                    <span className="shrink-0 rounded-full bg-[color:var(--ui-surface-3)] px-2 py-0.5 text-xs text-[color:var(--ui-text-dim)]">
                      {doc.chunk_count} chunks
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </SurfaceCard>
        </div>

        <aside className="space-y-6">
          <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">
              Ações rápidas
            </p>
            <div className="grid grid-cols-2 gap-3">
              <QuickActionTile to="/ingest" icon={FileText} label="Novo doc" tone="primary" />
              <QuickActionTile to="/chat" icon={MessageSquare} label="Abrir chat" tone="tertiary" />
              <QuickActionTile to="/artifacts" icon={Layers} label="Artefatos" tone="neutral" />
              <QuickActionTile to="/schedule" icon={CalendarClock} label="Calendário" tone="neutral" />
            </div>
          </SurfaceCard>

          <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
            <div className="mb-5 flex items-center justify-between">
              <h3 className="font-headline text-lg font-bold text-[color:var(--ui-text)]">Agenda hoje</h3>
              <Link to="/schedule" className="text-xs font-semibold text-[color:var(--ui-accent)] hover:underline">
                Ver agenda
              </Link>
            </div>
            {isCalendarLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((item) => (
                  <Skeleton key={item} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : todaySchedule.length ? (
              <div className="space-y-3">
                {todaySchedule.slice(0, 4).map((item) => (
                  <div key={item.id} className="flex gap-3">
                    <p className="w-14 shrink-0 text-xs font-semibold text-[color:var(--ui-text-meta)]">{item.start_time}</p>
                    <div className="flex-1 border-l border-[color:var(--ui-border-strong)] pl-3">
                      <p className="text-sm font-semibold text-[color:var(--ui-text)]">{item.title}</p>
                      <p className="text-xs text-[color:var(--ui-text-dim)]">
                        até {item.end_time}
                        {item.note ? ` - ${item.note}` : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[color:var(--ui-text-dim)]">Nenhuma atividade fixa para hoje.</p>
            )}
          </SurfaceCard>

          <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
            <div className="mb-5 flex items-center justify-between">
              <h3 className="font-headline text-lg font-bold text-[color:var(--ui-text)]">Lembretes</h3>
              <Link to="/schedule" className="text-xs font-semibold text-[color:var(--ui-accent)] hover:underline">
                Gerenciar
              </Link>
            </div>
            {isCalendarLoading ? (
              <div className="space-y-2">
                {[1, 2].map((item) => (
                  <Skeleton key={item} className="h-12 w-full rounded-lg" />
                ))}
              </div>
            ) : todayReminders.length ? (
              <div className="space-y-3">
                {todayReminders.slice(0, 4).map((reminder) => (
                  <div key={reminder.id} className="rounded-xl bg-[color:var(--ui-surface-1)] px-3 py-2">
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 h-2 w-2 rounded-full bg-amber-300" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-[color:var(--ui-text)]">{reminder.title}</p>
                        <p className="text-xs text-[color:var(--ui-text-dim)]">
                          {reminder.all_day
                            ? 'Dia inteiro'
                            : new Date(reminder.starts_at).toLocaleTimeString('pt-BR', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          {reminder.note ? ` - ${reminder.note}` : ''}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[color:var(--ui-text-dim)]">Nenhum lembrete para hoje.</p>
            )}
          </SurfaceCard>

          <SurfaceCard className="bg-[color:var(--ui-surface)]">
            <div className="mb-4 flex items-center gap-2">
              <div className="h-2 w-2 animate-pulse rounded-full bg-amber-300" />
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">
                Sinais operacionais
              </p>
            </div>

            {isBriefingLoading ? (
              <Skeleton className="h-24 w-full rounded-lg" />
            ) : briefing ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg bg-[color:var(--ui-surface-2)] px-3 py-2 text-sm">
                  <span className="inline-flex items-center gap-2 text-[color:var(--ui-text-dim)]">
                    <Clock3 className="h-4 w-4" />
                    Programações hoje
                  </span>
                  <span className="font-semibold text-[color:var(--ui-text)]">{briefing.today_schedule.length}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-[color:var(--ui-surface-2)] px-3 py-2 text-sm">
                  <span className="inline-flex items-center gap-2 text-[color:var(--ui-text-dim)]">
                    <NotebookPen className="h-4 w-4" />
                    Notas salvas
                  </span>
                  <span className="font-semibold text-[color:var(--ui-text)]">{briefing.notes_count}</span>
                </div>
                <div className={cn(
                  'flex items-center justify-between rounded-lg px-3 py-2 text-sm',
                  briefing.overdue_tasks.length
                    ? 'bg-amber-500/12 text-amber-300'
                    : 'bg-emerald-500/10 text-emerald-300',
                )}>
                  <span className="inline-flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" />
                    Pendências atrasadas
                  </span>
                  <span className="font-semibold">{briefing.overdue_tasks.length}</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-[color:var(--ui-text-dim)]">Briefing indisponível no momento.</p>
            )}

            <Button variant="ghost" size="sm" asChild className="mt-4 h-8 w-full justify-between text-xs text-[color:var(--ui-accent)]">
              <Link to="/tasks">
                Ir para tarefas
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </SurfaceCard>
        </aside>
      </div>
    </PageShell>
  )
}
