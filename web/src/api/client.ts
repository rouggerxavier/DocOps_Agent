import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000, // 15s — evita tela preta se o backend não responder
})

api.interceptors.response.use(
  (response) => {
    const url = String(response.config?.url ?? '')
    const responseType = String(response.config?.responseType ?? 'json').toLowerCase()
    const contentType = String(response.headers?.['content-type'] ?? '').toLowerCase()

    // If an API request expects JSON but receives app HTML fallback, fail fast.
    const expectsJson = responseType === 'json'
    if (expectsJson && url.includes('/api/') && contentType.includes('text/html')) {
      const error = new Error(
        `API endpoint returned HTML fallback instead of JSON: ${url}.`,
      ) as Error & {
        response?: typeof response
        is_api_html_fallback?: boolean
      }
      error.response = response
      error.is_api_html_fallback = true
      throw error
    }

    return response
  },
  (error) => Promise.reject(error),
)

const INGEST_TIMEOUT_MS = 180000
const FLASHCARD_GENERATION_TIMEOUT_MS = 180000

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DocItem {
  doc_id: string
  file_name: string
  source: string
  chunk_count: number
}

export interface SourceItem {
  fonte_n: number
  file_name: string
  page: string
  snippet: string
  chunk_id: string
}

export interface ChatQualitySignal {
  level: 'high' | 'medium' | 'low'
  score: number
  label: string
  reasons: string[]
  reason_codes?: string[]
  score_components?: {
    support_rate: number
    source_breadth: number
    unsupported_claims: number
    retrieval_depth: number
  }
  support_rate?: number | null
  unsupported_claim_count?: number
  suggested_action?: string | null
  source_count: number
  retrieved_count: number
}

export interface ChatResponse {
  answer: string
  sources: SourceItem[]
  intent: string
  session_id: string | null
  calendar_action: Record<string, any> | null
  quality_signal?: ChatQualitySignal | null
  action_metadata?: Record<string, any> | null
  needs_confirmation?: boolean
  confirmation_text?: string | null
  suggested_reply?: string | null
  active_context?: Record<string, any> | null
}

export interface CapabilityFlag {
  key: string
  enabled: boolean
  env_var: string
  default_enabled: boolean
  description: string
  owner: string
}

export interface CapabilitiesResponse {
  flags: CapabilityFlag[]
  map: Record<string, boolean>
  disable_all: boolean
  enable_all: boolean
  entitlements_enabled: boolean
  entitlement_tier: string
  entitlement_map: Record<string, boolean>
  entitlement_capabilities: EntitlementCapability[]
}

export interface EntitlementCapability {
  key: string
  enabled: boolean
  required_tier: string
  description: string
}

export interface LockedFeatureDetail {
  error: string
  code: string
  message: string
  capability: string
  required_tier: string
  current_tier: string
}

export interface UserPreferences {
  schema_version: number
  default_depth: 'brief' | 'balanced' | 'deep'
  tone: 'neutral' | 'didactic' | 'objective' | 'encouraging'
  strictness_preference: 'relaxed' | 'balanced' | 'strict'
  schedule_preference: 'flexible' | 'fixed' | 'intensive'
}

export interface UserPreferencesUpdatePayload {
  default_depth?: UserPreferences['default_depth']
  tone?: UserPreferences['tone']
  strictness_preference?: UserPreferences['strictness_preference']
  schedule_preference?: UserPreferences['schedule_preference']
}

export interface ChatStreamCallbacks {
  onStart?: () => void
  onStatus?: (status: { stage: string; detail?: string | null }) => void
  onDelta?: (delta: string) => void
  onError?: (detail: string) => void
}

export interface ChatRequestOptions {
  streamFallback?: boolean
}

export class ChatStreamError extends Error {
  statusCode: number | null
  recoverable: boolean
  reason: string

  constructor(
    message: string,
    options?: {
      statusCode?: number | null
      recoverable?: boolean
      reason?: string
    },
  ) {
    super(message)
    this.name = 'ChatStreamError'
    this.statusCode = options?.statusCode ?? null
    this.recoverable = options?.recoverable ?? true
    this.reason = options?.reason ?? 'stream_failure'
  }
}

export interface JobCreateResponse {
  job_id: string
  status: string
  progress: number
  stage: string
}

export interface JobStatusResponse {
  job_id: string
  status: string
  progress: number
  stage: string
  result: Record<string, any> | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface IngestResponse {
  files_loaded: number
  chunks_indexed: number
  file_names: string[]
}

export interface ArtifactItem {
  id: number
  filename: string
  size: number
  created_at: string
  artifact_type: string
  title: string | null
  template_id?: string | null
  generation_profile?: string | null
  confidence_level?: 'high' | 'medium' | 'low' | string | null
  confidence_score?: number | null
  metadata_version?: number
  source_doc_ids?: string[]
  source_doc_count?: number
  conversation_session_id?: string | null
  conversation_turn_ref?: string | null
}

export interface ArtifactResponse {
  answer: string
  filename: string
  path: string
  template_id?: string | null
  template_label?: string | null
  template_description?: string | null
  artifact_id?: number | null
}

export interface ChatArtifactCreatePayload {
  answer: string
  title?: string
  user_prompt?: string
  session_id?: string
  turn_ref?: string
  doc_ids?: string[]
  doc_names?: string[]
  template_id?: string
  artifact_type?: string
  generation_profile?: string
  confidence_level?: string
  confidence_score?: number
}

export interface ChatArtifactResponse extends ArtifactResponse {
  conversation_session_id?: string | null
  conversation_turn_ref?: string | null
}

export interface SummarizeResponse {
  answer: string
  artifact_path: string | null
  artifact_filename?: string | null
  template_id?: string | null
  template_label?: string | null
  template_description?: string | null
}

export interface CompareResponse {
  answer: string
  artifact_path: string | null
}

export interface ArtifactTemplate {
  template_id: string
  label: string
  short_description: string
  long_description: string
  preview_title: string
  preview_sections: string[]
  artifact_types: string[]
  summary_modes: string[]
  default_for_summary_modes: string[]
  default_for_artifact_types: string[]
  locked?: boolean
}

export interface ArtifactFilterOptions {
  artifact_types: string[]
  template_ids: string[]
  generation_profiles: string[]
  source_doc_ids: string[]
  confidence_levels: string[]
}

export interface ArtifactListQuery {
  artifact_type?: string
  source_doc_id?: string
  conversation_session_id?: string
  template_id?: string
  generation_profile?: string
  search?: string
  sort_by?: 'created_at' | 'updated_at' | 'title' | 'artifact_type' | 'confidence_score' | 'filename' | string
  sort_order?: 'asc' | 'desc'
}

export interface ReminderItem {
  id: number
  title: string
  starts_at: string
  ends_at: string | null
  note: string | null
  all_day: boolean
}

export interface ScheduleItem {
  id: number
  title: string
  day_of_week: number
  start_time: string
  end_time: string
  note: string | null
  active: boolean
}

export interface CalendarOverview {
  date: string
  now_iso: string
  today_reminders: ReminderItem[]
  today_schedule: ScheduleItem[]
  current_schedule_item: ScheduleItem | null
  next_schedule_item: ScheduleItem | null
}

export interface NoteItem {
  id: number
  title: string
  content: string
  pinned: boolean
  created_at: string
  updated_at: string
}

export interface TaskItem {
  id: number
  title: string
  note: string | null
  status: string
  priority: string
  due_date: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  checklist_done: number
  checklist_total: number
}

export interface TaskChecklistItem {
  id: number
  task_id: number
  text: string
  done: boolean
  position: number
  created_at: string
}

export interface TaskActivityLog {
  id: number
  task_id: number
  text: string
  created_at: string
}

export interface BriefingTask {
  id: number
  title: string
  priority: string
  due_date: string | null
}

export interface BriefingReminder {
  id: number
  title: string
  starts_at: string
  all_day: boolean
  note: string | null
}

export interface BriefingScheduleItem {
  title: string
  start_time: string
  end_time: string
}

export interface BriefingResponse {
  date: string
  greeting: string
  today_reminders: BriefingReminder[]
  today_schedule: BriefingScheduleItem[]
  pending_tasks: BriefingTask[]
  overdue_tasks: BriefingTask[]
  docs_count: number
  notes_count: number
}

// ── Flashcards ────────────────────────────────────────────────────────────────

export interface FlashcardCard {
  id: number
  front: string
  back: string
  difficulty: string  // facil, media, dificil
  ease: number
  next_review: string | null
}

export interface FlashcardDeck {
  id: number
  title: string
  source_doc: string | null
  created_at: string
  cards: FlashcardCard[]
}

export interface FlashcardDeckListItem {
  id: number
  title: string
  source_doc: string | null
  card_count: number
  created_at: string
}

export interface FlashcardBatchItem {
  requested_doc_name: string
  source_doc: string | null
  status: 'created' | 'failed'
  deck: FlashcardDeck | null
  error: string | null
}

export interface FlashcardBatchResponse {
  requested_docs: number
  created: number
  failed: number
  items: FlashcardBatchItem[]
}

// ── Study Plan ────────────────────────────────────────────────────────────────

export interface StudyPlanResponse {
  plan: string
  artifact_filename: string | null
  pdf_filename: string | null
}

export interface StudyPlanConflict {
  date: string
  session_time: string
  conflicting_with: string
  conflicting_time: string
}

export interface StudyPlanDocResponse {
  plan_text: string
  tasks_created: number
  reminders_created: number
  sessions_count: number
  deck_id: number | null
  titulo: string
  study_plan_id: number | null
  conflicts: StudyPlanConflict[]
}

export interface StudyPlanItem {
  id: number
  titulo: string
  doc_name: string
  tasks_created: number
  reminders_created: number
  sessions_count: number
  deck_id: number | null
  hours_per_day: number
  deadline_date: string
  created_at: string
  plan_text: string
}

// ── Daily Question ─────────────────────────────────────────────────────────────

export interface DailyQuestionResponse {
  question: string | null
  answer_hint: string | null
  doc_name: string | null
  date: string
}

export interface EvaluateAnswerResponse {
  feedback: string
  score: 'excelente' | 'bom' | 'parcial' | 'incorreto' | 'sem_resposta'
}

// ── Gap Analysis ──────────────────────────────────────────────────────────────

export interface GapItem {
  topico: string
  descricao: string
  prioridade: 'high' | 'normal' | 'low'
  sugestao: string
}

export interface GapAnalysisResponse {
  gaps: GapItem[]
  docs_analyzed: number
}

export type ProactiveRecommendationCategory = 'coverage' | 'schedule' | 'quality' | 'consistency'

export type ProactiveRecommendationAction =
  | 'dismiss'
  | 'snooze'
  | 'mute_category'
  | 'feedback_useful'
  | 'feedback_not_useful'

export interface ProactiveRecommendationItem {
  id: string
  category: ProactiveRecommendationCategory
  title: string
  description: string
  why_this: string
  action_label: string
  action_to: string
  score: number
  signals: Record<string, any>
}

export interface ProactiveRecommendationsResponse {
  generated_at: string
  recommendation_count: number
  recommendations: ProactiveRecommendationItem[]
}

export interface ProactiveRecommendationActionPayload {
  recommendation_id: string
  category?: ProactiveRecommendationCategory
  action: ProactiveRecommendationAction
  duration_hours?: number
  feedback_note?: string
}

export interface ProactiveRecommendationActionResponse {
  status: string
  action: ProactiveRecommendationAction
  event_type: string
  recommendation_id: string
  category: ProactiveRecommendationCategory | null
  effective_until: string | null
}

export type PremiumAnalyticsEventType =
  | 'premium_touchpoint_viewed'
  | 'upgrade_initiated'
  | 'upgrade_completed'
  | 'premium_feature_activation'

export interface PremiumAnalyticsTrackPayload {
  event_type: PremiumAnalyticsEventType
  touchpoint: string
  capability?: string
  metadata?: Record<string, any>
}

export interface PremiumAnalyticsTrackResponse {
  status: string
  id: number
  event_type: PremiumAnalyticsEventType
  touchpoint: string
  capability?: string | null
  created_at: string
}

export interface PremiumFunnelStageStats {
  events: number
  users: number
}

export interface PremiumFunnelTouchpoint {
  touchpoint: string
  capability?: string | null
  stages: Record<PremiumAnalyticsEventType, PremiumFunnelStageStats>
  conversion: {
    view_to_upgrade_initiated: number | null
    initiated_to_completed: number | null
    completed_to_activation: number | null
    view_to_activation: number | null
  }
}

export interface PremiumFunnelOverall {
  viewed_users: number
  upgrade_initiated_users: number
  upgrade_completed_users: number
  activated_users: number
  conversion: {
    view_to_upgrade_initiated: number | null
    initiated_to_completed: number | null
    completed_to_activation: number | null
    view_to_activation: number | null
  }
}

export interface PremiumFunnelResponse {
  window_days: number
  generated_at: string
  totals: {
    events: number
    users: number
    touchpoints: number
  }
  overall: PremiumFunnelOverall
  touchpoints: PremiumFunnelTouchpoint[]
}

export type RecommendationAnalyticsAction =
  | 'dismiss'
  | 'snooze'
  | 'mute_category'
  | 'feedback_useful'
  | 'feedback_not_useful'

export interface RecommendationAnalyticsActionBreakdown {
  dismiss: number
  snooze: number
  mute_category: number
  feedback_useful: number
  feedback_not_useful: number
  total: number
  feedback_useful_rate: number | null
}

export interface RecommendationCategoryAnalyticsItem {
  category: string
  actions: RecommendationAnalyticsActionBreakdown
  users: number
  recommendations: number
}

export interface RecommendationTouchpointAnalyticsItem {
  touchpoint: string
  actions: RecommendationAnalyticsActionBreakdown
  users: number
  recommendations: number
}

export interface RecommendationAnalyticsTotals {
  events: number
  users: number
  categories: number
  touchpoints: number
  recommendations: number
}

export interface PremiumRecommendationAnalyticsResponse {
  window_days: number
  generated_at: string
  totals: RecommendationAnalyticsTotals
  actions: RecommendationAnalyticsActionBreakdown
  categories: RecommendationCategoryAnalyticsItem[]
  touchpoints: RecommendationTouchpointAnalyticsItem[]
}

// ── Reading Status ─────────────────────────────────────────────────────────────

export type ReadingStatus = 'to_read' | 'reading' | 'done'

function looksLikeLockedDetail(value: unknown): value is LockedFeatureDetail {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    candidate.error === 'feature_locked'
    && typeof candidate.capability === 'string'
    && typeof candidate.required_tier === 'string'
    && typeof candidate.current_tier === 'string'
  )
}

export function extractLockedFeatureDetail(error: unknown): LockedFeatureDetail | null {
  const maybeError = error as {
    response?: {
      status?: number
      data?: {
        detail?: unknown
      }
    }
  }
  if (Number(maybeError?.response?.status) !== 403) return null
  const detail = maybeError?.response?.data?.detail
  return looksLikeLockedDetail(detail) ? detail : null
}

export function isLockedFeatureError(error: unknown): boolean {
  return extractLockedFeatureDetail(error) !== null
}

// ── API functions ─────────────────────────────────────────────────────────────

export const apiClient = {
  health: () => api.get('/api/health').then(r => r.data),

  listDocs: (): Promise<DocItem[]> =>
    api.get('/api/docs').then(r => r.data),

  getCapabilities: (): Promise<CapabilitiesResponse> =>
    api.get('/api/capabilities').then(r => r.data),

  getPreferences: (): Promise<UserPreferences> =>
    api.get('/api/preferences').then(r => r.data),

  updatePreferences: (payload: UserPreferencesUpdatePayload): Promise<UserPreferences> =>
    api.put('/api/preferences', payload).then(r => r.data),

  resetPreferences: (): Promise<UserPreferences> =>
    api.post('/api/preferences/reset').then(r => r.data),

  deleteDoc: (docId: string): Promise<void> =>
    api.delete(`/api/docs/${encodeURIComponent(docId)}`).then(() => undefined),

  chat: (
    message: string,
    session_id?: string,
    top_k?: number,
    doc_names?: string[],
    strict_grounding?: boolean,
    history?: Array<{ role: 'user' | 'assistant'; content: string }>,
    active_context?: Record<string, any> | null,
    options?: ChatRequestOptions,
  ): Promise<ChatResponse> =>
    api.post(
      '/api/chat',
      { message, session_id, top_k, doc_names, strict_grounding, history, active_context },
      {
        timeout: 180000,
        headers: options?.streamFallback ? { 'X-DocOps-Stream-Fallback': '1' } : undefined,
      },
    ).then(r => r.data),

  chatStream: async (
    message: string,
    session_id?: string,
    top_k?: number,
    doc_names?: string[],
    strict_grounding?: boolean,
    history?: Array<{ role: 'user' | 'assistant'; content: string }>,
    active_context?: Record<string, any> | null,
    callbacks?: ChatStreamCallbacks,
    signal?: AbortSignal,
  ): Promise<ChatResponse> => {
    const token = localStorage.getItem('docops_token')
    const resp = await fetch(`${BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        session_id,
        top_k,
        doc_names,
        strict_grounding,
        history,
        active_context,
      }),
      signal,
    })

    const isRecoverableStatus = (statusCode: number): boolean => (
      statusCode >= 500 || statusCode === 408 || statusCode === 429
    )

    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      throw new ChatStreamError(
        detail || `HTTP ${resp.status}`,
        {
          statusCode: resp.status,
          recoverable: isRecoverableStatus(resp.status),
          reason: 'http_error',
        },
      )
    }
    if (!resp.body) {
      throw new ChatStreamError(
        'Stream indisponivel no navegador.',
        { recoverable: true, reason: 'missing_body' },
      )
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResponse: ChatResponse | null = null
    let doneReceived = false

    const flushBlocks = () => {
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      return blocks
    }

    const handleBlock = (block: string) => {
      const payloadText = block
        .split(/\r?\n/)
        .filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart())
        .join('\n')
      if (!payloadText) return

      let payload: any
      try {
        payload = JSON.parse(payloadText)
      } catch {
        return
      }

      const type = String(payload?.type ?? '')
      if (type === 'start') {
        callbacks?.onStart?.()
        return
      }
      if (type === 'status') {
        callbacks?.onStatus?.({
          stage: String(payload?.stage ?? ''),
          detail: payload?.detail != null ? String(payload.detail) : null,
        })
        return
      }
      if (type === 'delta') {
        callbacks?.onDelta?.(String(payload?.delta ?? ''))
        return
      }
      if (type === 'final' && payload?.response) {
        finalResponse = payload.response as ChatResponse
        return
      }
      if (type === 'done') {
        doneReceived = true
        return
      }
      if (type === 'error') {
        const statusCode = Number(payload?.status_code ?? 500)
        const detail = String(payload?.detail ?? 'Erro no streaming de chat.')
        callbacks?.onError?.(detail)
        throw new ChatStreamError(
          detail,
          {
            statusCode,
            recoverable: isRecoverableStatus(statusCode),
            reason: 'server_error_event',
          },
        )
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      for (const block of flushBlocks()) {
        handleBlock(block)
      }
    }

    buffer += decoder.decode()
    for (const block of flushBlocks()) {
      handleBlock(block)
    }
    if (buffer.trim()) {
      handleBlock(buffer)
    }

    if (!finalResponse) {
      const reason = doneReceived ? 'done_without_final' : 'abrupt_close'
      throw new ChatStreamError(
        doneReceived
          ? 'Stream finalizado sem payload final.'
          : 'Stream encerrado sem resposta final.',
        { recoverable: true, reason },
      )
    }
    return finalResponse
  },

  ingestPath: (path: string, chunk_size = 0, chunk_overlap = 0): Promise<IngestResponse> =>
    api.post('/api/ingest', { path, chunk_size, chunk_overlap }, { timeout: INGEST_TIMEOUT_MS }).then(r => r.data),

  ingestUpload: (files: File[], chunk_size = 0, chunk_overlap = 0): Promise<IngestResponse> => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    form.append('chunk_size', String(chunk_size))
    form.append('chunk_overlap', String(chunk_overlap))
    return api.post('/api/ingest/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: INGEST_TIMEOUT_MS,
    }).then(r => r.data)
  },

  summarize: (
    doc: string,
    save = true,
    summary_mode: 'brief' | 'deep' = 'brief',
    template_id?: string,
  ): Promise<SummarizeResponse> =>
    api.post('/api/summarize', { doc, save, summary_mode, template_id }).then(r => r.data),

  summarizeAsync: (
    doc: string,
    save = true,
    summary_mode: 'brief' | 'deep' = 'brief',
    template_id?: string,
  ): Promise<JobCreateResponse> =>
    api.post('/api/summarize/async', { doc, save, summary_mode, template_id }).then(r => r.data),

  compare: (doc1: string, doc2: string, save = false): Promise<CompareResponse> =>
    api.post('/api/compare', { doc1, doc2, save }).then(r => r.data),

  listArtifactTemplates: (
    summary_mode?: 'brief' | 'deep' | string,
    artifact_type?: string,
  ): Promise<ArtifactTemplate[]> =>
    api.get('/api/artifact/templates', { params: { summary_mode, artifact_type } }).then(r => r.data),

  listArtifactFilterOptions: (): Promise<ArtifactFilterOptions> =>
    api.get('/api/artifacts/filters').then(r => r.data),

  createArtifact: (
    type: string,
    topic: string,
    output?: string,
    doc_names?: string[],
    template_id?: string,
  ): Promise<ArtifactResponse> =>
    api.post('/api/artifact', { type, topic, output, doc_names, template_id }).then(r => r.data),

  createArtifactAsync: (
    type: string,
    topic: string,
    output?: string,
    doc_names?: string[],
    template_id?: string,
  ): Promise<JobCreateResponse> =>
    api.post('/api/artifact/async', { type, topic, output, doc_names, template_id }).then(r => r.data),

  createArtifactFromChat: (payload: ChatArtifactCreatePayload): Promise<ChatArtifactResponse> =>
    api.post('/api/artifact/from-chat', payload).then(r => r.data),

  listArtifacts: (query?: ArtifactListQuery): Promise<ArtifactItem[]> =>
    api.get('/api/artifacts', { params: query }).then(r => r.data),

  getArtifactTextById: (artifactId: number): Promise<string> =>
    api
      .get(`/api/artifacts/id/${artifactId}`, { responseType: 'text' })
      .then(r => (typeof r.data === 'string' ? r.data : String(r.data))),

  getArtifactBlobById: (artifactId: number): Promise<Blob> =>
    api
      .get(`/api/artifacts/id/${artifactId}`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  getArtifactPdfBlobById: (artifactId: number): Promise<Blob> =>
    api
      .get(`/api/artifacts/id/${artifactId}/pdf`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  deleteArtifactById: (artifactId: number): Promise<void> =>
    api.delete(`/api/artifacts/id/${artifactId}`).then(() => undefined),

  getArtifactText: (filename: string): Promise<string> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}`, { responseType: 'text' })
      .then(r => (typeof r.data === 'string' ? r.data : String(r.data))),

  getArtifactBlob: (filename: string): Promise<Blob> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  getArtifactPdfBlob: (filename: string): Promise<Blob> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}/pdf`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  downloadArtifactUrl: (filename: string): string =>
    `${BASE_URL}/api/artifacts/${encodeURIComponent(filename)}`,

  downloadArtifactPdfUrl: (filename: string): string =>
    `${BASE_URL}/api/artifacts/${encodeURIComponent(filename)}/pdf`,

  deleteArtifact: (filename: string): Promise<void> =>
    api.delete(`/api/artifacts/${encodeURIComponent(filename)}`).then(() => undefined),

  getJobStatus: (jobId: string): Promise<JobStatusResponse> =>
    api.get(`/api/jobs/${encodeURIComponent(jobId)}`).then(r => r.data),

  listReminders: (start_from?: string, end_to?: string): Promise<ReminderItem[]> =>
    api.get('/api/calendar/reminders', { params: { start_from, end_to } }).then(r => r.data),

  createReminder: (payload: {
    title: string
    starts_at: string
    ends_at?: string | null
    note?: string | null
    all_day?: boolean
  }): Promise<ReminderItem> => api.post('/api/calendar/reminders', payload).then(r => r.data),

  updateReminder: (id: number, payload: {
    title: string
    starts_at: string
    ends_at?: string | null
    note?: string | null
    all_day?: boolean
  }): Promise<ReminderItem> => api.put(`/api/calendar/reminders/${id}`, payload).then(r => r.data),

  deleteReminder: (id: number): Promise<{ status: string }> =>
    api.delete(`/api/calendar/reminders/${id}`).then(r => r.data),

  listSchedules: (active_only = false): Promise<ScheduleItem[]> =>
    api.get('/api/calendar/schedules', { params: { active_only } }).then(r => r.data),

  createSchedule: (payload: {
    title: string
    day_of_week: number
    start_time: string
    end_time: string
    note?: string | null
    active?: boolean
  }): Promise<ScheduleItem> => api.post('/api/calendar/schedules', payload).then(r => r.data),

  updateSchedule: (id: number, payload: {
    title: string
    day_of_week: number
    start_time: string
    end_time: string
    note?: string | null
    active?: boolean
  }): Promise<ScheduleItem> => api.put(`/api/calendar/schedules/${id}`, payload).then(r => r.data),

  deleteSchedule: (id: number): Promise<{ status: string }> =>
    api.delete(`/api/calendar/schedules/${id}`).then(r => r.data),

  getCalendarOverview: (date?: string): Promise<CalendarOverview> =>
    api.get('/api/calendar/overview', { params: { date } }).then(r => r.data),

  // ── Notes ──────────────────────────────────────────────────────────────────

  listNotes: (): Promise<NoteItem[]> =>
    api.get('/api/notes').then(r => r.data),

  createNote: (title: string, content: string, pinned = false): Promise<NoteItem> =>
    api.post('/api/notes', { title, content, pinned }).then(r => r.data),

  updateNote: (id: number, title: string, content: string, pinned: boolean): Promise<NoteItem> =>
    api.put(`/api/notes/${id}`, { title, content, pinned }).then(r => r.data),

  deleteNote: (id: number): Promise<void> =>
    api.delete(`/api/notes/${id}`).then(() => undefined),

  // ── Tasks ──────────────────────────────────────────────────────────────────

  listTasks: (status?: string): Promise<TaskItem[]> =>
    api.get('/api/tasks', { params: { status } }).then(r => r.data),

  createTask: (
    title: string,
    note?: string,
    priority = 'normal',
    due_date?: string,
  ): Promise<TaskItem> =>
    api.post('/api/tasks', { title, note, priority, due_date }).then(r => r.data),

  updateTask: (
    id: number,
    title: string,
    note?: string,
    status = 'pending',
    priority = 'normal',
    due_date?: string,
  ): Promise<TaskItem> =>
    api.put(`/api/tasks/${id}`, { title, note, status, priority, due_date }).then(r => r.data),

  deleteTask: (id: number): Promise<void> =>
    api.delete(`/api/tasks/${id}`).then(() => undefined),

  listTaskChecklist: (taskId: number): Promise<TaskChecklistItem[]> =>
    api.get(`/api/tasks/${taskId}/checklist`).then(r => r.data),

  createChecklistItem: (taskId: number, text: string): Promise<TaskChecklistItem> =>
    api.post(`/api/tasks/${taskId}/checklist`, { text }).then(r => r.data),

  updateChecklistItem: (taskId: number, itemId: number, updates: { text?: string; done?: boolean }): Promise<TaskChecklistItem> =>
    api.put(`/api/tasks/${taskId}/checklist/${itemId}`, updates).then(r => r.data),

  deleteChecklistItem: (taskId: number, itemId: number): Promise<void> =>
    api.delete(`/api/tasks/${taskId}/checklist/${itemId}`).then(() => undefined),

  listTaskActivities: (taskId: number): Promise<TaskActivityLog[]> =>
    api.get(`/api/tasks/${taskId}/activities`).then(r => r.data),

  createTaskActivity: (taskId: number, text: string): Promise<TaskActivityLog> =>
    api.post(`/api/tasks/${taskId}/activities`, { text }).then(r => r.data),

  deleteTaskActivity: (taskId: number, logId: number): Promise<void> =>
    api.delete(`/api/tasks/${taskId}/activities/${logId}`).then(() => undefined),

  // ── Briefing ───────────────────────────────────────────────────────────────

  getBriefing: (): Promise<BriefingResponse> =>
    api.get('/api/briefing').then(r => r.data),

  // ── Flashcards ──────────────────────────────────────────────────────────────

  listFlashcardDecks: (): Promise<FlashcardDeckListItem[]> =>
    api.get('/api/flashcards').then(r => r.data),

  getFlashcardDeck: (id: number): Promise<FlashcardDeck> =>
    api.get(`/api/flashcards/${id}`).then(r => r.data),

  generateFlashcards: (
    docName: string,
    numCards: number,
    contentFilter = '',
    difficultyMode = 'any',
    difficultyCustom: { facil: number; media: number; dificil: number } | null = null,
  ): Promise<FlashcardDeck> =>
    api.post('/api/flashcards/generate', {
      doc_name: docName,
      num_cards: numCards,
      content_filter: contentFilter,
      difficulty_mode: difficultyMode,
      difficulty_custom: difficultyCustom,
    }, { timeout: FLASHCARD_GENERATION_TIMEOUT_MS }).then(r => r.data),

  generateFlashcardsBatch: (
    options: {
      allDocs?: boolean
      docNames?: string[]
      numCards: number
      contentFilter?: string
      difficultyMode?: string
      difficultyCustom?: { facil: number; media: number; dificil: number } | null
    }
  ): Promise<FlashcardBatchResponse> =>
    api.post('/api/flashcards/generate-batch', {
      all_docs: options.allDocs ?? false,
      doc_names: options.docNames ?? [],
      num_cards: options.numCards,
      content_filter: options.contentFilter ?? '',
      difficulty_mode: options.difficultyMode ?? 'any',
      difficulty_custom: options.difficultyCustom ?? null,
    }, { timeout: FLASHCARD_GENERATION_TIMEOUT_MS }).then(r => r.data),

  reviewFlashcard: (cardId: number, ease: number): Promise<{ status: string }> =>
    api.post('/api/flashcards/review', { card_id: cardId, ease }).then(r => r.data),

  updateFlashcardDifficulty: (cardId: number, difficulty: string): Promise<{ status: string; difficulty: string }> =>
    api.put(`/api/flashcards/card/${cardId}/difficulty`, { difficulty }).then(r => r.data),

  evaluateFlashcard: (cardId: number, userAnswer: string): Promise<{ verdict: string; feedback: string; highlight: string }> =>
    api.post(`/api/flashcards/card/${cardId}/evaluate`, { user_answer: userAnswer }).then(r => r.data),

  deleteFlashcardDeck: (id: number): Promise<void> =>
    api.delete(`/api/flashcards/${id}`).then(() => undefined),

  // ── Study Plan ──────────────────────────────────────────────────────────────

  createStudyPlan: (topic: string, days: number, docNames: string[]): Promise<StudyPlanResponse> =>
    api.post('/api/studyplan', { topic, days, doc_names: docNames }).then(r => r.data),

  createStudyPlanFromDoc: (
    docName: string,
    hoursPerDay: number,
    deadlineDate: string,
    generateFlashcards = true,
    numCards = 15,
    preferredStartTime = '20:00',
  ): Promise<StudyPlanDocResponse> =>
    api.post('/api/pipeline/study-plan', {
      doc_name: docName,
      hours_per_day: hoursPerDay,
      deadline_date: deadlineDate,
      generate_flashcards: generateFlashcards,
      num_cards: numCards,
      preferred_start_time: preferredStartTime,
    }, { timeout: 180000 }).then(r => r.data),

  listStudyPlans: (): Promise<StudyPlanItem[]> =>
    api.get('/api/pipeline/study-plans').then(r => r.data),

  deleteStudyPlan: (id: number): Promise<void> =>
    api.delete(`/api/pipeline/study-plans/${id}`).then(() => undefined),

  // ── Pipeline ────────────────────────────────────────────────────────────────

  digestDocument: (
    docName: string,
    options?: { generateFlashcards?: boolean; extractTasks?: boolean; numCards?: number; maxTasks?: number; scheduleReviews?: boolean }
  ): Promise<{ summary: string; deck_id: number | null; tasks_created: number; task_titles: string[]; reviews_scheduled: number }> =>
    api.post('/api/pipeline/digest', {
      doc_name: docName,
      generate_flashcards: options?.generateFlashcards ?? true,
      extract_tasks: options?.extractTasks ?? true,
      num_cards: options?.numCards ?? 10,
      max_tasks: options?.maxTasks ?? 8,
      schedule_reviews: options?.scheduleReviews ?? false,
    }, { timeout: 120000 }).then(r => r.data),

  extractTasksFromDoc: (
    docName: string,
    maxTasks?: number
  ): Promise<{ tasks_created: number; titles: string[] }> =>
    api.post('/api/pipeline/extract-tasks', {
      doc_name: docName,
      max_tasks: maxTasks ?? 10,
    }, { timeout: 90000 }).then(r => r.data),

  // ── Ingest Clip & Photo ─────────────────────────────────────────────────────

  ingestClip: (text: string, title: string): Promise<IngestResponse> =>
    api.post('/api/ingest/clip', { text, title }, { timeout: INGEST_TIMEOUT_MS }).then(r => r.data),

  ingestPhoto: (file: File, title: string): Promise<IngestResponse> => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    return api.post('/api/ingest/photo', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: INGEST_TIMEOUT_MS,
    }).then(r => r.data)
  },

  // ── Daily Question ──────────────────────────────────────────────────────────

  getDailyQuestion: (): Promise<DailyQuestionResponse> =>
    api.get('/api/pipeline/daily-question').then(r => r.data),

  evaluateAnswer: (question: string, userAnswer: string, answerHint: string): Promise<EvaluateAnswerResponse> =>
    api.post('/api/pipeline/evaluate-answer', { question, user_answer: userAnswer, answer_hint: answerHint }, { timeout: 30000 }).then(r => r.data),

  // ── Gap Analysis ────────────────────────────────────────────────────────────

  runGapAnalysis: (docNames: string[] = []): Promise<GapAnalysisResponse> =>
    api.post('/api/pipeline/gap-analysis', { doc_names: docNames }, { timeout: 90000 }).then(r => r.data),

  listProactiveRecommendations: (): Promise<ProactiveRecommendationsResponse> =>
    api.get('/api/pipeline/recommendations').then(r => r.data),

  recordProactiveRecommendationAction: (
    payload: ProactiveRecommendationActionPayload,
  ): Promise<ProactiveRecommendationActionResponse> =>
    api.post('/api/pipeline/recommendations/actions', payload).then(r => r.data),

  // ── Reading Status ──────────────────────────────────────────────────────────

  trackPremiumAnalyticsEvent: (payload: PremiumAnalyticsTrackPayload): Promise<PremiumAnalyticsTrackResponse> =>
    api.post('/api/analytics/premium/events', payload).then(r => r.data),

  getPremiumFunnel: (windowDays = 30): Promise<PremiumFunnelResponse> =>
    api.get('/api/analytics/premium/funnel', { params: { window_days: windowDays } }).then(r => r.data),

  getPremiumFunnelCsv: (windowDays = 30): Promise<Blob> =>
    api
      .get('/api/analytics/premium/funnel/export.csv', {
        params: { window_days: windowDays },
        responseType: 'blob',
      })
      .then(r => r.data as Blob),

  getPremiumRecommendationAnalytics: (windowDays = 30): Promise<PremiumRecommendationAnalyticsResponse> =>
    api.get('/api/analytics/premium/recommendations', { params: { window_days: windowDays } }).then(r => r.data),

  getPremiumRecommendationAnalyticsCsv: (windowDays = 30): Promise<Blob> =>
    api
      .get('/api/analytics/premium/recommendations/export.csv', {
        params: { window_days: windowDays },
        responseType: 'blob',
      })
      .then(r => r.data as Blob),

  getReadingStatus: (): Promise<Record<string, ReadingStatus>> =>
    api.get('/api/docs/reading-status').then(r => r.data),

  updateReadingStatus: (docId: string, status: ReadingStatus): Promise<{ doc_id: string; status: ReadingStatus }> =>
    api.patch(`/api/docs/${encodeURIComponent(docId)}/reading-status`, { status }).then(r => r.data),
}
