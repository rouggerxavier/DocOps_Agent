import { apiClient } from '@/api/client'

type TrackOptions = {
  touchpoint: string
  capability?: string
  metadata?: Record<string, unknown>
}

const viewedTouchpoints = new Set<string>()
const activatedTouchpoints = new Set<string>()

function toKey(options: TrackOptions): string {
  const touchpoint = String(options.touchpoint || '').trim().toLowerCase()
  const capability = String(options.capability || '').trim().toLowerCase()
  return `${touchpoint}::${capability}`
}

function track(eventType: 'premium_touchpoint_viewed' | 'upgrade_initiated' | 'upgrade_completed' | 'premium_feature_activation', options: TrackOptions) {
  const touchpoint = String(options.touchpoint || '').trim().toLowerCase()
  if (!touchpoint) return

  void apiClient.trackPremiumAnalyticsEvent({
    event_type: eventType,
    touchpoint,
    capability: options.capability,
    metadata: options.metadata ?? {},
  }).catch(() => {
    // Analytics should never break product flows.
  })
}

export function trackPremiumTouchpointViewed(options: TrackOptions) {
  const key = toKey(options)
  if (!key || viewedTouchpoints.has(key)) return
  viewedTouchpoints.add(key)
  track('premium_touchpoint_viewed', options)
}

export function trackUpgradeInitiated(options: TrackOptions) {
  track('upgrade_initiated', options)
}

export function trackUpgradeCompleted(options: TrackOptions) {
  track('upgrade_completed', options)
}

export function trackPremiumFeatureActivation(options: TrackOptions, oncePerSession = true) {
  const key = toKey(options)
  if (!key) return
  if (oncePerSession && activatedTouchpoints.has(key)) return
  if (oncePerSession) {
    activatedTouchpoints.add(key)
  }
  track('premium_feature_activation', options)
}
