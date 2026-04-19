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
  contentClassName,
}: {
  children: ReactNode
  className?: string
  contentClassName?: string
}) {
  return (
    <Card className={cn(
      'rounded-[1.15rem] border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] shadow-none',
      className,
    )}>
      <CardContent className={cn('p-4 sm:p-5', contentClassName)}>{children}</CardContent>
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
  className,
}: {
  title: string
  value: string | number
  icon: IconType
  description: string
  loading?: boolean
  tone?: 'primary' | 'tertiary' | 'neutral'
  className?: string
}) {
  const toneMap: Record<string, string> = {
    primary: 'text-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)]',
    tertiary: 'text-amber-300 bg-amber-500/10',
    neutral: 'text-[color:var(--ui-text-dim)] bg-[color:var(--ui-surface-2)]',
  }

  return (
    <SurfaceCard className={cn('h-full bg-[color:var(--ui-surface-2)]', className)} contentClassName="p-3 sm:p-5">
      <div className="mb-2 flex items-start justify-between gap-2 sm:mb-5 sm:gap-4">
        <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg sm:h-11 sm:w-11 sm:rounded-xl', toneMap[tone])}>
          <Icon className="h-4 w-4 sm:h-5 sm:w-5" />
        </div>
      </div>
      <p className="text-[9px] uppercase tracking-[0.12em] text-[color:var(--ui-text-meta)] sm:text-[11px] sm:tracking-[0.16em]">{title}</p>
      {loading ? (
        <Skeleton className="mt-1.5 h-6 w-12 rounded-md sm:mt-2 sm:h-8 sm:w-20" />
      ) : (
        <p className="mt-1.5 font-headline text-[2.05rem] font-bold leading-none text-[color:var(--ui-text)] sm:mt-2 sm:text-4xl">{value}</p>
      )}
      <p className="mt-1 text-[10px] leading-snug text-[color:var(--ui-text-dim)] sm:mt-3 sm:text-xs">{description}</p>
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
      className="group cursor-pointer rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] p-3.5 transition-colors duration-200 hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-3)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)] sm:p-4"
    >
      <Icon className={cn('h-5 w-5 transition-transform duration-200 group-hover:scale-110', toneClasses[tone])} />
      <p className="mt-2 text-xs font-semibold text-[color:var(--ui-text)] sm:text-sm">{label}</p>
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
  compact = false,
}: {
  data: DailyQuestionResponse | undefined
  loading: boolean
  compact?: boolean
}) {
  const [showHint, setShowHint] = useState(false)
  const [userAnswer, setUserAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<EvaluateAnswerResponse | null>(null)
  const [showComposer, setShowComposer] = useState(!compact)

  useEffect(() => {
    if (!compact) {
      setShowComposer(true)
    }
  }, [compact])

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

        <p className="font-headline text-xl font-bold leading-tight text-[color:var(--ui-text)] sm:text-2xl">
          {data.question}
        </p>

        {!evaluation ? (
          <div className="mt-5 space-y-3">
            {compact && !showComposer ? (
              <Button
                onClick={() => setShowComposer(true)}
                className="w-full bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
              >
                Responder agora
              </Button>
            ) : (
              <>
                <textarea
                  value={userAnswer}
                  onChange={(event) => setUserAnswer(event.target.value)}
                  placeholder="Articule sua resposta aqui..."
                  rows={compact ? 2 : 3}
                  className="w-full resize-none rounded-xl border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)] px-4 py-3 text-sm text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)] outline-none transition-colors focus:border-[color:var(--ui-accent)]"
                />
                <div className={cn('flex justify-end', compact && 'flex-col gap-2')}>
                  <Button
                    onClick={() => evaluateMutation.mutate()}
                    disabled={userAnswer.trim().length < 3 || evaluateMutation.isPending}
                    className="w-full bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)] sm:w-auto"
                  >
                    {evaluateMutation.isPending ? 'Avaliando...' : 'Avaliar resposta'}
                  </Button>
                  {compact ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => setShowComposer(false)}
                      className="w-full text-xs text-[color:var(--ui-text-meta)]"
                    >
                      Minimizar
                    </Button>
                  ) : null}
                </div>
              </>
            )}
          </div>
        ) : (
          <div className={cn('mt-5 rounded-xl border p-4', SCORE_STYLE[evaluation.score] ?? SCORE_STYLE.parcial)}>
            <div className="mb-2 flex items-center justify-between gap-4">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em]">
                {SCORE_LABEL[evaluation.score] ?? evaluation.score}
              </span>
              <button
                type="button"
                onClick={() => {
                  setEvaluation(null)
                  setUserAnswer('')
                  if (compact) setShowComposer(false)
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
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 639px)').matches : false,
  )

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
  } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    retry: 1,
  })

  const {
    data: briefing,
    isLoading: isBriefingLoading,
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

  useEffect(() => {
    const media = window.matchMedia('(max-width: 639px)')
    const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches)

    setIsMobile(media.matches)
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', handler)
      return () => media.removeEventListener('change', handler)
    }
    media.addListener(handler)
    return () => media.removeListener(handler)
  }, [])

  const firstName = user?.name?.trim().split(/\s+/)[0] || 'arquiteto'
  const todayLabel = now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })
  const currentTimeLabel = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const greeting = briefing?.greeting ?? 'Boa noite'

  const overdueCount = briefing?.overdue_tasks.length ?? 0
  const heroSignalText = overdueCount
    ? overdueCount === 1
      ? '1 pendência atrasada requer atenção.'
      : `${overdueCount} pendências atrasadas requerem atenção.`
    : 'Workspace sincronizado com agenda e artefatos.'

  const todaySchedule = calendar?.today_schedule ?? []
  const todayReminders = calendar?.today_reminders ?? []
  const docsPreviewCount = isMobile ? 3 : 5
  const schedulePreviewCount = isMobile ? 2 : 4
  const remindersPreviewCount = isMobile ? 2 : 4

  return (
    <PageShell className="space-y-4 pb-20 sm:space-y-6 md:pb-0">
      <section className="px-1 py-1 sm:px-0">
        <p className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)] sm:text-[11px] sm:tracking-[0.18em]">
          {todayLabel} - {currentTimeLabel}
        </p>
        <h1 className="mt-2 font-headline text-3xl font-extrabold tracking-tight text-[color:var(--ui-text)] sm:text-4xl">
          {greeting}, {firstName}.
        </h1>
        <p className="mt-2 max-w-xl text-xs text-[color:var(--ui-text-dim)] sm:text-sm">
          {heroSignalText}
        </p>
      </section>

      {docsError ? (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          Não foi possível conectar com a API. Inicie o backend com{' '}
          <code className="font-mono">python -m docops serve</code>.
        </div>
      ) : null}

      <div className="mx-auto w-full max-w-[30rem] space-y-4 sm:max-w-none sm:space-y-6">
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-2 sm:gap-4 xl:grid-cols-3">
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
            className="sm:col-span-2 xl:col-span-1"
            title="Lembretes hoje"
            value={todayReminders.length}
            icon={CalendarClock}
            description="Itens de calendário para executar"
            loading={isCalendarLoading}
            tone={todayReminders.length ? 'primary' : 'neutral'}
          />
        </div>

        <div className="grid gap-4 sm:gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
          <div className="space-y-4 sm:space-y-6">
            <DailyQuestionPanel data={dailyQuestion} loading={isDailyQuestionLoading} compact={isMobile} />

            <SurfaceCard className="overflow-hidden bg-[color:var(--ui-surface-2)] p-0" contentClassName="p-0">
              <div className="flex items-center justify-between px-4 py-4 sm:px-5">
                <h2 className="font-headline text-lg font-bold text-[color:var(--ui-text)] sm:text-xl">Documentos recentes</h2>
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
                <div className="space-y-2 px-4 pb-4 sm:px-5 sm:pb-5">
                  {[1, 2, 3].map((item) => (
                    <Skeleton key={item} className="h-16 w-full rounded-xl" />
                  ))}
                </div>
              ) : null}

              {!isDocsLoading && !hasDocuments ? (
                <div className="px-4 pb-4 sm:px-5 sm:pb-5">
                  <OnboardingSteps />
                </div>
              ) : null}

              {hasDocuments ? (
                <div className="space-y-2 px-4 pb-4 sm:px-5 sm:pb-5">
                  {docs.slice(0, docsPreviewCount).map((doc) => (
                    <div
                      key={doc.doc_id}
                      className="group flex items-center gap-3 rounded-xl bg-[color:var(--ui-surface-1)] px-3 py-3 transition-colors hover:bg-[color:var(--ui-surface-3)] sm:gap-4 sm:px-4"
                    >
                      <div className="min-w-0 flex w-full items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ui-accent-soft)]">
                          <FileText className="h-4 w-4 text-[color:var(--ui-accent)]" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-semibold text-[color:var(--ui-text)] sm:text-sm">{doc.file_name}</p>
                          <p className="hidden text-[11px] text-[color:var(--ui-text-meta)] sm:block">Fonte: {doc.source || 'local'}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </SurfaceCard>
          </div>

          <aside className="w-full space-y-4 sm:space-y-6">
          <SurfaceCard className="hidden bg-[color:var(--ui-surface-2)] md:block">
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
              <h3 className="font-headline text-base font-bold text-[color:var(--ui-text)] sm:text-lg">Agenda hoje</h3>
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
                {todaySchedule.slice(0, schedulePreviewCount).map((item) => (
                  <div key={item.id} className="flex gap-3">
                    <p className="w-11 shrink-0 text-[11px] font-semibold text-[color:var(--ui-text-meta)] sm:w-14 sm:text-xs">{item.start_time}</p>
                    <div className="flex-1 border-l border-[color:var(--ui-border-strong)] pl-3">
                      <p className="text-xs font-semibold text-[color:var(--ui-text)] sm:text-sm">{item.title}</p>
                      <p className="text-[11px] text-[color:var(--ui-text-dim)] sm:text-xs">
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
              <h3 className="font-headline text-base font-bold text-[color:var(--ui-text)] sm:text-lg">Lembretes</h3>
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
                {todayReminders.slice(0, remindersPreviewCount).map((reminder) => (
                  <div key={reminder.id} className="rounded-xl bg-[color:var(--ui-surface-1)] px-3 py-2.5">
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 h-2 w-2 rounded-full bg-amber-300" />
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-[color:var(--ui-text)] sm:text-sm">{reminder.title}</p>
                        <p className="text-[11px] text-[color:var(--ui-text-dim)] sm:text-xs">
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

          <SurfaceCard className="hidden bg-[color:var(--ui-surface)] sm:block">
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
      </div>

      <div className="fixed bottom-3 left-1/2 z-30 w-[calc(100%-2rem)] max-w-[30rem] -translate-x-1/2 sm:max-w-none md:hidden">
        <div className="grid grid-cols-3 gap-2 rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface)]/95 p-2 shadow-[0_14px_34px_-18px_rgba(0,0,0,0.65)] backdrop-blur-xl">
          <Link
            to="/ingest"
            className="inline-flex h-10 items-center justify-center gap-1 rounded-lg bg-[color:var(--ui-surface-2)] text-[11px] font-semibold text-[color:var(--ui-text)]"
          >
            <FileText className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
            Inserir
          </Link>
          <Link
            to="/chat"
            className="inline-flex h-10 items-center justify-center gap-1 rounded-lg bg-[color:var(--ui-accent)] text-[11px] font-semibold text-[color:var(--ui-bg)]"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Chat
          </Link>
          <Link
            to="/tasks"
            className="inline-flex h-10 items-center justify-center gap-1 rounded-lg bg-[color:var(--ui-surface-2)] text-[11px] font-semibold text-[color:var(--ui-text)]"
          >
            <NotebookPen className="h-3.5 w-3.5 text-amber-300" />
            Tarefas
          </Link>
        </div>
      </div>
    </PageShell>
  )
}
