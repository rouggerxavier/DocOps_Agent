import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { BarChart3, Download, RotateCcw, SlidersHorizontal, Sparkles, TrendingUp } from 'lucide-react'
import { toast } from 'sonner'

import {
  apiClient,
  type PremiumFunnelTouchpoint,
  type RecommendationCategoryAnalyticsItem,
  type RecommendationTouchpointAnalyticsItem,
  type UserPreferences,
  type UserPreferencesUpdatePayload,
} from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { trackPremiumFeatureActivation, trackPremiumTouchpointViewed, trackUpgradeCompleted, trackUpgradeInitiated } from '@/features/premiumAnalytics'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader, PageShell } from '@/components/ui/page-shell'
import { SectionIntro } from '@/onboarding/SectionIntro'

const DEFAULT_PREFERENCES: UserPreferences = {
  schema_version: 1,
  default_depth: 'brief',
  tone: 'neutral',
  strictness_preference: 'balanced',
  schedule_preference: 'flexible',
}

type Option<T extends string> = {
  value: T
  label: string
  helper: string
}

const DEPTH_OPTIONS: Option<UserPreferences['default_depth']>[] = [
  { value: 'brief', label: 'Breve', helper: 'Sintese objetiva.' },
  { value: 'balanced', label: 'Equilibrado', helper: 'Resumo com contexto.' },
  { value: 'deep', label: 'Profundo', helper: 'Analise detalhada.' },
]

const TONE_OPTIONS: Option<UserPreferences['tone']>[] = [
  { value: 'neutral', label: 'Neutro', helper: 'Direto e claro.' },
  { value: 'didactic', label: 'Didático', helper: 'Explicativo e orientado a estudo.' },
  { value: 'objective', label: 'Objetivo', helper: 'Foco em fatos e passos.' },
  { value: 'encouraging', label: 'Encorajador', helper: 'Tom motivador.' },
]

const STRICTNESS_OPTIONS: Option<UserPreferences['strictness_preference']>[] = [
  { value: 'relaxed', label: 'Relaxado', helper: 'Mais fluido, menos restritivo.' },
  { value: 'balanced', label: 'Equilibrado', helper: 'Compromisso entre fluidez e rigor.' },
  { value: 'strict', label: 'Estrito', helper: 'Maior exigencia de evidencia.' },
]

const SCHEDULE_OPTIONS: Option<UserPreferences['schedule_preference']>[] = [
  { value: 'flexible', label: 'Flexível', helper: 'Ajusta estudo conforme contexto.' },
  { value: 'fixed', label: 'Fixo', helper: 'Mantem rotina previsivel.' },
  { value: 'intensive', label: 'Intensivo', helper: 'Prioriza volume e ritmo alto.' },
]

const ANALYTICS_WINDOW_OPTIONS = [7, 30, 90] as const
type AnalyticsWindowDays = (typeof ANALYTICS_WINDOW_OPTIONS)[number]

function downloadBlobFile(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = filename
  window.document.body.appendChild(link)
  link.click()
  window.document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function asPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return `${(value * 100).toFixed(1)}%`
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function toNullableRate(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function getFunnelStageUsers(item: PremiumFunnelTouchpoint, stageKey: string): number {
  const stageMap = (item as { stages?: Record<string, { users?: unknown }> } | null)?.stages
  const stageUsers = stageMap?.[stageKey]?.users
  return toNumber(stageUsers, 0)
}

function getFunnelViewToActivation(item: PremiumFunnelTouchpoint): number | null {
  const conversion = (item as { conversion?: { view_to_activation?: unknown } } | null)?.conversion
  return toNullableRate(conversion?.view_to_activation)
}

function getActionTotal(value: unknown): number {
  const payload = value as { actions?: { total?: unknown } } | null
  return toNumber(payload?.actions?.total, 0)
}

function getActionUsefulRate(value: unknown): number | null {
  const payload = value as { actions?: { feedback_useful_rate?: unknown } } | null
  return toNullableRate(payload?.actions?.feedback_useful_rate)
}

function readableTouchpoint(raw: string): string {
  const cleaned = String(raw ?? '').trim()
  if (!cleaned) return 'Unknown'
  return cleaned
    .split(/[._:-]/g)
    .filter(Boolean)
    .map(token => token.charAt(0).toUpperCase() + token.slice(1))
    .join(' ')
}

function getApiErrorDetail(error: unknown, fallback: string): string {
  const maybeError = error as { response?: { data?: { detail?: unknown } }; message?: unknown }
  const detail = maybeError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  const message = maybeError?.message
  if (typeof message === 'string' && /html fallback instead of json/i.test(message)) {
    return 'Endpoint de analytics indisponivel nesta instancia da API. Reinicie o backend na branch atual.'
  }
  if (typeof message === 'string' && message.trim()) return message
  return fallback
}

function OptionGroup<T extends string>({
  title,
  subtitle,
  options,
  value,
  disabled,
  onChange,
}: {
  title: string
  subtitle: string
  options: Option<T>[]
  value: T
  disabled?: boolean
  onChange: (next: T) => void
}) {
  return (
    <div className="space-y-2">
      <div>
        <p className="text-sm font-semibold text-zinc-200">{title}</p>
        <p className="text-xs text-zinc-500">{subtitle}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {options.map(option => {
          const selected = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={cn(
                'rounded-xl border px-3 py-2 text-left transition-colors',
                selected
                  ? 'border-blue-700 bg-blue-950/40'
                  : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700',
              )}
            >
              <p className={cn('text-sm font-medium', selected ? 'text-blue-200' : 'text-zinc-200')}>
                {option.label}
              </p>
              <p className="mt-1 text-[11px] text-zinc-500">{option.helper}</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function Preferences() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const capabilities = useCapabilities()
  const analyticsAdmin = Boolean(user?.is_admin)
  const [analyticsWindowDays, setAnalyticsWindowDays] = useState<AnalyticsWindowDays>(30)
  const personalizationEnabled = capabilities.isEnabled('personalization_enabled')
  const personalizationUnlocked = capabilities.hasCapability('premium_personalization')
  const personalizationLocked = personalizationEnabled && !personalizationUnlocked
  const [lastUpgradeTouchpoint, setLastUpgradeTouchpoint] = useState('preferences.memory')
  const [wasPersonalizationLocked, setWasPersonalizationLocked] = useState(personalizationLocked)

  const preferencesQuery = useQuery({
    queryKey: ['user-preferences'],
    queryFn: apiClient.getPreferences,
    enabled: personalizationEnabled && personalizationUnlocked,
    staleTime: 30_000,
    retry: 1,
  })

  const premiumFunnelQuery = useQuery({
    queryKey: ['premium-funnel', analyticsWindowDays],
    queryFn: () => apiClient.getPremiumFunnel(analyticsWindowDays),
    enabled: analyticsAdmin,
    staleTime: 60_000,
    retry: 1,
  })

  const recommendationAnalyticsQuery = useQuery({
    queryKey: ['premium-recommendations-analytics', analyticsWindowDays],
    queryFn: () => apiClient.getPremiumRecommendationAnalytics(analyticsWindowDays),
    enabled: analyticsAdmin,
    staleTime: 60_000,
    retry: 1,
  })

  const updateMutation = useMutation({
    mutationFn: (payload: UserPreferencesUpdatePayload) => apiClient.updatePreferences(payload),
    onSuccess: (next) => {
      queryClient.setQueryData(['user-preferences'], next)
      toast.success('Preferências atualizadas.')
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail ?? error?.message ?? 'Falha ao atualizar preferências.'
      toast.error(String(detail))
    },
  })

  const resetAllMutation = useMutation({
    mutationFn: () => apiClient.resetPreferences(),
    onSuccess: (next) => {
      queryClient.setQueryData(['user-preferences'], next)
      toast.success('Todas as preferências foram redefinidas.')
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail ?? error?.message ?? 'Falha ao redefinir preferências.'
      toast.error(String(detail))
    },
  })

  const preferences = useMemo(
    () => preferencesQuery.data ?? DEFAULT_PREFERENCES,
    [preferencesQuery.data],
  )

  const topFunnelTouchpoints = useMemo(
    () => asArray<PremiumFunnelTouchpoint>(premiumFunnelQuery.data?.touchpoints).slice(0, 4),
    [premiumFunnelQuery.data?.touchpoints],
  )

  const topRecommendationCategories = useMemo(
    () => asArray<RecommendationCategoryAnalyticsItem>(recommendationAnalyticsQuery.data?.categories).slice(0, 4),
    [recommendationAnalyticsQuery.data?.categories],
  )

  const topRecommendationTouchpoints = useMemo(
    () => asArray<RecommendationTouchpointAnalyticsItem>(recommendationAnalyticsQuery.data?.touchpoints).slice(0, 4),
    [recommendationAnalyticsQuery.data?.touchpoints],
  )

  const totalViewedUsers = useMemo(
    () => asArray<PremiumFunnelTouchpoint>(premiumFunnelQuery.data?.touchpoints).reduce(
      (acc, item) => acc + getFunnelStageUsers(item, 'premium_touchpoint_viewed'),
      0,
    ),
    [premiumFunnelQuery.data?.touchpoints],
  )

  const totalActivatedUsers = useMemo(
    () => asArray<PremiumFunnelTouchpoint>(premiumFunnelQuery.data?.touchpoints).reduce(
      (acc, item) => acc + getFunnelStageUsers(item, 'premium_feature_activation'),
      0,
    ),
    [premiumFunnelQuery.data?.touchpoints],
  )

  const overallViewToActivationFromApi = toNullableRate(
    (premiumFunnelQuery.data as { overall?: { conversion?: { view_to_activation?: unknown } } } | undefined)
      ?.overall?.conversion?.view_to_activation,
  )

  const overallViewToActivationRate = useMemo(
    () => (
      overallViewToActivationFromApi
      ?? (totalViewedUsers > 0 ? totalActivatedUsers / totalViewedUsers : null)
    ),
    [overallViewToActivationFromApi, totalActivatedUsers, totalViewedUsers],
  )

  const analyticsLoading = premiumFunnelQuery.isLoading || recommendationAnalyticsQuery.isLoading
  const funnelError = premiumFunnelQuery.error
  const recommendationError = recommendationAnalyticsQuery.error
  const hasFunnelData = toNumber(premiumFunnelQuery.data?.totals?.events, 0) > 0
  const hasRecommendationData = toNumber(recommendationAnalyticsQuery.data?.totals?.events, 0) > 0
  const analyticsHasData = hasFunnelData || hasRecommendationData
  const analyticsUnavailable = !analyticsHasData && Boolean(funnelError) && Boolean(recommendationError)

  const isBusy = updateMutation.isPending || resetAllMutation.isPending

  const handleExportFunnelCsv = async () => {
    try {
      const blob = await apiClient.getPremiumFunnelCsv(analyticsWindowDays)
      downloadBlobFile(blob, `premium-funnel-${analyticsWindowDays}d.csv`)
      toast.success('CSV do funil exportado.')
    } catch (error) {
      toast.error(getApiErrorDetail(error, 'Falha ao exportar CSV do funil.'))
    }
  }

  const handleExportRecommendationCsv = async () => {
    try {
      const blob = await apiClient.getPremiumRecommendationAnalyticsCsv(analyticsWindowDays)
      downloadBlobFile(blob, `premium-recommendacoes-${analyticsWindowDays}d.csv`)
      toast.success('CSV de recomendacoes exportado.')
    } catch (error) {
      toast.error(getApiErrorDetail(error, 'Falha ao exportar CSV de recomendacoes.'))
    }
  }

  const applyPatch = (patch: UserPreferencesUpdatePayload) => {
    if (!personalizationEnabled || !personalizationUnlocked) return
    updateMutation.mutate(patch)
  }

  useEffect(() => {
    if (!personalizationLocked) return
    trackPremiumTouchpointViewed({
      touchpoint: 'preferences.memory',
      capability: 'premium_personalization',
      metadata: { surface: 'preferences' },
    })
  }, [personalizationLocked])

  useEffect(() => {
    if (wasPersonalizationLocked && !personalizationLocked) {
      trackUpgradeCompleted({
        touchpoint: lastUpgradeTouchpoint,
        capability: 'premium_personalization',
        metadata: { surface: 'preferences' },
      })
      trackPremiumFeatureActivation({
        touchpoint: 'preferences.memory',
        capability: 'premium_personalization',
        metadata: { surface: 'preferences', source: 'unlock_transition' },
      })
    }
    setWasPersonalizationLocked(personalizationLocked)
  }, [lastUpgradeTouchpoint, personalizationLocked, wasPersonalizationLocked])

  useEffect(() => {
    if (!(personalizationEnabled && personalizationUnlocked) || preferencesQuery.isLoading || preferencesQuery.isError) return
    trackPremiumFeatureActivation({
      touchpoint: 'preferences.memory',
      capability: 'premium_personalization',
      metadata: { surface: 'preferences', source: 'preferences_loaded' },
    })
  }, [personalizationEnabled, personalizationUnlocked, preferencesQuery.isError, preferencesQuery.isLoading])

  const handleUpgradeIntent = (source: 'link' | 'refresh_access') => {
    setLastUpgradeTouchpoint('preferences.memory')
    trackUpgradeInitiated({
      touchpoint: 'preferences.memory',
      capability: 'premium_personalization',
      metadata: { surface: 'preferences', source },
    })
  }

  const handleRefreshCapabilities = async () => {
    handleUpgradeIntent('refresh_access')
    await capabilities.refresh()
    await queryClient.invalidateQueries({ queryKey: ['user-preferences'] })
    await queryClient.invalidateQueries({ queryKey: ['premium-funnel'] })
    await queryClient.invalidateQueries({ queryKey: ['premium-recommendations-analytics'] })
    toast.info('Acesso atualizado. Se o upgrade já foi aplicado, recarregamos as capacidades.')
  }

  const resetResponseBehavior = () => {
    applyPatch({
      default_depth: DEFAULT_PREFERENCES.default_depth,
      tone: DEFAULT_PREFERENCES.tone,
      strictness_preference: DEFAULT_PREFERENCES.strictness_preference,
    })
  }

  const resetStudyBehavior = () => {
    applyPatch({
      schedule_preference: DEFAULT_PREFERENCES.schedule_preference,
    })
  }

  return (
    <PageShell className="space-y-6">
      <SectionIntro sectionId="settings" />
      <PageHeader
        title="Configurações de Preferência"
        subtitle="Controle o estilo padrão das respostas e o comportamento de estudo."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={!personalizationEnabled || isBusy}
            onClick={() => resetAllMutation.mutate()}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Resetar tudo
          </Button>
        }
      />

      {analyticsAdmin ? (
        <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                <BarChart3 className="h-4 w-4 text-cyan-400" />
                Conversao e Valor Premium
              </CardTitle>
              <p className="mt-1 text-xs text-zinc-500">
                Janela de {analyticsWindowDays} dias para acompanhar conversao e qualidade das recomendacoes.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-1">
                {ANALYTICS_WINDOW_OPTIONS.map(days => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => setAnalyticsWindowDays(days)}
                    className={cn(
                      'rounded-md px-2 py-1 text-xs transition-colors',
                      analyticsWindowDays === days
                        ? 'bg-blue-900/50 text-blue-200'
                        : 'text-zinc-400 hover:text-zinc-200',
                    )}
                  >
                    {days}d
                  </button>
                ))}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleExportFunnelCsv}
                disabled={analyticsLoading || !analyticsHasData}
              >
                <Download className="h-3.5 w-3.5" />
                CSV funil
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleExportRecommendationCsv}
                disabled={analyticsLoading || !analyticsHasData}
              >
                <Download className="h-3.5 w-3.5" />
                CSV qualidade
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {analyticsLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full rounded-xl" />
              <Skeleton className="h-24 w-full rounded-xl" />
            </div>
          ) : analyticsUnavailable ? (
            <div className="rounded-xl border border-rose-500/40 bg-rose-950/20 px-3 py-2 text-xs text-rose-200">
              {getApiErrorDetail(
                recommendationError ?? funnelError,
                'Nao foi possivel carregar analytics premium.',
              )}
            </div>
          ) : (
            <>
              {funnelError && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                  Nao foi possivel carregar parte do funil de conversao. Exibindo dados parciais.
                </div>
              )}
              {recommendationError && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                  Nao foi possivel carregar analytics de qualidade das recomendacoes. Exibindo dados disponiveis.
                </div>
              )}
              {!analyticsHasData ? (
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-400">
                  Ainda sem eventos suficientes para analytics premium nesta janela.
                </div>
              ) : null}

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">Eventos de funil</p>
                  <p className="mt-1 text-xl font-semibold text-zinc-100">{toNumber(premiumFunnelQuery.data?.totals?.events, 0)}</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">Usuarios tocados</p>
                  <p className="mt-1 text-xl font-semibold text-zinc-100">{toNumber(premiumFunnelQuery.data?.totals?.users, 0)}</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">View para ativacao</p>
                  <p className="mt-1 text-xl font-semibold text-emerald-300">{asPercent(overallViewToActivationRate)}</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">Feedback util</p>
                  <p className="mt-1 text-xl font-semibold text-cyan-300">
                    {asPercent(getActionUsefulRate(recommendationAnalyticsQuery.data))}
                  </p>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-3">
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <TrendingUp className="h-3.5 w-3.5 text-emerald-300" />
                    <p className="text-xs font-medium text-zinc-300">Top touchpoints de conversao</p>
                  </div>
                  <div className="space-y-2">
                    {topFunnelTouchpoints.length === 0 && (
                      <p className="text-xs text-zinc-500">Sem touchpoints no periodo.</p>
                    )}
                    {topFunnelTouchpoints.map((item: PremiumFunnelTouchpoint) => (
                      <div key={item.touchpoint} className="rounded-lg border border-zinc-800 px-2 py-1.5">
                        <p className="text-xs font-medium text-zinc-200">{readableTouchpoint(item.touchpoint)}</p>
                        <p className="mt-1 text-[11px] text-zinc-500">
                          View: {getFunnelStageUsers(item, 'premium_touchpoint_viewed')} | Ativacoes: {getFunnelStageUsers(item, 'premium_feature_activation')}
                        </p>
                        <p className="text-[11px] text-emerald-300">
                          Conversao: {asPercent(getFunnelViewToActivation(item))}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
                  <p className="mb-2 text-xs font-medium text-zinc-300">Qualidade por categoria</p>
                  <div className="space-y-2">
                    {topRecommendationCategories.length === 0 && (
                      <p className="text-xs text-zinc-500">Sem categorias de recomendacao no periodo.</p>
                    )}
                    {topRecommendationCategories.map((item: RecommendationCategoryAnalyticsItem) => (
                      <div key={item.category} className="rounded-lg border border-zinc-800 px-2 py-1.5">
                        <p className="text-xs font-medium text-zinc-200">{item.category}</p>
                        <p className="mt-1 text-[11px] text-zinc-500">
                          Acoes: {getActionTotal(item)} | Recom.: {toNumber(item.recommendations, 0)} | Usuarios: {toNumber(item.users, 0)}
                        </p>
                        <p className="text-[11px] text-cyan-300">
                          Feedback util: {asPercent(getActionUsefulRate(item))}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
                  <p className="mb-2 text-xs font-medium text-zinc-300">Qualidade por touchpoint</p>
                  <div className="space-y-2">
                    {topRecommendationTouchpoints.length === 0 && (
                      <p className="text-xs text-zinc-500">Sem acoes de recomendacao por touchpoint.</p>
                    )}
                    {topRecommendationTouchpoints.map((item: RecommendationTouchpointAnalyticsItem) => (
                      <div key={item.touchpoint} className="rounded-lg border border-zinc-800 px-2 py-1.5">
                        <p className="text-xs font-medium text-zinc-200">{readableTouchpoint(item.touchpoint)}</p>
                        <p className="mt-1 text-[11px] text-zinc-500">
                          Acoes: {getActionTotal(item)} | Recom.: {toNumber(item.recommendations, 0)} | Usuarios: {toNumber(item.users, 0)}
                        </p>
                        <p className="text-[11px] text-cyan-300">
                          Feedback util: {asPercent(getActionUsefulRate(item))}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </CardContent>
        </Card>
      ) : null}

      {!personalizationEnabled && (
        <Card className="border-zinc-800 bg-zinc-900">
          <CardContent className="pt-6">
            <p className="text-sm text-zinc-300">
              Personalização está desativada por configuração do workspace.
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              Ative a feature flag `personalization_enabled` para liberar preferências de memória.
            </p>
          </CardContent>
        </Card>
      )}

      {personalizationLocked && (
        <Card className="border-amber-500/30 bg-amber-950/15">
          <CardContent className="space-y-3 pt-6">
            <p className="text-sm font-medium text-amber-200">
              Recurso premium bloqueado no seu plano atual ({capabilities.entitlementTier}).
            </p>
            <p className="text-xs text-amber-100/85">
              Memória e preferências persistentes exigem upgrade de entitlement para `premium_personalization`.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={handleRefreshCapabilities}>
                Já fiz upgrade, atualizar acesso
              </Button>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/dashboard" onClick={() => handleUpgradeIntent('link')}>Ver recursos premium no dashboard</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {personalizationEnabled && personalizationUnlocked && preferencesQuery.isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
      )}

      {personalizationEnabled && personalizationUnlocked && !preferencesQuery.isLoading && (
        <>
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Sparkles className="h-4 w-4 text-blue-400" />
                Comportamento de Resposta
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <OptionGroup
                title="Profundidade padrão"
                subtitle="Define o nível padrão de detalhe nas respostas."
                options={DEPTH_OPTIONS}
                value={preferences.default_depth}
                disabled={isBusy}
                onChange={(next) => applyPatch({ default_depth: next })}
              />
              <OptionGroup
                title="Tom padrão"
                subtitle="Ajusta o estilo de explicação usado pelo assistente."
                options={TONE_OPTIONS}
                value={preferences.tone}
                disabled={isBusy}
                onChange={(next) => applyPatch({ tone: next })}
              />
              <OptionGroup
                title="Preferência de rigor"
                subtitle="Controla quão conservadora a resposta deve ser com evidências."
                options={STRICTNESS_OPTIONS}
                value={preferences.strictness_preference}
                disabled={isBusy}
                onChange={(next) => applyPatch({ strictness_preference: next })}
              />
              <div className="flex items-center justify-end">
                <Button variant="ghost" size="sm" disabled={isBusy} onClick={resetResponseBehavior}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  Resetar comportamento de resposta
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <SlidersHorizontal className="h-4 w-4 text-emerald-400" />
                Comportamento de Estudo
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <OptionGroup
                title="Ritmo de rotina"
                subtitle="Preferência usada para orientar sugestões de agenda e plano."
                options={SCHEDULE_OPTIONS}
                value={preferences.schedule_preference}
                disabled={isBusy}
                onChange={(next) => applyPatch({ schedule_preference: next })}
              />
              <div className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-500">
                <span>No chat, mostramos quando as respostas estão usando essas preferências.</span>
                <Link to="/chat" className="text-blue-400 hover:text-blue-300">
                  Ir para chat
                </Link>
              </div>
              <div className="flex items-center justify-end">
                <Button variant="ghost" size="sm" disabled={isBusy} onClick={resetStudyBehavior}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  Resetar comportamento de estudo
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </PageShell>
  )
}

