import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  apiClient,
  type OnboardingEventRequest,
  type OnboardingEventResponse,
  type OnboardingStateResponse,
} from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { WelcomeModal } from './WelcomeModal'
import { HotspotTour } from './HotspotTour'

const QUERY_KEY = ['onboarding-state']

interface OnboardingContextValue {
  state: OnboardingStateResponse | undefined
  loading: boolean
  postEvent: (payload: OnboardingEventRequest) => Promise<OnboardingEventResponse>
  isPending: boolean
  activeTour: string | null
  startTour: (sectionId: string) => void
  closeTour: () => void
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const capabilities = useCapabilities()
  const enabled = capabilities.isEnabled('onboarding_enabled')
  const queryClient = useQueryClient()

  const [activeTour, setActiveTour] = useState<string | null>(null)

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

  const startTour = useCallback((sectionId: string) => setActiveTour(sectionId), [])
  const closeTour = useCallback(() => setActiveTour(null), [])

  const value = useMemo<OnboardingContextValue>(
    () => ({ state, loading, postEvent, isPending: mutation.isPending, activeTour, startTour, closeTour }),
    [state, loading, postEvent, mutation.isPending, activeTour, startTour, closeTour],
  )

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      <WelcomeModal />
      <HotspotTour />
    </OnboardingContext.Provider>
  )
}

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  return ctx
}
