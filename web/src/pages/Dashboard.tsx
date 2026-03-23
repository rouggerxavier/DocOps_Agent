import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  CalendarClock, FileText, Layers, BookOpen,
  MessageSquare, Clock, ChevronRight, ArrowRight, ScrollText,
  Sun, AlertTriangle, ListTodo, StickyNote, Lightbulb, ChevronDown,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type CalendarOverview, type DocItem, type ArtifactItem, type BriefingResponse, type DailyQuestionResponse, type EvaluateAnswerResponse } from '@/api/client'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { PageShell } from '@/components/ui/page-shell'

// ── Morning Briefing card ──────────────────────────────────────────────────

function MorningBriefing({ data, loading }: { data: BriefingResponse | undefined; loading: boolean }) {
  if (loading) return <Skeleton className="h-32 w-full rounded-xl" />
  if (!data) return null

  const hasOverdue = data.overdue_tasks.length > 0
  const hasReminders = data.today_reminders.length > 0
  const hasSchedule = data.today_schedule.length > 0
  const hasTasks = data.pending_tasks.length > 0

  return (
    <Card className={cn(
      'border bg-gradient-to-r overflow-hidden',
      hasOverdue
        ? 'border-amber-800/60 from-amber-950/40 to-zinc-900'
        : 'border-blue-800/40 from-blue-950/30 to-zinc-900',
    )}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
            hasOverdue ? 'bg-amber-600/20' : 'bg-blue-600/20',
          )}>
            <Sun className={cn('h-5 w-5', hasOverdue ? 'text-amber-400' : 'text-blue-400')} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-zinc-100">{data.greeting}!</p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
              {hasOverdue && (
                <span className="flex items-center gap-1 text-amber-400 font-medium">
                  <AlertTriangle className="h-3 w-3" />
                  {data.overdue_tasks.length} tarefa{data.overdue_tasks.length > 1 ? 's' : ''} atrasada{data.overdue_tasks.length > 1 ? 's' : ''}
                </span>
              )}
              {hasReminders && (
                <span className="flex items-center gap-1">
                  <CalendarClock className="h-3 w-3 text-yellow-500" />
                  {data.today_reminders.length} lembrete{data.today_reminders.length > 1 ? 's' : ''} hoje
                </span>
              )}
              {hasSchedule && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-zinc-500" />
                  {data.today_schedule.length} programaç{data.today_schedule.length > 1 ? 'ões' : 'ão'} para hoje
                </span>
              )}
              {hasTasks && (
                <span className="flex items-center gap-1">
                  <ListTodo className="h-3 w-3 text-zinc-500" />
                  {data.pending_tasks.length} tarefa{data.pending_tasks.length > 1 ? 's' : ''} pendente{data.pending_tasks.length > 1 ? 's' : ''}
                </span>
              )}
              <span className="flex items-center gap-1">
                <StickyNote className="h-3 w-3 text-zinc-500" />
                {data.notes_count} nota{data.notes_count !== 1 ? 's' : ''}
              </span>
            </div>
            {data.today_schedule.length > 0 && (
              <div className="mt-2 space-y-0.5">
                {data.today_schedule.slice(0, 2).map((s, i) => (
                  <p key={i} className="text-[11px] text-zinc-500">
                    <span className="text-emerald-400 font-medium">{s.start_time}–{s.end_time}</span>
                    {' '}· {s.title}
                  </p>
                ))}
              </div>
            )}
          </div>
          <div className="shrink-0 flex gap-2">
            <Link to="/tasks" className="text-[10px] text-blue-400 hover:underline">Tarefas</Link>
            <Link to="/schedule" className="text-[10px] text-blue-400 hover:underline">Calendário</Link>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Stat card ──────────────────────────────────────────────────────────────

function StatCard({
  title, value, icon: Icon, description, loading, accent,
}: {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  description?: string
  loading?: boolean
  accent?: 'green' | 'blue' | 'yellow'
}) {
  const accentMap: Record<string, string> = {
    green: 'text-emerald-400',
    blue: 'text-blue-400',
    yellow: 'text-yellow-400',
  }
  const accentClass = accent ? (accentMap[accent] ?? 'text-zinc-100') : 'text-zinc-100'

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">{title}</span>
          <Icon className="h-4 w-4 text-zinc-600" />
        </div>
        {loading ? (
          <Skeleton className="h-7 w-16 mb-1" />
        ) : (
          <div className={cn('text-2xl font-bold', accentClass)}>{value}</div>
        )}
        {description && <p className="mt-1 text-xs text-zinc-600">{description}</p>}
      </CardContent>
    </Card>
  )
}

// ── Quick action button ────────────────────────────────────────────────────

function QuickAction({
  to, icon: Icon, label, description, color,
}: {
  to: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  description: string
  color: string
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 transition-all hover:border-zinc-600 hover:bg-zinc-800"
    >
      <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', color)}>
        <Icon className="h-4 w-4 text-white" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-100">{label}</p>
        <p className="text-xs text-zinc-500">{description}</p>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-zinc-600 transition-transform group-hover:translate-x-0.5 group-hover:text-zinc-400" />
    </Link>
  )
}

// ── Onboarding steps (empty state) ────────────────────────────────────────

function OnboardingSteps() {
  const steps = [
    { n: 1, label: 'Insira um documento', sub: 'PDF, Markdown ou TXT', to: '/ingest', cta: 'Inserir' },
    { n: 2, label: 'Converse com o agente', sub: 'Faça perguntas sobre seus docs', to: '/chat', cta: 'Abrir chat' },
    { n: 3, label: 'Exporte artefatos', sub: 'Resumos e checklists salvos', to: '/artifacts', cta: 'Ver artefatos' },
  ]
  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardContent className="p-6">
        <div className="mb-5 flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-zinc-500" />
          <span className="text-sm font-semibold text-zinc-300">Como começar</span>
        </div>
        <div className="space-y-3">
          {steps.map((s) => (
            <div key={s.n} className="flex items-center gap-4">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-zinc-400">
                {s.n}
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-zinc-200">{s.label}</p>
                <p className="text-xs text-zinc-500">{s.sub}</p>
              </div>
              <Button variant="ghost" size="sm" asChild className="text-xs text-blue-400 hover:text-blue-300">
                <Link to={s.to}>{s.cta} <ChevronRight className="ml-1 h-3 w-3" /></Link>
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Daily Question card ────────────────────────────────────────────────────

const SCORE_STYLE: Record<string, string> = {
  excelente: 'text-emerald-400 border-emerald-700/50 bg-emerald-950/30',
  bom: 'text-blue-400 border-blue-700/50 bg-blue-950/30',
  parcial: 'text-yellow-400 border-yellow-700/50 bg-yellow-950/30',
  incorreto: 'text-red-400 border-red-700/50 bg-red-950/30',
  sem_resposta: 'text-zinc-400 border-zinc-700/50 bg-zinc-800/30',
}

const SCORE_LABEL: Record<string, string> = {
  excelente: 'Excelente',
  bom: 'Bom',
  parcial: 'Parcial',
  incorreto: 'Incorreto',
  sem_resposta: 'Sem resposta',
}

function DailyQuestion({ data, loading }: { data: DailyQuestionResponse | undefined; loading: boolean }) {
  const [showHint, setShowHint] = useState(false)
  const [userAnswer, setUserAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<EvaluateAnswerResponse | null>(null)

  const evalMut = useMutation({
    mutationFn: () => apiClient.evaluateAnswer(data!.question!, userAnswer, data?.answer_hint ?? ''),
    onSuccess: result => setEvaluation(result),
  })

  if (loading) return <Skeleton className="h-28 w-full rounded-xl" />
  if (!data?.question) return null

  return (
    <Card className="border-violet-800/40 bg-gradient-to-r from-violet-950/30 to-zinc-900 overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-600/20">
            <Lightbulb className="h-5 w-5 text-violet-400" />
          </div>
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-violet-400">Pergunta do Dia</span>
              {data.doc_name && (
                <span className="text-[10px] text-zinc-600 truncate">· {data.doc_name}</span>
              )}
            </div>
            <p className="text-sm font-medium text-zinc-100 leading-snug">{data.question}</p>

            {/* Answer textarea */}
            {!evaluation && (
              <div className="space-y-1.5">
                <textarea
                  value={userAnswer}
                  onChange={e => setUserAnswer(e.target.value)}
                  placeholder="Digite sua resposta aqui..."
                  rows={2}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900/80 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-violet-600/60 resize-none"
                />
                <Button
                  size="sm"
                  onClick={() => evalMut.mutate()}
                  disabled={userAnswer.trim().length < 3 || evalMut.isPending}
                  className="h-7 text-xs bg-violet-700 hover:bg-violet-600"
                >
                  {evalMut.isPending ? 'Avaliando...' : 'Avaliar resposta'}
                </Button>
              </div>
            )}

            {/* Evaluation result */}
            {evaluation && (
              <div className={cn('rounded-lg border px-3 py-2 space-y-1', SCORE_STYLE[evaluation.score] ?? SCORE_STYLE.parcial)}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase">{SCORE_LABEL[evaluation.score] ?? evaluation.score}</span>
                  <button
                    onClick={() => { setEvaluation(null); setUserAnswer('') }}
                    className="text-[10px] text-zinc-500 hover:text-zinc-300"
                  >
                    Tentar novamente
                  </button>
                </div>
                <p className="text-xs leading-relaxed">{evaluation.feedback}</p>
              </div>
            )}

            {/* Hint toggle */}
            {data.answer_hint && (
              <div>
                <button
                  onClick={() => setShowHint(h => !h)}
                  className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                >
                  <ChevronDown className={cn('h-3 w-3 transition-transform', showHint && 'rotate-180')} />
                  {showHint ? 'Ocultar dica' : 'Ver dica de resposta'}
                </button>
                {showHint && (
                  <p className="mt-1.5 rounded-lg bg-zinc-800/60 px-3 py-2 text-xs text-zinc-400 leading-relaxed">
                    {data.answer_hint}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────

export function Dashboard() {
  const { data: docs, isLoading, error } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })
  const { data: artifacts } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts'],
    queryFn: apiClient.listArtifacts,
    retry: 1,
  })
  const { data: calendar, isLoading: isCalLoading } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    retry: 1,
  })
  const { data: briefing, isLoading: isBriefingLoading } = useQuery<BriefingResponse>({
    queryKey: ['briefing'],
    queryFn: apiClient.getBriefing,
    staleTime: 60_000,
    retry: 1,
  })
  const { data: dailyQuestion, isLoading: isDQLoading } = useQuery<DailyQuestionResponse>({
    queryKey: ['daily-question'],
    queryFn: apiClient.getDailyQuestion,
    staleTime: 12 * 60 * 60 * 1000, // 12h — muda uma vez por dia
    retry: false,
    enabled: !isLoading && !!docs && docs.length > 0,
  })


  const hasDocuments = !isLoading && docs && docs.length > 0
  const apiStatus = error ? 'Offline' : 'Online'

  const now = new Date()
  const todayLabel = now.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <PageShell className="space-y-6">

      {/* Header + API status badge */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Dashboard</h1>
          <p className="mt-0.5 text-sm text-zinc-500">{todayLabel}</p>
        </div>
        <span className={cn(
          'mt-1 flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
          error
            ? 'bg-red-950/50 text-red-400 border border-red-800'
            : 'bg-emerald-950/50 text-emerald-400 border border-emerald-800'
        )}>
          <span className={cn('h-1.5 w-1.5 rounded-full', error ? 'bg-red-400' : 'bg-emerald-400')} />
          API {apiStatus}
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Não foi possível conectar à API.{' '}
          <code className="font-mono">python -m docops serve</code>
        </div>
      )}

      {/* Morning Briefing */}
      <MorningBriefing data={briefing} loading={isBriefingLoading} />

      {/* Pergunta do Dia */}
      <DailyQuestion data={dailyQuestion} loading={isDQLoading} />

      {/* Ações Rápidas — sempre visíveis no topo */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">Ações Rápidas</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          <QuickAction to="/ingest"    icon={FileText}       label="Inserir Documentos" description="Adicionar PDFs, Markdown ou TXT"    color="bg-blue-600" />
          <QuickAction to="/chat"      icon={MessageSquare}  label="Iniciar Chat"        description="Conversar com seus documentos"     color="bg-violet-600" />
          <QuickAction to="/artifacts" icon={Layers}         label="Ver Artefatos"       description="Resumos e checklists salvos"       color="bg-amber-600" />
          <QuickAction to="/schedule"  icon={CalendarClock}  label="Calendário"          description="Cronograma e lembretes do dia"     color="bg-emerald-600" />
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-3">
        <StatCard title="Documentos"    value={docs?.length ?? 0}        icon={FileText}      description="indexados"            loading={isLoading}   accent="blue" />
        <StatCard title="Artefatos"      value={artifacts?.length ?? 0}       icon={ScrollText} description="resumos e checklists"   loading={isLoading} accent="blue" />
        <StatCard title="Lembretes Hoje" value={calendar?.today_reminders.length ?? 0} icon={CalendarClock} description="agenda do dia" loading={isCalLoading} accent={calendar && calendar.today_reminders.length > 0 ? 'yellow' : undefined} />
      </div>

      {/* Cronograma atual */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border-zinc-800 bg-zinc-900">
          <CardContent className="p-4">
            <div className="mb-3 flex items-center gap-2">
              <Clock className="h-4 w-4 text-zinc-500" />
              <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Agora no Cronograma</span>
            </div>
            {isCalLoading ? (
              <Skeleton className="h-6 w-3/4" />
            ) : calendar?.current_schedule_item ? (
              <>
                <p className="text-base font-semibold text-emerald-300">{calendar.current_schedule_item.title}</p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {calendar.current_schedule_item.start_time} às {calendar.current_schedule_item.end_time}
                </p>
              </>
            ) : (
              <p className="text-sm text-zinc-500">Sem atividade fixa neste horário.</p>
            )}
            {!isCalLoading && calendar?.next_schedule_item && (
              <p className="mt-3 text-xs text-zinc-400 border-t border-zinc-800 pt-3">
                <span className="text-zinc-600">Próximo: </span>
                {calendar.next_schedule_item.title}
                <span className="text-zinc-600"> às {calendar.next_schedule_item.start_time}</span>
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900">
          <CardContent className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-zinc-500" />
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Lembretes de Hoje</span>
              </div>
              {calendar && calendar.today_reminders.length > 0 && (
                <Link to="/schedule" className="text-xs text-blue-400 hover:text-blue-300">Ver todos</Link>
              )}
            </div>
            {isCalLoading && <Skeleton className="h-10 w-full" />}
            {!isCalLoading && (!calendar || calendar.today_reminders.length === 0) && (
              <p className="text-sm text-zinc-500">Nenhum lembrete para hoje.</p>
            )}
            {!isCalLoading && calendar?.today_reminders.slice(0, 3).map(rem => (
              <div key={rem.id} className="mb-2 last:mb-0 flex items-start gap-2 rounded-lg bg-zinc-800/60 px-3 py-2">
                <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-yellow-400" />
                <div>
                  <p className="text-sm text-zinc-200">{rem.title}</p>
                  <p className="text-xs text-zinc-500">
                    {rem.all_day
                      ? 'Dia inteiro'
                      : new Date(rem.starts_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    {rem.note ? ` · ${rem.note}` : ''}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Documentos Recentes */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Documentos Recentes</h2>
          {hasDocuments && (
            <Button variant="ghost" size="sm" asChild className="text-xs text-zinc-400 hover:text-zinc-200 h-auto py-1">
              <Link to="/docs">Ver todos <ChevronRight className="ml-1 h-3 w-3" /></Link>
            </Button>
          )}
        </div>

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        )}

        {!isLoading && !hasDocuments && <OnboardingSteps />}

        {hasDocuments && (
          <div className="space-y-1.5">
            {docs.slice(0, 5).map(doc => (
              <div
                key={doc.file_name}
                className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 hover:border-zinc-700 transition-colors"
              >
                <FileText className="h-4 w-4 shrink-0 text-blue-400" />
                <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{doc.file_name}</p>
                <span className="shrink-0 rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-500">
                  {doc.chunk_count} chunks
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

    </PageShell>
  )
}
