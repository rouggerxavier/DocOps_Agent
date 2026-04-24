import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  apiClient,
  type OnboardingEventRequest,
  type OnboardingEventResponse,
  type OnboardingStateResponse,
} from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'

const QUERY_KEY = ['onboarding-state']

interface OnboardingContextValue {
  state: OnboardingStateResponse | undefined
  loading: boolean
  postEvent: (payload: OnboardingEventRequest) => Promise<OnboardingEventResponse>
  isPending: boolean
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const capabilities = useCapabilities()
  const enabled = capabilities.isEnabled('onboarding_enabled')
  const queryClient = useQueryClient()

  const { data: state, isLoading: loading } = useQuery<OnboardingStateResponse>({
    queryKey: QUERY_KEY,
    queryFn: apiClient.getOnboardingState,
    enabled,
    staleTime: 60_000,
    retry: 1,
  })

  const mutation = useMutation<OnboardingEventResponse, Error, OnboardingEventRequest>({
    mutationFn: apiClient.postOnboardingEvent,
    onSuccess: (result) => {
      queryClient.setQueryData(QUERY_KEY, result.state)
    },
  })

  const postEvent = useCallback(
    (payload: OnboardingEventRequest) => mutation.mutateAsync(payload),
    [mutation],
  )

  const value = useMemo<OnboardingContextValue>(
    () => ({ state, loading, postEvent, isPending: mutation.isPending }),
    [state, loading, postEvent, mutation.isPending],
  )

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>
}

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  return ctx
}
