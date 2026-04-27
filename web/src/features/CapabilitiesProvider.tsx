import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import { apiClient, type CapabilitiesResponse } from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'

export type FeatureFlagKey =
  | 'chat_streaming_enabled'
  | 'strict_grounding_enabled'
  | 'premium_trust_layer_enabled'
  | 'premium_artifact_templates_enabled'
  | 'premium_chat_to_artifact_enabled'
  | 'personalization_enabled'
  | 'proactive_copilot_enabled'
  | 'premium_entitlements_enabled'
  | 'onboarding_enabled'

export type EntitlementCapabilityKey =
  | 'premium_artifact_templates'
  | 'premium_chat_to_artifact'
  | 'premium_personalization'
  | 'premium_proactive_copilot'

const DEFAULT_FLAG_MAP: Record<FeatureFlagKey, boolean> = {
  chat_streaming_enabled: true,
  strict_grounding_enabled: true,
  premium_trust_layer_enabled: false,
  premium_artifact_templates_enabled: false,
  premium_chat_to_artifact_enabled: false,
  personalization_enabled: false,
  proactive_copilot_enabled: false,
  premium_entitlements_enabled: false,
  onboarding_enabled: true,
}

const DEFAULT_ENTITLEMENT_MAP: Record<EntitlementCapabilityKey, boolean> = {
  premium_artifact_templates: true,
  premium_chat_to_artifact: true,
  premium_personalization: true,
  premium_proactive_copilot: true,
}

interface CapabilitiesContextValue {
  flags: Record<string, boolean>
  entitlements: Record<string, boolean>
  isEnabled: (flag: FeatureFlagKey | string) => boolean
  hasCapability: (capability: EntitlementCapabilityKey | string) => boolean
  loading: boolean
  disableAll: boolean
  enableAll: boolean
  entitlementsEnabled: boolean
  entitlementTier: string
  refresh: () => Promise<unknown>
}

const CapabilitiesContext = createContext<CapabilitiesContextValue | null>(null)

function mergeFlags(data: CapabilitiesResponse | undefined): Record<string, boolean> {
  const result: Record<string, boolean> = { ...DEFAULT_FLAG_MAP }
  const source = data?.map ?? {}
  for (const [key, value] of Object.entries(source)) {
    result[key] = Boolean(value)
  }
  return result
}

function mergeEntitlements(data: CapabilitiesResponse | undefined): Record<string, boolean> {
  const result: Record<string, boolean> = { ...DEFAULT_ENTITLEMENT_MAP }
  const source = data?.entitlement_map ?? {}
  for (const [key, value] of Object.entries(source)) {
    result[key] = Boolean(value)
  }
  return result
}

export function CapabilitiesProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: apiClient.getCapabilities,
    enabled: Boolean(token),
    staleTime: 60_000,
    retry: 1,
  })

  const flags = useMemo(() => mergeFlags(query.data), [query.data])
  const entitlements = useMemo(() => mergeEntitlements(query.data), [query.data])
  const value = useMemo<CapabilitiesContextValue>(
    () => ({
      flags,
      entitlements,
      isEnabled: (flag: FeatureFlagKey | string) => Boolean(flags[String(flag)]),
      hasCapability: (capability: EntitlementCapabilityKey | string) => Boolean(entitlements[String(capability)]),
      loading: query.isLoading && !query.data,
      disableAll: Boolean(query.data?.disable_all),
      enableAll: Boolean(query.data?.enable_all),
      entitlementsEnabled: Boolean(query.data?.entitlements_enabled),
      entitlementTier: String(query.data?.entitlement_tier ?? 'free'),
      refresh: () => query.refetch(),
    }),
    [entitlements, flags, query]
  )

  return (
    <CapabilitiesContext.Provider value={value}>
      {children}
    </CapabilitiesContext.Provider>
  )
}

export function useCapabilities(): CapabilitiesContextValue {
  const ctx = useContext(CapabilitiesContext)
  if (!ctx) {
    throw new Error('useCapabilities deve ser usado dentro de <CapabilitiesProvider>')
  }
  return ctx
}
