import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { RotateCcw, SlidersHorizontal, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { apiClient, type UserPreferences, type UserPreferencesUpdatePayload } from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader, PageShell } from '@/components/ui/page-shell'

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
  const capabilities = useCapabilities()
  const personalizationEnabled = capabilities.isEnabled('personalization_enabled')

  const preferencesQuery = useQuery({
    queryKey: ['user-preferences'],
    queryFn: apiClient.getPreferences,
    enabled: personalizationEnabled,
    staleTime: 30_000,
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

  const isBusy = updateMutation.isPending || resetAllMutation.isPending

  const applyPatch = (patch: UserPreferencesUpdatePayload) => {
    if (!personalizationEnabled) return
    updateMutation.mutate(patch)
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

      {personalizationEnabled && preferencesQuery.isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
      )}

      {personalizationEnabled && !preferencesQuery.isLoading && (
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

