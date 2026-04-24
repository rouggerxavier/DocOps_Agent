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
  Target,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
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
  type GapAnalysisResponse,
  type ProactiveRecommendationActionPayload,
  type ProactiveRecommendationItem,
  type ProactiveRecommendationsResponse,
} from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { OnboardingChecklist } from '@/onboarding/OnboardingChecklist'
import { trackPremiumFeatureActivation, trackPremiumTouchpointViewed, trackUpgradeCompleted, trackUpgradeInitiated } from '@/features/premiumAnalytics'
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

const GAP_PRIORITY_STYLE: Record<string, string> = {
  high: 'border-rose-500/35 bg-rose-500/10 text-rose-200',
  normal: 'border-amber-500/35 bg-amber-500/10 text-amber-200',
  low: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200',
}

const GAP_PRIORITY_LABEL: Record<string, string> = {
  high: 'Alta',
  normal: 'Normal',
  low: 'Baixa',
}

const RECOMMENDATION_ACTION_TOAST: Record<ProactiveRecommendationActionPayload['action'], string | null> = {
  dismiss: 'Recomendacao dispensada.',
  snooze: 'Recomendacao adiada por 24h.',
  mute_category: 'Categoria silenciada por 7 dias.',
  feedback_useful: 'Feedback recebido. Vamos reforcar sugestoes desse perfil.',
  feedback_not_useful: 'Feedback recebido. Vamos ajustar as proximas sugestoes.',
}

function getApiErrorDetail(error: unknown, fallback = 'Nao foi possivel concluir a operacao.'): string {
  const maybeError = error as {
    response?: {
      data?: {
        detail?: string
      }
    }
    message?: string
  }

  return (
    maybeError?.response?.data?.detail
    || maybeError?.message
    || fallback
  )
}

function SurfaceCard({
  children,
  className,
  contentClassName,
  id,
}: {
  children: ReactNode
  className?: string
  contentClassName?: string
  id?: string
}) {
  return (
    <Card id={id} className={cn(
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


function DailyQuestionPanel({
  data,
  loading,
  touchpoint,
  locked = false,
  entitlementTier = 'free',
  onRefreshAccess,
  onUpgradeIntent,
  compact = false,
}: {
  data: DailyQuestionResponse | undefined
  loading: boolean
  touchpoint: string
  locked?: boolean
  entitlementTier?: string
  onRefreshAccess?: (touchpoint: string) => Promise<void> | void
  onUpgradeIntent?: (touchpoint: string) => void
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

  if (locked) {
    return (
      <SurfaceCard className="border-amber-500/35 bg-amber-500/10">
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-200">Pergunta do dia</p>
              <h3 className="mt-1 font-headline text-lg font-bold text-amber-100 sm:text-xl">
                Recurso premium bloqueado
              </h3>
            </div>
            <Sparkles className="h-5 w-5 text-amber-200" />
          </div>
          <p className="text-sm text-amber-100/90">
            Seu plano atual ({entitlementTier}) nao inclui `premium_proactive_copilot`.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => { void onRefreshAccess?.(touchpoint) }}>
              Ja fiz upgrade, atualizar acesso
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/settings" onClick={() => onUpgradeIntent?.(touchpoint)}>Ver recursos premium</Link>
            </Button>
          </div>
        </div>
      </SurfaceCard>
    )
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

function GapAnalysisPanel({
  docs,
  loadingDocs,
  touchpoint,
  locked = false,
  entitlementTier = 'free',
  onRefreshAccess,
  onUpgradeIntent,
  compact = false,
  id,
}: {
  docs: DocItem[] | undefined
  loadingDocs: boolean
  touchpoint: string
  locked?: boolean
  entitlementTier?: string
  onRefreshAccess?: (touchpoint: string) => Promise<void> | void
  onUpgradeIntent?: (touchpoint: string) => void
  compact?: boolean
  id?: string
}) {
  const [selectedDocNames, setSelectedDocNames] = useState<string[]>([])
  const [result, setResult] = useState<GapAnalysisResponse | null>(null)
  const [errorText, setErrorText] = useState<string | null>(null)
  const hasDocs = !!docs?.length
  const docPreview = docs?.slice(0, compact ? 4 : 6) ?? []
  const resultPreviewCount = compact ? 3 : 5

  useEffect(() => {
    if (!docs?.length) {
      setSelectedDocNames([])
      return
    }
    setSelectedDocNames((prev) => prev.filter((name) => docs.some((doc) => doc.file_name === name)))
  }, [docs])

  const gapMutation = useMutation({
    mutationFn: () => apiClient.runGapAnalysis(selectedDocNames),
    onSuccess: (payload) => {
      setResult(payload)
      setErrorText(null)
      trackPremiumFeatureActivation({
        touchpoint,
        capability: 'premium_proactive_copilot',
        metadata: {
          surface: 'dashboard',
          docs_analyzed: payload.docs_analyzed,
          gap_count: payload.gaps.length,
        },
      })
    },
    onError: (error) => {
      setErrorText(getApiErrorDetail(error, 'Nao foi possivel concluir a analise de lacunas.'))
    },
  })

  function toggleDoc(docName: string) {
    setSelectedDocNames((prev) => (
      prev.includes(docName)
        ? prev.filter((item) => item !== docName)
        : [...prev, docName]
    ))
  }

  function runAnalysis() {
    setErrorText(null)
    gapMutation.mutate()
  }

  return (
    <SurfaceCard id={id} className="overflow-hidden bg-[color:var(--ui-surface-2)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">Recomendacoes</p>
          <h3 className="mt-2 font-headline text-lg font-bold text-[color:var(--ui-text)] sm:text-xl">Mapa de lacunas</h3>
          <p className="mt-1 text-xs text-[color:var(--ui-text-dim)] sm:text-sm">
            Detecta topicos importantes ainda sem cobertura forte em tarefas e flashcards.
          </p>
        </div>
        <div className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[color:var(--ui-accent-soft)]">
          <Target className="h-4 w-4 text-[color:var(--ui-accent)]" />
        </div>
      </div>

      {locked ? (
        <div className="mt-4 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3">
          <p className="text-sm font-medium text-amber-100">
            Mapa de lacunas bloqueado no plano atual ({entitlementTier}).
          </p>
          <p className="mt-1 text-xs text-amber-100/85">
            Este fluxo exige o entitlement `premium_proactive_copilot`.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => { void onRefreshAccess?.(touchpoint) }}>
              Ja fiz upgrade, atualizar acesso
            </Button>
            <Button variant="ghost" size="sm" asChild className="text-amber-100">
              <Link to="/settings" onClick={() => onUpgradeIntent?.(touchpoint)}>Ver recursos premium</Link>
            </Button>
          </div>
        </div>
      ) : loadingDocs ? (
        <div className="mt-4 space-y-2">
          <Skeleton className="h-9 w-full rounded-lg" />
          <Skeleton className="h-9 w-full rounded-lg" />
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      ) : !hasDocs ? (
        <div className="mt-4 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-4 py-3">
          <p className="text-sm text-[color:var(--ui-text-dim)]">
            Insira ao menos um documento para liberar a analise de lacunas.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-4">
            <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-[color:var(--ui-text-meta)]">
              Escopo opcional por documento
            </p>
            <div className="flex flex-wrap gap-2">
              {docPreview.map((doc) => {
                const active = selectedDocNames.includes(doc.file_name)
                return (
                  <button
                    key={doc.doc_id}
                    type="button"
                    onClick={() => toggleDoc(doc.file_name)}
                    className={cn(
                      'rounded-full border px-3 py-1 text-[11px] font-medium transition-colors',
                      active
                        ? 'border-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]'
                        : 'border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] text-[color:var(--ui-text-dim)] hover:border-[color:var(--ui-border-strong)]',
                    )}
                  >
                    {doc.file_name}
                  </button>
                )
              })}
            </div>
            {docs.length > docPreview.length ? (
              <p className="mt-2 text-[11px] text-[color:var(--ui-text-meta)]">
                Mostrando {docPreview.length} de {docs.length} docs. Sem filtro, analisamos o workspace inteiro.
              </p>
            ) : null}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={runAnalysis}
              disabled={gapMutation.isPending}
              className="h-9 bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
            >
              {gapMutation.isPending ? 'Analisando...' : 'Analisar lacunas'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setSelectedDocNames([])}
              disabled={gapMutation.isPending || selectedDocNames.length === 0}
              className="h-9 text-xs text-[color:var(--ui-text-dim)]"
            >
              Limpar filtro
            </Button>
          </div>

          {gapMutation.isPending ? (
            <div className="mt-4 space-y-2">
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
            </div>
          ) : null}

          {errorText ? (
            <div className="mt-4 rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {errorText}
            </div>
          ) : null}

          {!gapMutation.isPending && result ? (
            <div className="mt-4 space-y-3">
              <p className="text-xs text-[color:var(--ui-text-meta)]">
                Analise concluida em {result.docs_analyzed} documento(s).
              </p>

              {result.gaps.length === 0 ? (
                <div className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3">
                  <p className="text-sm font-medium text-emerald-200">Nenhuma lacuna relevante encontrada agora.</p>
                  <p className="mt-1 text-xs text-emerald-100/80">
                    Continue o ritmo no chat e gere flashcards para manter a cobertura.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button variant="ghost" size="sm" asChild className="h-8 px-2 text-xs text-emerald-100">
                      <Link to="/chat">Revisar no chat</Link>
                    </Button>
                    <Button variant="ghost" size="sm" asChild className="h-8 px-2 text-xs text-emerald-100">
                      <Link to="/flashcards">Abrir flashcards</Link>
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {result.gaps.slice(0, resultPreviewCount).map((gap) => {
                    const priority = gap.prioridade || 'normal'
                    return (
                      <div key={`${gap.topico}-${gap.sugestao}`} className="rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-[color:var(--ui-text)]">{gap.topico}</p>
                          <span className={cn(
                            'rounded-full border px-2 py-0.5 text-[11px] font-semibold',
                            GAP_PRIORITY_STYLE[priority] ?? GAP_PRIORITY_STYLE.normal,
                          )}>
                            Prioridade {GAP_PRIORITY_LABEL[priority] ?? GAP_PRIORITY_LABEL.normal}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-[color:var(--ui-text-dim)]">{gap.descricao}</p>
                        <p className="mt-2 text-xs text-[color:var(--ui-text)]">
                          <span className="text-[color:var(--ui-text-meta)]">Sugestao: </span>{gap.sugestao}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Button variant="ghost" size="sm" asChild className="h-7 px-2 text-xs text-[color:var(--ui-accent)]">
                            <Link to="/chat">Revisar no chat</Link>
                          </Button>
                          <Button variant="ghost" size="sm" asChild className="h-7 px-2 text-xs text-amber-300">
                            <Link to="/flashcards">Criar flashcards</Link>
                          </Button>
                          <Button variant="ghost" size="sm" asChild className="h-7 px-2 text-xs text-[color:var(--ui-text-dim)]">
                            <Link to="/tasks">Virar tarefa</Link>
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                  {result.gaps.length > resultPreviewCount ? (
                    <p className="text-xs text-[color:var(--ui-text-meta)]">
                      Mostrando {resultPreviewCount} de {result.gaps.length} lacunas encontradas.
                    </p>
                  ) : null}
                </div>
              )}
            </div>
          ) : null}
        </>
      )}
    </SurfaceCard>
  )
}

function ProactiveRecommendationsPanel({
  recommendations,
  featureEnabled,
  capabilityUnlocked,
  touchpoint,
  loading = false,
  actionPending = false,
  entitlementTier = 'free',
  onRefreshAccess,
  onUpgradeIntent,
  onRecordAction,
  compact = false,
}: {
  recommendations: ProactiveRecommendationItem[]
  featureEnabled: boolean
  capabilityUnlocked: boolean
  touchpoint: string
  loading?: boolean
  actionPending?: boolean
  entitlementTier?: string
  onRefreshAccess?: (touchpoint: string) => Promise<void> | void
  onUpgradeIntent?: (touchpoint: string) => void
  onRecordAction?: (payload: ProactiveRecommendationActionPayload) => Promise<void>
  compact?: boolean
}) {
  const previewCount = compact ? 3 : 4

  if (!featureEnabled) {
    return (
      <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">Copilot proativo</p>
            <h3 className="mt-2 font-headline text-lg font-bold text-[color:var(--ui-text)] sm:text-xl">Recomendacoes inteligentes</h3>
          </div>
          <Sparkles className="h-5 w-5 text-[color:var(--ui-text-meta)]" />
        </div>
        <p className="mt-3 text-sm text-[color:var(--ui-text-dim)]">
          Este modulo esta desativado por feature flag (`proactive_copilot_enabled`).
        </p>
      </SurfaceCard>
    )
  }

  if (!capabilityUnlocked) {
    return (
      <SurfaceCard className="border-amber-500/35 bg-amber-500/10">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-200">Copilot proativo</p>
            <h3 className="mt-2 font-headline text-lg font-bold text-amber-100 sm:text-xl">Recomendacoes bloqueadas</h3>
          </div>
          <Sparkles className="h-5 w-5 text-amber-200" />
        </div>
        <p className="mt-3 text-sm text-amber-100/90">
          Seu plano atual ({entitlementTier}) nao inclui `premium_proactive_copilot`.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => { void onRefreshAccess?.(touchpoint) }}>
            Ja fiz upgrade, atualizar acesso
          </Button>
          <Button variant="ghost" size="sm" asChild className="text-amber-100">
            <Link to="/settings" onClick={() => onUpgradeIntent?.(touchpoint)}>Ver recursos premium</Link>
          </Button>
        </div>
      </SurfaceCard>
    )
  }

  async function dismissRecommendation(item: ProactiveRecommendationItem) {
    if (!onRecordAction) return
    await onRecordAction({
      recommendation_id: item.id,
      category: item.category,
      action: 'dismiss',
    })
  }

  async function snoozeRecommendation(item: ProactiveRecommendationItem) {
    if (!onRecordAction) return
    await onRecordAction({
      recommendation_id: item.id,
      category: item.category,
      action: 'snooze',
      duration_hours: 24,
    })
  }

  async function muteCategory(item: ProactiveRecommendationItem) {
    if (!onRecordAction) return
    await onRecordAction({
      recommendation_id: item.id,
      category: item.category,
      action: 'mute_category',
      duration_hours: 24 * 7,
    })
  }

  async function markRecommendationFeedback(item: ProactiveRecommendationItem, useful: boolean) {
    if (!onRecordAction) return
    await onRecordAction({
      recommendation_id: item.id,
      category: item.category,
      action: useful ? 'feedback_useful' : 'feedback_not_useful',
    })
  }

  return (
    <SurfaceCard className="bg-[color:var(--ui-surface-2)]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-text-meta)]">Copilot proativo</p>
          <h3 className="mt-2 font-headline text-lg font-bold text-[color:var(--ui-text)] sm:text-xl">Proximas melhores acoes</h3>
          <p className="mt-1 text-xs text-[color:var(--ui-text-dim)] sm:text-sm">
            Sugestoes com contexto do seu ritmo de estudo e cobertura atual.
          </p>
        </div>
        <Sparkles className="h-5 w-5 text-[color:var(--ui-accent)]" />
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : recommendations.length === 0 ? (
        <div className="rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-4 py-3">
          <p className="text-sm font-medium text-[color:var(--ui-text)]">Sem recomendacoes ativas por enquanto.</p>
          <p className="mt-1 text-xs text-[color:var(--ui-text-dim)]">
            Volte mais tarde ou continue interagindo no workspace para gerar novas sugestoes.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {recommendations.slice(0, previewCount).map((item) => (
            <div key={item.id} className="rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-4 py-3">
              <p className="text-sm font-semibold text-[color:var(--ui-text)]">{item.title}</p>
              <p className="mt-1 text-xs text-[color:var(--ui-text-dim)]">{item.description}</p>
              <p className="mt-2 text-xs text-[color:var(--ui-text)]">
                <span className="text-[color:var(--ui-text-meta)]">Por que isso: </span>
                {item.why_this}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button size="sm" asChild className="h-8 bg-[color:var(--ui-accent)] px-2 text-xs text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]">
                  <Link to={item.action_to}>{item.action_label}</Link>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={actionPending}
                  onClick={() => { void snoozeRecommendation(item) }}
                  className="h-8 px-2 text-xs text-[color:var(--ui-text-dim)]"
                >
                  {actionPending ? 'Aplicando...' : 'Adiar 24h'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={actionPending}
                  onClick={() => { void muteCategory(item) }}
                  className="h-8 px-2 text-xs text-[color:var(--ui-text-dim)]"
                >
                  Silenciar categoria
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={actionPending}
                  onClick={() => { void dismissRecommendation(item) }}
                  className="h-8 px-2 text-xs text-rose-300"
                >
                  Dispensar
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--ui-border-soft)] pt-3">
                <p className="text-[11px] text-[color:var(--ui-text-meta)]">Essa recomendacao foi util?</p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Marcar recomendacao ${item.title} como util`}
                    disabled={actionPending}
                    onClick={() => { void markRecommendationFeedback(item, true) }}
                    className="h-8 border border-emerald-500/35 bg-emerald-500/10 px-2 text-xs text-emerald-200 transition-colors hover:bg-emerald-500/20"
                  >
                    <ThumbsUp className="mr-1 h-3.5 w-3.5" />
                    Util
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Marcar recomendacao ${item.title} como nao util`}
                    disabled={actionPending}
                    onClick={() => { void markRecommendationFeedback(item, false) }}
                    className="h-8 border border-rose-500/35 bg-rose-500/10 px-2 text-xs text-rose-200 transition-colors hover:bg-rose-500/20"
                  >
                    <ThumbsDown className="mr-1 h-3.5 w-3.5" />
                    Nao util
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </SurfaceCard>
  )
}

export function Dashboard() {
  const { user } = useAuth()
  const capabilities = useCapabilities()
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

  const proactiveCopilotFeatureEnabled = capabilities.isEnabled('proactive_copilot_enabled')
  const proactiveCopilotUnlocked = capabilities.hasCapability('premium_proactive_copilot')
  const proactiveCopilotEnabled = proactiveCopilotFeatureEnabled && proactiveCopilotUnlocked
  const proactiveCopilotLocked = proactiveCopilotFeatureEnabled && !proactiveCopilotUnlocked
  const [lastUpgradeTouchpoint, setLastUpgradeTouchpoint] = useState('dashboard.proactive_recommendations')
  const [wasProactiveLocked, setWasProactiveLocked] = useState(proactiveCopilotLocked)

  const { data: dailyQuestion, isLoading: isDailyQuestionLoading } = useQuery<DailyQuestionResponse>({
    queryKey: ['daily-question'],
    queryFn: apiClient.getDailyQuestion,
    staleTime: 12 * 60 * 60 * 1000,
    retry: false,
    enabled: hasDocuments && proactiveCopilotEnabled,
  })

  const {
    data: proactiveRecommendationsPayload,
    isLoading: isProactiveRecommendationsLoading,
    refetch: refetchProactiveRecommendations,
  } = useQuery<ProactiveRecommendationsResponse>({
    queryKey: ['proactive-recommendations'],
    queryFn: apiClient.listProactiveRecommendations,
    staleTime: 60_000,
    retry: false,
    enabled: proactiveCopilotEnabled,
  })

  const recommendationActionMutation = useMutation({
    mutationFn: (payload: ProactiveRecommendationActionPayload) =>
      apiClient.recordProactiveRecommendationAction(payload),
    onSuccess: (_result, payload) => {
      const successMessage = RECOMMENDATION_ACTION_TOAST[payload.action]
      if (successMessage) {
        toast.success(successMessage)
      }
      void refetchProactiveRecommendations()
    },
    onError: (error) => {
      toast.error(getApiErrorDetail(error, 'Nao foi possivel registrar a acao da recomendacao.'))
    },
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

  useEffect(() => {
    if (!proactiveCopilotLocked) return
    trackPremiumTouchpointViewed({
      touchpoint: 'dashboard.proactive_recommendations',
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'dashboard' },
    })
    trackPremiumTouchpointViewed({
      touchpoint: 'dashboard.daily_question',
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'dashboard' },
    })
    trackPremiumTouchpointViewed({
      touchpoint: 'dashboard.gap_analysis',
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'dashboard' },
    })
  }, [proactiveCopilotLocked])

  useEffect(() => {
    if (wasProactiveLocked && !proactiveCopilotLocked) {
      trackUpgradeCompleted({
        touchpoint: lastUpgradeTouchpoint,
        capability: 'premium_proactive_copilot',
        metadata: { surface: 'dashboard' },
      })
      trackPremiumFeatureActivation({
        touchpoint: lastUpgradeTouchpoint,
        capability: 'premium_proactive_copilot',
        metadata: { surface: 'dashboard', source: 'unlock_transition' },
      })
    }
    setWasProactiveLocked(proactiveCopilotLocked)
  }, [lastUpgradeTouchpoint, proactiveCopilotLocked, wasProactiveLocked])

  useEffect(() => {
    if (!proactiveCopilotEnabled || !dailyQuestion?.question) return
    trackPremiumFeatureActivation({
      touchpoint: 'dashboard.daily_question',
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'dashboard', source: 'daily_question' },
    })
  }, [dailyQuestion?.question, proactiveCopilotEnabled])

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
  const proactiveRecommendations = proactiveRecommendationsPayload?.recommendations ?? []

  function handleProactiveUpgradeIntent(touchpoint: string, source: 'link' | 'refresh_access' = 'link') {
    setLastUpgradeTouchpoint(touchpoint)
    trackUpgradeInitiated({
      touchpoint,
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'dashboard', source },
    })
  }

  async function handleRefreshProactiveAccess(touchpoint: string) {
    handleProactiveUpgradeIntent(touchpoint, 'refresh_access')
    await capabilities.refresh()
    toast.info('Acesso premium atualizado. Se o upgrade ja foi aplicado, recarregamos suas capacidades.')
  }
  async function handleRecommendationAction(payload: ProactiveRecommendationActionPayload) {
    await recommendationActionMutation.mutateAsync(payload)
  }
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
            <ProactiveRecommendationsPanel
              recommendations={proactiveRecommendations}
              featureEnabled={proactiveCopilotFeatureEnabled}
              capabilityUnlocked={proactiveCopilotUnlocked}
              touchpoint="dashboard.proactive_recommendations"
              loading={isProactiveRecommendationsLoading}
              actionPending={recommendationActionMutation.isPending}
              entitlementTier={capabilities.entitlementTier}
              onRefreshAccess={handleRefreshProactiveAccess}
              onUpgradeIntent={handleProactiveUpgradeIntent}
              onRecordAction={handleRecommendationAction}
              compact={isMobile}
            />
            <DailyQuestionPanel
              data={dailyQuestion}
              loading={isDailyQuestionLoading}
              touchpoint="dashboard.daily_question"
              locked={proactiveCopilotLocked}
              entitlementTier={capabilities.entitlementTier}
              onRefreshAccess={handleRefreshProactiveAccess}
              onUpgradeIntent={handleProactiveUpgradeIntent}
              compact={isMobile}
            />
            <GapAnalysisPanel
              id="gap-analysis-panel"
              docs={docs}
              loadingDocs={isDocsLoading}
              touchpoint="dashboard.gap_analysis"
              locked={proactiveCopilotLocked}
              entitlementTier={capabilities.entitlementTier}
              onRefreshAccess={handleRefreshProactiveAccess}
              onUpgradeIntent={handleProactiveUpgradeIntent}
              compact={isMobile}
            />

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
                  <OnboardingChecklist />
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
