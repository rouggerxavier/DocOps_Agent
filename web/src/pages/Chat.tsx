import { useState, useRef, useEffect, useId } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import {
  Send, Bot, User, FileText, ChevronRight, ChevronDown, Loader2, X,
  Plus, Clock, CalendarCheck, Trash2,
  Sparkles, Search, Pause, ThumbsDown, ThumbsUp,
  MoreHorizontal, Paperclip, Menu,
} from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  apiClient,
  ChatStreamError,
  extractLockedFeatureDetail,
  type ChatResponse,
  type ChatQualitySignal,
  type SourceItem,
  type DocItem,
  type FlashcardDeck,
  type ProactiveRecommendationActionPayload,
  type ProactiveRecommendationItem,
  type ProactiveRecommendationsResponse,
  type UserPreferences,
} from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { trackPremiumFeatureActivation, trackPremiumTouchpointViewed, trackUpgradeCompleted, trackUpgradeInitiated } from '@/features/premiumAnalytics'
import { cn } from '@/lib/utils'
import { SectionIntro } from '@/onboarding/SectionIntro'
import { useStepAutoComplete } from '@/onboarding/useStepAutoComplete'

interface Message {
  role: 'user' | 'assistant'
  content: string
  prompt_hint?: string | null
  sources?: SourceItem[]
  intent?: string
  calendar_action?: Record<string, any> | null
  quality_signal?: ChatQualitySignal | null
  action_metadata?: ChatActionMetadata | null
  needs_confirmation?: boolean
  confirmation_text?: string | null
  suggested_reply?: string | null
  streaming?: boolean
  stream_stage?: StreamStage | null
  stream_status_text?: string | null
  stream_interrupted?: boolean
  active_context_snapshot?: ChatActiveContext | null
}

type StreamStage = 'analyzing' | 'retrieving' | 'drafting' | 'finalizing'

interface ChatActiveContext {
  active_doc_ids: string[]
  active_doc_names: string[]
  active_deck_id?: number | null
  active_deck_title?: string | null
  active_task_id?: number | null
  active_task_title?: string | null
  active_note_id?: number | null
  active_note_title?: string | null
  active_intent?: string | null
  last_action?: string | null
  last_user_command?: string | null
  last_card_count?: number | null
  last_difficulty_mix?: FlashcardDifficultyMix | null
}

interface ChatSession {
  id: string
  title: string
  messages: Message[]
  activeContext: ChatActiveContext
  createdAt: Date
}

const STORAGE_KEY = 'docops_chat_sessions'
const EMPTY_MESSAGES: Message[] = []

type FlashcardGenerationMode = 'any' | 'only_facil' | 'only_media' | 'only_dificil' | 'custom'

interface FlashcardDifficultyMix {
  facil: number
  media: number
  dificil: number
}

interface ChatActionMetadata {
  kind: string
  title?: string | null
  summary?: string | null
  status?: 'preview' | 'needs_confirmation' | 'executing' | 'executed' | 'failed'
  scope?: string | null
  doc_names?: string[]
  doc_count?: number | null
  card_count?: number | null
  difficulty?: FlashcardDifficultyMix | null
  next_steps?: string[] | null
  links?: Array<{ label: string; href: string }>
  error?: string | null
}

interface FlashcardCommandPlan {
  kind: 'flashcards'
  title: string
  summary: string
  confirmationText: string
  docs: DocItem[]
  scopeLabel: string
  numCards: number
  contentFilter: string
  difficultyMode: FlashcardGenerationMode
  difficultyCustom: FlashcardDifficultyMix | null
}

interface FlashcardBatchResult {
  doc: DocItem
  success: boolean
  deck?: FlashcardDeck
  error?: string
}

interface ChatRunPayload {
  message: string
  displayMessage: string
  sessionId: string
  docIds: string[]
  strictGrounding: boolean
  history: Array<{ role: 'user' | 'assistant'; content: string }>
  activeContext: ChatActiveContext
}

type ComposerPreferenceOverrides = {
  default_depth: UserPreferences['default_depth'] | null
  tone: UserPreferences['tone'] | null
  strictness_preference: UserPreferences['strictness_preference'] | null
}

const DEFAULT_USER_PREFERENCES: UserPreferences = {
  schema_version: 1,
  default_depth: 'brief',
  tone: 'neutral',
  strictness_preference: 'balanced',
  schedule_preference: 'flexible',
}

const DEPTH_LABELS: Record<UserPreferences['default_depth'], string> = {
  brief: 'Breve',
  balanced: 'Equilibrado',
  deep: 'Profundo',
}

const TONE_LABELS: Record<UserPreferences['tone'], string> = {
  neutral: 'Neutro',
  didactic: 'Didatico',
  objective: 'Objetivo',
  encouraging: 'Encorajador',
}

const STRICTNESS_LABELS: Record<UserPreferences['strictness_preference'], string> = {
  relaxed: 'Relaxado',
  balanced: 'Equilibrado',
  strict: 'Estrito',
}

const DEPTH_OPTIONS: Array<{ value: UserPreferences['default_depth'] }> = [
  { value: 'brief' },
  { value: 'balanced' },
  { value: 'deep' },
]

const TONE_OPTIONS: Array<{ value: UserPreferences['tone'] }> = [
  { value: 'neutral' },
  { value: 'didactic' },
  { value: 'objective' },
  { value: 'encouraging' },
]

const STRICTNESS_OPTIONS: Array<{ value: UserPreferences['strictness_preference'] }> = [
  { value: 'relaxed' },
  { value: 'balanced' },
  { value: 'strict' },
]

const SCHEDULE_LABELS: Record<UserPreferences['schedule_preference'], string> = {
  flexible: 'Flexivel',
  fixed: 'Fixo',
  intensive: 'Intensivo',
}

const RECOMMENDATION_ACTION_TOAST: Record<ProactiveRecommendationActionPayload['action'], string | null> = {
  dismiss: 'Recomendacao dispensada.',
  snooze: 'Recomendacao adiada por 24h.',
  mute_category: 'Categoria silenciada por 7 dias.',
  feedback_useful: 'Feedback recebido. Vamos reforcar sugestoes desse perfil.',
  feedback_not_useful: 'Feedback recebido. Vamos ajustar as proximas sugestoes.',
}

function emptyComposerOverrides(): ComposerPreferenceOverrides {
  return {
    default_depth: null,
    tone: null,
    strictness_preference: null,
  }
}

function resolveComposerPreferences(
  base: UserPreferences,
  overrides: ComposerPreferenceOverrides,
): UserPreferences {
  return {
    ...base,
    default_depth: overrides.default_depth ?? base.default_depth,
    tone: overrides.tone ?? base.tone,
    strictness_preference: overrides.strictness_preference ?? base.strictness_preference,
  }
}

function hasComposerOverrides(overrides: ComposerPreferenceOverrides): boolean {
  return Boolean(overrides.default_depth || overrides.tone || overrides.strictness_preference)
}

function buildPreferenceInstructionBlock(preferences: UserPreferences): string {
  return [
    '',
    '[Preferencias para esta resposta]',
    `- profundidade: ${DEPTH_LABELS[preferences.default_depth]}`,
    `- tom: ${TONE_LABELS[preferences.tone]}`,
    `- rigor: ${STRICTNESS_LABELS[preferences.strictness_preference]}`,
    '- aplique essas preferencias nesta resposta sem mencionar esse bloco.',
  ].join('\n')
}

const WELCOME_MESSAGE: Message = {
  role: 'assistant',
  content: `Olá! Sou o **DocOps Agent** — seu assistente de estudos com IA. Aqui está o que posso fazer por você:

**📚 Flashcards** — *"Crie 10 flashcards sobre [documento]"*
Selecione um documento indexado e eu gero cartões de revisão prontos para estudar.

**🗺️ Plano de Estudos** — *"Monte um plano de estudos para [tema]"*
Crio um cronograma personalizado com base nos seus documentos e metas.

**✨ Smart Digest** — *"Faça um resumo de [documento]"*
Resumo inteligente do conteúdo indexado, destacando os pontos mais importantes.

**📅 Rotina** — *"Crie uma rotina de estudos para esta semana"*
Organizo sua agenda de estudos no calendário integrado.

**📝 Notas** — *"Crie uma nota sobre [tema]"*
Salvo anotações diretamente nas suas notas.

**✅ Tarefas** — *"Adicione a tarefa: revisar capítulo 3"*
Criação rápida de tarefas no seu quadro Kanban.

**💬 Perguntas livres** — Tire dúvidas sobre qualquer conteúdo indexado.

---
Para começar, **indexe um documento** em *Inserção* e depois me diga o que quer criar!`,
}

function ensureWelcome(session: ChatSession): ChatSession {
  if (session.messages.length === 0 || session.messages[0].role !== 'assistant') {
    return { ...session, messages: [WELCOME_MESSAGE, ...session.messages] }
  }
  return session
}

function emptyActiveContext(): ChatActiveContext {
  return {
    active_doc_ids: [],
    active_doc_names: [],
    active_deck_id: null,
    active_deck_title: null,
    active_task_id: null,
    active_task_title: null,
    active_note_id: null,
    active_note_title: null,
    active_intent: null,
    last_action: null,
    last_user_command: null,
    last_card_count: null,
    last_difficulty_mix: null,
  }
}

function normalizeActiveContext(value: unknown): ChatActiveContext {
  const raw = (value && typeof value === 'object') ? (value as Record<string, unknown>) : {}
  const normalizeList = (key: string) => {
    const items = raw[key]
    if (!Array.isArray(items)) return []
    return Array.from(new Set(items.map(item => String(item ?? '').trim()).filter(Boolean))).slice(0, 10)
  }
  const normalizeNullableText = (key: string) => {
    const item = raw[key]
    const text = typeof item === 'string' ? item.trim() : ''
    return text || null
  }
  const normalizeNullableNumber = (key: string) => {
    const item = raw[key]
    if (typeof item === 'number' && Number.isFinite(item)) return item
    if (typeof item === 'string' && item.trim()) {
      const parsed = Number(item)
      return Number.isFinite(parsed) ? parsed : null
    }
    return null
  }

  const mix = raw.last_difficulty_mix
  let normalizedMix: FlashcardDifficultyMix | null = null
  if (mix && typeof mix === 'object') {
    const safeMix = mix as Record<string, unknown>
    normalizedMix = {
      facil: Number(safeMix.facil ?? 0) || 0,
      media: Number(safeMix.media ?? 0) || 0,
      dificil: Number(safeMix.dificil ?? 0) || 0,
    }
  }

  return {
    active_doc_ids: normalizeList('active_doc_ids'),
    active_doc_names: normalizeList('active_doc_names'),
    active_deck_id: normalizeNullableNumber('active_deck_id'),
    active_deck_title: normalizeNullableText('active_deck_title'),
    active_task_id: normalizeNullableNumber('active_task_id'),
    active_task_title: normalizeNullableText('active_task_title'),
    active_note_id: normalizeNullableNumber('active_note_id'),
    active_note_title: normalizeNullableText('active_note_title'),
    active_intent: normalizeNullableText('active_intent'),
    last_action: normalizeNullableText('last_action'),
    last_user_command: normalizeNullableText('last_user_command'),
    last_card_count: normalizeNullableNumber('last_card_count'),
    last_difficulty_mix: normalizedMix,
  }
}

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatSession[]
    return parsed.map(s => ensureWelcome({
      ...s,
      createdAt: new Date(s.createdAt),
      activeContext: normalizeActiveContext((s as ChatSession).activeContext),
    }))
  } catch {
    return []
  }
}

function saveSessions(sessions: ChatSession[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  } catch {
    // localStorage can be unavailable or full; keeping chat usable matters more than persistence here.
  }
}

function newSession(): ChatSession {
  return {
    id: `session_${Date.now()}`,
    title: 'Nova conversa',
    messages: [WELCOME_MESSAGE],
    activeContext: emptyActiveContext(),
    createdAt: new Date(),
  }
}

function getSessionPreview(session: ChatSession): string {
  const last = [...session.messages].reverse().find(message => {
    if (!message.content?.trim()) return false
    if (message.streaming) return false
    return true
  })
  if (!last) return 'Conversa pronta para comecar.'

  const compact = last.content.replace(/\s+/g, ' ').trim()
  if (!compact) return 'Conversa pronta para comecar.'
  return compact.length > 84 ? `${compact.slice(0, 84)}...` : compact
}

function formatSessionAge(createdAt: Date): string {
  const created = createdAt instanceof Date ? createdAt.getTime() : Number(createdAt)
  if (!Number.isFinite(created)) return 'agora'

  const diffMs = Math.max(0, Date.now() - created)
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'agora'
  if (minutes < 60) return `${minutes}m`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`

  const days = Math.floor(hours / 24)
  if (days === 1) return 'ontem'
  return `${days}d`
}

function normalizeForMatch(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[_-]+/g, ' ')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

function shouldOfferChatArtifactCTA(message: Message): boolean {
  if (message.role !== 'assistant' || message.streaming || message.needs_confirmation) return false
  if (message.action_metadata || message.calendar_action) return false

  const content = normalizeForMatch(message.content || '')
  const prompt = normalizeForMatch(message.prompt_hint || '')
  const intent = normalizeForMatch(message.intent || '')

  const promptLooksDeepSummary = (
    /\b(resumo|resumir|sumario|sintese)\b/.test(prompt)
    && /\b(aprofundad|detalhad|profund|complet|secc?ao por secc?ao)\b/.test(prompt)
  )
  const contentLooksDeepSummary = (
    /\b(resumo aprofundado|analise detalhada|analise completa|secao por secao)\b/.test(content)
    || (message.content.includes('##') && content.length >= 420)
  )

  if (intent === 'summary') {
    return promptLooksDeepSummary || contentLooksDeepSummary || content.length >= 500
  }
  return promptLooksDeepSummary && content.length >= 420
}

function formatDifficultyMix(mix: FlashcardDifficultyMix) {
  return `${mix.facil} faceis, ${mix.media} medias e ${mix.dificil} dificeis`
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
  if (typeof message === 'string' && message.trim()) return message
  return fallback
}

function buildRecommendationPrompt(
  recommendation: ProactiveRecommendationItem,
  activeContext: ChatActiveContext,
): string {
  const docHint = activeContext.active_doc_names.slice(0, 3)
  const docSegment = docHint.length > 0
    ? ` Use como base principal: ${docHint.join(', ')}.`
    : ''

  const categoryPromptMap: Record<ProactiveRecommendationItem['category'], string> = {
    consistency: 'Me ajude a executar esta recomendacao com passos curtos e prioridades claras.',
    schedule: 'Monte um plano pratico para hoje com foco e blocos de tempo.',
    coverage: 'Identifique os gaps e proponha as proximas acoes de cobertura.',
    quality: 'Eleve a qualidade do meu estudo com uma estrategia objetiva de revisao.',
  }

  const categoryPrompt = categoryPromptMap[recommendation.category] ?? 'Me ajude a executar esta recomendacao.'
  return `${recommendation.title}. ${recommendation.description} ${categoryPrompt}${docSegment}`.trim()
}

function parseFlashcardCommandPlan(prompt: string, docs: DocItem[], selectedDocs: DocItem[]): FlashcardCommandPlan | null {
  const normalized = normalizeForMatch(prompt)
  const flashcardKeyword = /\bflashcards?\b|\bcards?\b|\brevisao\b|\bquiz\b/.test(normalized)
  const commandVerb = /\b(crie|criar|gere|gerar|fa[çc]a|fazer|monte|produza|quero|gostaria|preciso)\b/.test(normalized)

  if (!flashcardKeyword || !commandVerb) return null

  const totalMatch = prompt.match(/(\d+)\s*(?:flashcards?|cards?|cart[õo]es?)/i)
  const facilMatch = prompt.match(/(\d+)\s*(?:f[aá]ceis?|facil(?:es)?)/i)
  const mediaMatch = prompt.match(/(\d+)\s*(?:m[eé]dias?|medias?)/i)
  const dificilMatch = prompt.match(/(\d+)\s*(?:d[ií]f[ií]ceis?|dificeis?)/i)

  const difficultyCustom = facilMatch || mediaMatch || dificilMatch
    ? {
        facil: Number(facilMatch?.[1] ?? 0),
        media: Number(mediaMatch?.[1] ?? 0),
        dificil: Number(dificilMatch?.[1] ?? 0),
      }
    : null

  const customTotal = difficultyCustom
    ? difficultyCustom.facil + difficultyCustom.media + difficultyCustom.dificil
    : 0

  const totalCards = totalMatch
    ? Number(totalMatch[1])
    : customTotal > 0
      ? customTotal
      : 10
  const difficultyMode: FlashcardGenerationMode = difficultyCustom
    ? (difficultyCustom.media === 0 && difficultyCustom.dificil === 0 && difficultyCustom.facil > 0
      ? 'only_facil'
      : difficultyCustom.facil === 0 && difficultyCustom.dificil === 0 && difficultyCustom.media > 0
        ? 'only_media'
        : difficultyCustom.facil === 0 && difficultyCustom.media === 0 && difficultyCustom.dificil > 0
          ? 'only_dificil'
          : 'custom')
    : 'any'

  const wantsAllDocs = [
    /cada documento/,
    /todos? os documentos/,
    /todos? esses documentos/,
    /todos? estes documentos/,
    /na aba documentos/,
    /documentos indexados? na conversa/,
    /documentos que tenho/,
    /todos? os docs/,
  ].some(pattern => pattern.test(normalized))

  const matchedDocs = docs.filter(doc => {
    const normalizedName = normalizeForMatch(doc.file_name.replace(/\.[^.]+$/, ''))
    return normalizedName.length > 0 && (normalized.includes(normalizedName) || normalizedName.includes(normalized))
  })

  let targetDocs: DocItem[] = []
  let scopeLabel = ''

  if (wantsAllDocs) {
    targetDocs = docs
    scopeLabel = `${docs.length} documento${docs.length !== 1 ? 's' : ''} indexado${docs.length !== 1 ? 's' : ''}`
  } else if (matchedDocs.length > 0) {
    targetDocs = matchedDocs
    scopeLabel = matchedDocs.length === 1
      ? `documento "${matchedDocs[0].file_name}"`
      : `${matchedDocs.length} documentos encontrados pelo nome`
  } else if (selectedDocs.length > 0) {
    targetDocs = selectedDocs
    scopeLabel = selectedDocs.length === 1
      ? `documento selecionado "${selectedDocs[0].file_name}"`
      : `${selectedDocs.length} documentos selecionados`
  } else if (docs.length === 1) {
    targetDocs = docs
    scopeLabel = `documento "${docs[0].file_name}"`
  }

  if (targetDocs.length === 0) {
    return {
      kind: 'flashcards',
      title: 'Comando de flashcards detectado',
      summary: 'Encontrei um pedido de flashcards, mas preciso de um documento ou de uma selecao de documentos para executar com seguranca.',
      confirmationText: 'Selecione um documento na area de filtros ou diga "todos os documentos" para eu executar em lote.',
      docs: [],
      scopeLabel: 'escopo indefinido',
      numCards: totalCards,
      contentFilter: '',
      difficultyMode,
      difficultyCustom,
    }
  }

  const difficultyLabel = difficultyCustom
    ? `Distribuicao pedida: ${formatDifficultyMix(difficultyCustom)}`
    : difficultyMode === 'only_facil'
      ? 'Somente cards faceis'
      : difficultyMode === 'only_media'
        ? 'Somente cards medios'
        : difficultyMode === 'only_dificil'
          ? 'Somente cards dificeis'
          : 'Dificuldade mista'

  const summary = targetDocs.length === 1
    ? `Vou gerar ${totalCards} flashcards para ${scopeLabel}.`
    : `Vou gerar ${totalCards} flashcards para cada um dos ${targetDocs.length} documentos selecionados.`

  return {
    kind: 'flashcards',
    title: 'Comando de flashcards detectado',
    summary,
    confirmationText: `${difficultyLabel}. ${targetDocs.length > 1 ? 'Isso vai criar um deck por documento.' : 'Isso vai criar um deck para um unico documento.'}`,
    docs: targetDocs,
    scopeLabel,
    numCards: totalCards,
    contentFilter: '',
    difficultyMode,
    difficultyCustom,
  }
}

const STREAM_STAGE_LABELS: Record<StreamStage, string> = {
  analyzing: 'Analisando',
  retrieving: 'Buscando evidencias',
  drafting: 'Redigindo resposta',
  finalizing: 'Finalizando',
}

const STREAM_STAGE_DETAIL_DEFAULT: Record<StreamStage, string> = {
  analyzing: 'Entendendo sua solicitacao.',
  retrieving: 'Consultando os documentos ativos.',
  drafting: 'Montando a resposta em tempo real.',
  finalizing: 'Consolidando a versao final.',
}

const STREAM_STAGE_ORDER: Record<StreamStage, number> = {
  analyzing: 1,
  retrieving: 2,
  drafting: 3,
  finalizing: 4,
}

function normalizeStreamStage(raw: string | null | undefined): StreamStage | null {
  const value = (raw ?? '').trim().toLowerCase()
  if (value === 'analyzing' || value === 'retrieving' || value === 'drafting' || value === 'finalizing') {
    return value
  }
  if (value === 'processing') {
    return 'retrieving'
  }
  return null
}

// ── Typing indicator ──────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex items-center rounded-xl bg-[color:var(--ui-surface-container-low)] px-4 py-3">
        <span className="flex gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--ui-text-meta)] animate-bounce [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--ui-text-meta)] animate-bounce [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--ui-text-meta)] animate-bounce [animation-delay:300ms]" />
        </span>
      </div>
    </div>
  )
}

// ── Source panel ──────────────────────────────────────────────────────────

function SourcePanel({
  sources, selected, onSelect,
}: {
  sources: SourceItem[]
  selected: SourceItem | null
  onSelect: (s: SourceItem) => void
}) {
  if (sources.length === 0) return null

  return (
    <div className="space-y-2">
      {sources.map(src => (
        <button
          key={src.chunk_id || src.fonte_n}
          onClick={() => onSelect(src)}
          className={cn(
            'w-full rounded-xl border p-3 text-left transition-colors',
            selected?.fonte_n === src.fonte_n
              ? 'border-[color:var(--ui-accent)]/35 bg-[color:var(--ui-accent-soft)]'
              : 'border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-container-lowest)] hover:border-[color:var(--ui-border-strong)]'
          )}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold text-[color:var(--ui-accent)]">[Fonte {src.fonte_n}]</span>
            <span className="text-xs text-[color:var(--ui-text-meta)] truncate">{src.file_name}</span>
          </div>
          {src.page !== 'N/A' && (
            <span className="text-xs text-[color:var(--ui-text-meta)]">p. {src.page}</span>
          )}
          {selected?.fonte_n === src.fonte_n && (
            <p className="mt-2 line-clamp-4 text-xs text-[color:var(--ui-text-dim)]">{src.snippet}</p>
          )}
        </button>
      ))}
    </div>
  )
}

// ── Calendar action badge ─────────────────────────────────────────────────

function CalendarActionBadge({ action }: { action: Record<string, any> }) {
  if (action.type === 'reminder_created') {
    return (
      <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-blue-600/30 bg-blue-600/10 px-2.5 py-1.5 text-xs text-blue-300">
        <CalendarCheck className="h-3.5 w-3.5" />
        Lembrete adicionado ao calendário
      </div>
    )
  }
  if (action.type === 'schedule_created') {
    const count = action.blocks?.length ?? 0
    return (
      <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-emerald-600/30 bg-emerald-600/10 px-2.5 py-1.5 text-xs text-emerald-300">
        <CalendarCheck className="h-3.5 w-3.5" />
        {count} bloco{count !== 1 ? 's' : ''} adicionado{count !== 1 ? 's' : ''} ao cronograma
      </div>
    )
  }
  return null
}

function ActionSummaryCard({
  action,
  onConfirm,
  onCancel,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
}: {
  action: ChatActionMetadata
  onConfirm?: () => void
  onCancel?: () => void
  confirmLabel?: string
  cancelLabel?: string
}) {
  const statusLabel: Record<NonNullable<ChatActionMetadata['status']>, string> = {
    preview: 'Previa',
    needs_confirmation: 'Confirmacao',
    executing: 'Executando',
    executed: 'Executado',
    failed: 'Falhou',
  }

  const toneClass =
    action.status === 'executed'
      ? 'border-emerald-800/50 bg-emerald-950/20 text-emerald-200'
      : action.status === 'failed'
        ? 'border-red-800/50 bg-red-950/20 text-red-200'
        : 'border-[color:var(--ui-accent)]/35 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-text)]'

  return (
    <div className={cn('rounded-2xl border px-4 py-3 text-xs', toneClass)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">
            {action.title ?? 'Comando de flashcards'}
          </p>
          <p className="mt-1 leading-5 text-zinc-200/90">{action.summary ?? 'Aguarde a confirmacao.'}</p>
        </div>
        {action.status && statusLabel[action.status] && (
          <span className="shrink-0 rounded-full border border-current/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide">
            {statusLabel[action.status]}
          </span>
        )}
      </div>

      <div className="mt-3 space-y-2 text-[11px] text-zinc-300/90">
        {action.scope && (
          <p><span className="font-semibold text-zinc-200">Escopo:</span> {action.scope}</p>
        )}
        {typeof action.doc_count === 'number' && (
          <p><span className="font-semibold text-zinc-200">Documentos:</span> {action.doc_count}</p>
        )}
        {typeof action.card_count === 'number' && (
          <p><span className="font-semibold text-zinc-200">Cards por documento:</span> {action.card_count}</p>
        )}
        {action.difficulty && (
          <p><span className="font-semibold text-zinc-200">Dificuldade:</span> {formatDifficultyMix(action.difficulty)}</p>
        )}
        {action.doc_names && action.doc_names.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {action.doc_names.map(name => (
              <span key={name} className="rounded-full border border-current/20 px-2 py-0.5 text-[10px]">
                {name}
              </span>
            ))}
          </div>
        )}
        {action.next_steps && action.next_steps.length > 0 && (
          <ul className="space-y-1 text-zinc-300/90">
            {action.next_steps.map(step => (
              <li key={step}>• {step}</li>
            ))}
          </ul>
        )}
        {action.links && action.links.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {action.links.map(link => (
              <a
                key={link.href}
                href={link.href}
                className="rounded-full border border-current/20 px-2.5 py-1 text-[11px] font-medium hover:bg-white/5"
              >
                {link.label}
              </a>
            ))}
          </div>
        )}
      </div>

      {(onConfirm || onCancel) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {onCancel && (
            <button
              onClick={onCancel}
              className="rounded-full border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-[11px] font-medium text-zinc-300 hover:border-zinc-500"
            >
              {cancelLabel}
            </button>
          )}
          {onConfirm && (
            <button
              onClick={onConfirm}
              className="rounded-full border border-blue-700/60 bg-blue-600/15 px-3 py-1.5 text-[11px] font-medium text-blue-200 hover:bg-blue-600/25"
            >
              {confirmLabel}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Intent label map ──────────────────────────────────────────────────────

const INTENT_LABELS: Record<string, string> = {
  cascade_study_plan:       '📚 Plano de estudos criado',
  cascade_task_deadline:    '✅ Tarefa criada',
  cascade_create_reminder:  '🔔 Lembrete criado',
  cascade_create_schedule:  '📅 Agenda criada',
  cascade_create_note:      '📝 Nota criada',
  cascade_create_summary:   '📄 Resumo gerado',
  schedule_fc_reviews:      '🔁 Revisões agendadas',
  flashcards_batch:         '🗂️ Flashcards em lote',
  action_confirmation:      '🟡 Ação em confirmação',
}

// ── Message bubble ────────────────────────────────────────────────────────

const QUALITY_TONE_CLASS: Record<'high' | 'medium' | 'low', string> = {
  high: 'border-emerald-700/40 bg-emerald-600/10 text-emerald-100',
  medium: 'border-amber-700/40 bg-amber-600/10 text-amber-100',
  low: 'border-red-700/40 bg-red-600/10 text-red-100',
}

const QUALITY_BADGE_CLASS: Record<'high' | 'medium' | 'low', string> = {
  high: 'border-emerald-500/40 bg-emerald-400/10 text-emerald-200',
  medium: 'border-amber-500/40 bg-amber-400/10 text-amber-200',
  low: 'border-red-500/40 bg-red-400/10 text-red-200',
}

type QualityComponentKey = 'support_rate' | 'source_breadth' | 'unsupported_claims' | 'retrieval_depth'

const QUALITY_COMPONENT_LABELS: Record<QualityComponentKey, string> = {
  support_rate: 'Suporte factual',
  source_breadth: 'Variedade de fontes',
  unsupported_claims: 'Afirmacoes suportadas',
  retrieval_depth: 'Profundidade da busca',
}

const QUALITY_REASON_CODE_LABELS: Record<string, string> = {
  support_rate_strong: 'Alta taxa de suporte nas evidencias.',
  support_rate_moderate: 'Taxa de suporte moderada.',
  support_rate_weak: 'Taxa de suporte baixa.',
  support_rate_missing: 'Taxa de suporte indisponivel para esta resposta.',
  source_breadth_none: 'Nenhuma fonte citada no texto.',
  source_breadth_single: 'A resposta depende de uma unica fonte.',
  source_breadth_multi: 'A resposta usa multiplas fontes.',
  unsupported_claims_none: 'Nao foram detectadas afirmacoes sem suporte.',
  unsupported_claims_present: 'Foram detectadas afirmacoes com suporte parcial.',
  retrieval_depth_none: 'Nenhum trecho foi recuperado no contexto.',
  retrieval_depth_shallow: 'Poucos trechos foram recuperados para sustentar a resposta.',
  retrieval_depth_sufficient: 'Quantidade suficiente de trechos recuperados.',
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

function toPercent(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 0
  return Math.round(clamp01(value) * 100)
}

function parseLegacyReason(reason: string): string {
  const raw = String(reason || '').trim()
  if (!raw) return 'Sinal de confianca nao detalhado.'
  if (QUALITY_REASON_CODE_LABELS[raw]) return QUALITY_REASON_CODE_LABELS[raw]
  if (raw === 'no_inline_sources') return 'Nenhuma fonte citada no texto.'
  if (raw === 'single_source') return 'A resposta depende de uma unica fonte.'
  if (raw === 'multi_source') return 'A resposta usa multiplas fontes.'
  if (raw === 'no_retrieval') return 'Nenhum trecho foi recuperado no contexto.'

  if (raw.startsWith('support_rate=')) {
    const parsed = Number(raw.split('=')[1])
    if (Number.isFinite(parsed)) return `Taxa de suporte: ${toPercent(parsed)}%.`
  }
  if (raw.startsWith('unsupported_claims=')) {
    const count = Number(raw.split('=')[1])
    if (Number.isFinite(count)) {
      return count <= 0
        ? 'Nao foram detectadas afirmacoes sem suporte.'
        : `${Math.round(count)} afirmacao(oes) com suporte parcial.`
    }
  }
  if (raw.startsWith('retrieval_chunks=')) {
    const count = Number(raw.split('=')[1])
    if (Number.isFinite(count)) {
      return `${Math.round(count)} trecho(s) recuperado(s) na busca.`
    }
  }

  return raw.replace(/_/g, ' ')
}

function deriveReasonLabels(signal: ChatQualitySignal): string[] {
  const fromCodes = (signal.reason_codes ?? [])
    .map(code => QUALITY_REASON_CODE_LABELS[String(code)] ?? parseLegacyReason(String(code)))
    .filter(Boolean)
  if (fromCodes.length > 0) return Array.from(new Set(fromCodes))

  const fromReasons = (signal.reasons ?? [])
    .map(reason => parseLegacyReason(String(reason)))
    .filter(Boolean)
  if (fromReasons.length > 0) return Array.from(new Set(fromReasons))

  return ['Sem diagnostico detalhado para esta resposta.']
}

function deriveScoreComponents(signal: ChatQualitySignal): Array<{ key: QualityComponentKey; label: string; value: number }> {
  const unsupportedCount = Number(signal.unsupported_claim_count ?? 0)
  const fallbackUnsupported = unsupportedCount <= 0
    ? 1
    : unsupportedCount === 1
      ? 0.75
      : unsupportedCount === 2
        ? 0.5
        : 0.25
  const retrievedCount = Number(signal.retrieved_count ?? 0)
  const fallbackRetrieval = retrievedCount <= 0
    ? 0
    : retrievedCount <= 2
      ? (retrievedCount === 1 ? 0.45 : 0.7)
      : 1
  const sourceCount = Number(signal.source_count ?? 0)
  const fallbackSourceBreadth = sourceCount <= 0 ? 0 : (sourceCount === 1 ? 0.6 : 1)

  const raw: Partial<Record<QualityComponentKey, number>> = signal.score_components ?? {}
  const values: Record<QualityComponentKey, number> = {
    support_rate: clamp01(Number(raw.support_rate ?? signal.support_rate ?? signal.score ?? 0)),
    source_breadth: clamp01(Number(raw.source_breadth ?? fallbackSourceBreadth)),
    unsupported_claims: clamp01(Number(raw.unsupported_claims ?? fallbackUnsupported)),
    retrieval_depth: clamp01(Number(raw.retrieval_depth ?? fallbackRetrieval)),
  }

  return (Object.keys(QUALITY_COMPONENT_LABELS) as QualityComponentKey[]).map(key => ({
    key,
    label: QUALITY_COMPONENT_LABELS[key],
    value: values[key],
  }))
}

function QualitySignalCard({ signal }: { signal: ChatQualitySignal }) {
  const scorePct = toPercent(signal.score)
  const reasonLabels = deriveReasonLabels(signal)
  const components = deriveScoreComponents(signal)
  const explainId = useId()
  const [expanded, setExpanded] = useState(false)

  const sourceCount = Math.max(0, Number(signal.source_count ?? 0))
  const retrievedCount = Math.max(0, Number(signal.retrieved_count ?? 0))
  const unsupportedCount = Math.max(0, Number(signal.unsupported_claim_count ?? 0))
  const sourceSpreadPct = retrievedCount > 0
    ? Math.round(Math.min(1, sourceCount / retrievedCount) * 100)
    : (sourceCount > 0 ? 100 : 0)

  return (
    <div
      data-testid="chat-quality-signal"
      className={cn(
        'rounded-xl border px-3 py-3 text-[11px] leading-5',
        QUALITY_TONE_CLASS[signal.level],
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold">
            Confiabilidade: {signal.label} ({scorePct}%)
          </p>
          <p className="text-[11px] opacity-90">
            Score normalizado com sinais de suporte, fontes e recuperacao.
          </p>
        </div>
        <span className={cn(
          'shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
          QUALITY_BADGE_CLASS[signal.level],
        )}
        >
          {signal.level}
        </span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
        <div className="rounded-md border border-white/10 bg-black/15 px-2 py-1.5">
          <p className="text-zinc-300/90">Fontes citadas</p>
          <p className="font-semibold">{sourceCount}</p>
        </div>
        <div className="rounded-md border border-white/10 bg-black/15 px-2 py-1.5">
          <p className="text-zinc-300/90">Trechos recuperados</p>
          <p className="font-semibold">{retrievedCount}</p>
        </div>
        <div className="rounded-md border border-white/10 bg-black/15 px-2 py-1.5">
          <p className="text-zinc-300/90">Espalhamento de fontes</p>
          <p className="font-semibold">{sourceSpreadPct}%</p>
        </div>
        <div className="rounded-md border border-white/10 bg-black/15 px-2 py-1.5">
          <p className="text-zinc-300/90">Claims sem suporte</p>
          <p className="font-semibold">{unsupportedCount}</p>
        </div>
      </div>

      {signal.suggested_action && (
        <p className="mt-2 rounded-md border border-white/10 bg-black/20 px-2 py-1.5 text-[11px]">
          {signal.suggested_action}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-1.5">
        {reasonLabels.slice(0, 3).map(label => (
          <span
            key={label}
            className="rounded-full border border-white/15 bg-black/20 px-2 py-0.5 text-[10px]"
          >
            {label}
          </span>
        ))}
      </div>

      <button
        type="button"
        className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-blue-200 transition-colors hover:text-blue-100"
        aria-expanded={expanded}
        aria-controls={explainId}
        onClick={() => setExpanded(prev => !prev)}
      >
        Como esta resposta foi construida
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
      </button>

      {expanded && (
        <div id={explainId} className="mt-2 space-y-2 rounded-lg border border-white/10 bg-black/20 p-2.5">
          <p className="text-[10px] text-zinc-300/90">
            Diagnostico resumido do pipeline de evidencia desta resposta.
          </p>

          <div className="space-y-1.5">
            {components.map(item => {
              const pct = toPercent(item.value)
              return (
                <div key={item.key}>
                  <div className="mb-0.5 flex items-center justify-between gap-2">
                    <span className="text-[10px] text-zinc-200">{item.label}</span>
                    <span className="text-[10px] font-semibold text-zinc-100">{pct}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900/70">
                    <div
                      className="h-full rounded-full bg-blue-400/70"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          <div className="space-y-1 text-[10px] text-zinc-200/90">
            <p>1. Recuperamos {retrievedCount} trecho(s) relevantes para a pergunta.</p>
            <p>2. A resposta citou {sourceCount} fonte(s) no texto final.</p>
            <p>3. Detectamos {unsupportedCount} claim(s) com suporte parcial.</p>
          </div>
        </div>
      )}
    </div>
  )
}

function StreamStatusCard({
  stage,
  detail,
  interrupted,
}: {
  stage: StreamStage | null | undefined
  detail?: string | null
  interrupted?: boolean
}) {
  if (!stage && !interrupted && !detail) return null
  const label = stage ? STREAM_STAGE_LABELS[stage] : 'Transmissao interrompida'
  const safeDetail = detail?.trim() || (stage ? STREAM_STAGE_DETAIL_DEFAULT[stage] : 'Tente reenviar para continuar.')
  return (
    <div
      className={cn(
        'rounded-xl border px-3 py-2 text-[11px] leading-5',
        interrupted
          ? 'border-amber-500/35 bg-amber-500/10 text-amber-100'
          : 'border-[color:var(--ui-accent)]/35 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
      )}
    >
      <div className="flex items-center gap-2">
        {!interrupted && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        <span className="font-semibold">{label}</span>
      </div>
      <p className="mt-1 opacity-95">{safeDetail}</p>
    </div>
  )
}

function MessageBubble({
  message,
  onSourceClick,
  onCitationClick,
  canSaveAsArtifact,
  showArtifactUnlockCta,
  artifactEntitlementTier,
  savingAsArtifact,
  onSaveAsArtifact,
  onRefreshArtifactAccess,
  onUpgradeIntent,
}: {
  message: Message
  onSourceClick?: (sources: SourceItem[]) => void
  onCitationClick?: (source: SourceItem, allSources: SourceItem[]) => void
  canSaveAsArtifact?: boolean
  showArtifactUnlockCta?: boolean
  artifactEntitlementTier?: string
  savingAsArtifact?: boolean
  onSaveAsArtifact?: () => void
  onRefreshArtifactAccess?: () => void
  onUpgradeIntent?: () => void
}) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-md',
          isUser ? 'bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)]' : 'bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className={cn('max-w-[88%] space-y-2', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'select-text rounded-2xl px-4 py-3 text-sm transition-all duration-200',
            isUser
              ? 'rounded-tr-sm bg-[color:var(--ui-surface-container-high)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-surface-3)] selection:bg-sky-200 selection:text-zinc-950'
              : 'rounded-tl-sm bg-[color:var(--ui-surface-container-low)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-surface-2)] selection:bg-amber-200 selection:text-zinc-950'
          )}
          draggable={false}
          onDragStart={isUser ? e => e.preventDefault() : undefined}
          style={{
            userSelect: 'text',
            WebkitUserSelect: 'text',
            cursor: 'text',
          }}
        >
          {isUser ? (
            <div
              className="select-text whitespace-pre-wrap break-words leading-relaxed selection:bg-sky-200 selection:text-zinc-950"
              draggable={false}
              onDragStart={e => e.preventDefault()}
              style={{ userSelect: 'text', WebkitUserSelect: 'text' }}
            >
              {message.content}
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none select-text leading-relaxed selection:bg-amber-200 selection:text-zinc-950" style={{ userSelect: 'text', WebkitUserSelect: 'text' }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {message.streaming && (
                <span className="ml-1 inline-flex h-[1.05em] w-[2px] animate-pulse rounded-full bg-[color:var(--ui-accent)]/80 align-[-0.15em] shadow-[0_0_10px_rgba(147,205,252,0.45)]" />
              )}
            </div>
          )}
        </div>

        {!isUser && (message.streaming || message.stream_interrupted || message.stream_status_text) && (
          <StreamStatusCard
            stage={message.stream_stage}
            detail={message.stream_status_text}
            interrupted={message.stream_interrupted}
          />
        )}

        {!isUser && message.calendar_action && (
          <CalendarActionBadge action={message.calendar_action} />
        )}

        {!isUser && message.action_metadata && (
          <ActionSummaryCard action={message.action_metadata} />
        )}

        {!isUser && !message.action_metadata && (message.needs_confirmation || message.confirmation_text) && (
          <ActionSummaryCard
            action={{
              kind: 'action_confirmation',
              title: 'Confirmacao necessaria',
              summary: message.confirmation_text ?? 'Esta acao precisa de confirmacao.',
              status: 'needs_confirmation',
              links: [
                { label: 'Abrir Flashcards', href: '/flashcards' },
              ],
            }}
          />
        )}

        {!isUser && message.quality_signal && (
          <QualitySignalCard signal={message.quality_signal} />
        )}

        {!isUser && canSaveAsArtifact && (
          <div>
            <button
              type="button"
              onClick={onSaveAsArtifact}
              disabled={Boolean(savingAsArtifact)}
              className="rounded-full border border-emerald-600/45 bg-emerald-500/10 px-3 py-1.5 text-[11px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {savingAsArtifact ? 'Salvando artefato...' : 'Salvar como artefato'}
            </button>
          </div>
        )}

        {!isUser && showArtifactUnlockCta && (
          <div className="rounded-xl border border-amber-600/35 bg-amber-950/15 px-3 py-2">
            <p className="text-[11px] text-amber-100/90">
              Salvar como artefato exige plano premium ({artifactEntitlementTier ?? 'free'}).
            </p>
            <button
              type="button"
              onClick={onRefreshArtifactAccess}
              className="mt-1.5 rounded-md border border-amber-500/45 px-2 py-1 text-[11px] text-amber-100 transition-colors hover:bg-amber-500/10"
            >
              Ja fiz upgrade, atualizar acesso
            </button>
            <button
              type="button"
              onClick={onUpgradeIntent}
              className="ml-2 mt-1.5 rounded-md border border-amber-500/25 px-2 py-1 text-[11px] text-amber-100/90 transition-colors hover:bg-amber-500/10"
            >
              Ver recursos premium
            </button>
          </div>
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="space-y-2">
            <button
              onClick={() => onSourceClick?.(message.sources!)}
              className="flex items-center gap-1.5 text-xs text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-accent)]"
            >
              <FileText className="h-3 w-3" />
              {message.sources.length} fonte(s) citada(s)
              <ChevronRight className="h-3 w-3" />
            </button>
            <div className="flex flex-wrap gap-1.5">
              {message.sources.map(src => (
                <button
                  key={`citation-${src.chunk_id || src.fonte_n}`}
                  onClick={() => onCitationClick?.(src, message.sources!)}
                  className="rounded-full border border-[color:var(--ui-accent)]/40 bg-[color:var(--ui-accent-soft)] px-2 py-0.5 text-[11px] text-[color:var(--ui-accent)] hover:bg-[color:var(--ui-accent-soft)]/80"
                >
                  [Fonte {src.fonte_n}]
                </button>
              ))}
            </div>
          </div>
        )}

        {!isUser && (message.intent || message.action_metadata?.kind) && (
          <Badge variant="secondary" className="border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-xs text-[color:var(--ui-text-dim)]">
            {INTENT_LABELS[message.intent ?? message.action_metadata?.kind ?? ''] ?? 'Acao'}
          </Badge>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────

function ChatProactiveStartersPanel({
  recommendations,
  featureEnabled,
  capabilityUnlocked,
  loading = false,
  actionPending = false,
  entitlementTier = 'free',
  onRefreshAccess,
  onUpgradeIntent,
  onExecute,
  onUseInChat,
  onRecordAction,
  compact = false,
}: {
  recommendations: ProactiveRecommendationItem[]
  featureEnabled: boolean
  capabilityUnlocked: boolean
  loading?: boolean
  actionPending?: boolean
  entitlementTier?: string
  onRefreshAccess?: () => Promise<void> | void
  onUpgradeIntent?: () => void
  onExecute?: (item: ProactiveRecommendationItem) => void
  onUseInChat?: (item: ProactiveRecommendationItem) => void
  onRecordAction?: (payload: ProactiveRecommendationActionPayload) => Promise<void>
  compact?: boolean
}) {
  const visibleCount = compact ? 2 : 3

  if (!featureEnabled) return null

  if (!capabilityUnlocked) {
    return (
      <div className="rounded-2xl border border-amber-600/35 bg-amber-950/15 p-3">
        <p className="text-xs font-medium text-amber-100">
          Recomendacoes proativas exigem plano premium ({entitlementTier}).
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => { void onRefreshAccess?.() }}
            className="rounded-md border border-amber-500/45 px-2 py-1 text-[11px] text-amber-100 transition-colors hover:bg-amber-500/10"
          >
            Ja fiz upgrade, atualizar acesso
          </button>
          <button
            type="button"
            onClick={onUpgradeIntent}
            className="rounded-md border border-amber-500/25 px-2 py-1 text-[11px] text-amber-100/90 transition-colors hover:bg-amber-500/10"
          >
            Ver recursos premium
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-container-low)]/75 p-3 backdrop-blur">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[color:var(--ui-accent)]" />
        <p className="text-xs font-semibold text-[color:var(--ui-text)]">Sugestoes proativas</p>
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      ) : recommendations.length === 0 ? (
        <p className="text-xs text-[color:var(--ui-text-meta)]">
          Sem sugestoes no momento. Continue usando o produto para gerar novas recomendacoes.
        </p>
      ) : (
        <div className="space-y-2">
          {recommendations.slice(0, visibleCount).map(item => (
            <div
              key={item.id}
              className="rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-container-lowest)] px-3 py-2"
            >
              <p className="text-xs font-semibold text-[color:var(--ui-text)]">{item.title}</p>
              <p className="mt-1 text-[11px] text-[color:var(--ui-text-meta)]">{item.why_this}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onExecute?.(item)}
                  className="rounded-md border border-[color:var(--ui-accent)]/40 bg-[color:var(--ui-accent-soft)] px-2 py-1 text-[11px] text-[color:var(--ui-accent)] transition-colors hover:bg-[color:var(--ui-accent-soft)]/75"
                >
                  {item.action_label}
                </button>
                <button
                  type="button"
                  onClick={() => onUseInChat?.(item)}
                  className="rounded-md border border-[color:var(--ui-border-soft)] px-2 py-1 text-[11px] text-[color:var(--ui-text)] transition-colors hover:bg-[color:var(--ui-surface-2)]"
                >
                  Usar no chat
                </button>
                <button
                  type="button"
                  disabled={actionPending}
                  onClick={() => {
                    void onRecordAction?.({
                      recommendation_id: item.id,
                      category: item.category,
                      action: 'snooze',
                      duration_hours: 24,
                    })
                  }}
                  className="rounded-md border border-[color:var(--ui-border-soft)] px-2 py-1 text-[11px] text-[color:var(--ui-text-meta)] transition-colors hover:bg-[color:var(--ui-surface-2)] disabled:opacity-60"
                >
                  Adiar 24h
                </button>
                <button
                  type="button"
                  disabled={actionPending}
                  onClick={() => {
                    void onRecordAction?.({
                      recommendation_id: item.id,
                      category: item.category,
                      action: 'dismiss',
                    })
                  }}
                  className="rounded-md border border-rose-500/30 px-2 py-1 text-[11px] text-rose-300 transition-colors hover:bg-rose-500/10 disabled:opacity-60"
                >
                  Dispensar
                </button>
                <button
                  type="button"
                  aria-label={`Marcar ${item.title} como util`}
                  disabled={actionPending}
                  onClick={() => {
                    void onRecordAction?.({
                      recommendation_id: item.id,
                      category: item.category,
                      action: 'feedback_useful',
                    })
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 px-2 py-1 text-[11px] text-emerald-300 transition-colors hover:bg-emerald-500/10 disabled:opacity-60"
                >
                  <ThumbsUp className="h-3 w-3" />
                  Util
                </button>
                <button
                  type="button"
                  aria-label={`Marcar ${item.title} como nao util`}
                  disabled={actionPending}
                  onClick={() => {
                    void onRecordAction?.({
                      recommendation_id: item.id,
                      category: item.category,
                      action: 'feedback_not_useful',
                    })
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-rose-500/30 px-2 py-1 text-[11px] text-rose-300 transition-colors hover:bg-rose-500/10 disabled:opacity-60"
                >
                  <ThumbsDown className="h-3 w-3" />
                  Nao util
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function Chat() {
  const qc = useQueryClient()
  const capabilities = useCapabilities()
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions()
    return loaded.length > 0 ? loaded : [newSession()]
  })
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const loaded = loadSessions()
    return loaded.length > 0 ? loaded[0].id : sessions[0]?.id ?? newSession().id
  })
  const [input, setInput] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])
  const [strictGrounding, setStrictGrounding] = useState(false)
  const [composerOverrides, setComposerOverrides] = useState<ComposerPreferenceOverrides>(() => emptyComposerOverrides())
  const [activeSources, setActiveSources] = useState<SourceItem[]>([])
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => (
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)').matches : true
  ))
  const [isMobile, setIsMobile] = useState(() => (
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 1023px)').matches : false
  ))
  const [mobileViewportInset, setMobileViewportInset] = useState(0)
  const [mobileSourcesOpen, setMobileSourcesOpen] = useState(false)
  const [sessionSearch, setSessionSearch] = useState('')
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false)
  const [docPickerOpen, setDocPickerOpen] = useState(false)
  const [treatmentPickerOpen, setTreatmentPickerOpen] = useState(false)
  const [pendingFlashcardCommand, setPendingFlashcardCommand] = useState<FlashcardCommandPlan | null>(null)
  const [savingArtifactTurnRef, setSavingArtifactTurnRef] = useState<string | null>(null)
  const [chatDone, setChatDone] = useState(false)
  const [artifactSavedFromChat, setArtifactSavedFromChat] = useState(false)
  useStepAutoComplete('chat.first_question', chatDone)
  useStepAutoComplete('artifacts.first_save', artifactSavedFromChat)
  const bottomRef = useRef<HTMLDivElement>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null)

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? sessions[0]
  const messages = activeSession?.messages ?? EMPTY_MESSAGES
  const activeContext = activeSession?.activeContext ?? emptyActiveContext()
  const isStreamingEnabled = capabilities.isEnabled('chat_streaming_enabled')
  const isStrictGroundingEnabled = capabilities.isEnabled('strict_grounding_enabled')
  const isChatToArtifactEnabled = capabilities.isEnabled('premium_chat_to_artifact_enabled')
  const isChatToArtifactUnlocked = (
    isChatToArtifactEnabled
    && capabilities.hasCapability('premium_chat_to_artifact')
  )
  const isChatToArtifactLocked = isChatToArtifactEnabled && !isChatToArtifactUnlocked
  const isProactiveCopilotEnabled = capabilities.isEnabled('proactive_copilot_enabled')
  const isProactiveCopilotUnlocked = (
    isProactiveCopilotEnabled
    && capabilities.hasCapability('premium_proactive_copilot')
  )
  const isProactiveCopilotLocked = isProactiveCopilotEnabled && !isProactiveCopilotUnlocked
  const [lastUpgradeTouchpoint, setLastUpgradeTouchpoint] = useState('chat.chat_to_artifact_cta')
  const [wasChatToArtifactLocked, setWasChatToArtifactLocked] = useState(isChatToArtifactLocked)
  const [lastProactiveUpgradeTouchpoint, setLastProactiveUpgradeTouchpoint] = useState('chat.proactive_starters')
  const [wasProactiveCopilotLocked, setWasProactiveCopilotLocked] = useState(isProactiveCopilotLocked)
  const isPersonalizationEnabled = capabilities.isEnabled('personalization_enabled')
  const isPersonalizationUnlocked = (
    isPersonalizationEnabled
    && capabilities.hasCapability('premium_personalization')
  )
  const isPersonalizationLocked = isPersonalizationEnabled && !isPersonalizationUnlocked

  const preferencesQuery = useQuery<UserPreferences>({
    queryKey: ['user-preferences'],
    queryFn: apiClient.getPreferences,
    enabled: isPersonalizationUnlocked,
    staleTime: 30_000,
    retry: 1,
  })

  const proactiveRecommendationsQuery = useQuery<ProactiveRecommendationsResponse>({
    queryKey: ['chat-proactive-recommendations'],
    queryFn: apiClient.listProactiveRecommendations,
    staleTime: 60_000,
    retry: false,
    enabled: isProactiveCopilotUnlocked,
  })

  const userPreferences = preferencesQuery.data ?? DEFAULT_USER_PREFERENCES
  const resolvedComposerPreferences = resolveComposerPreferences(userPreferences, composerOverrides)
  const composerHasOverrides = hasComposerOverrides(composerOverrides)

  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  useEffect(() => {
    setPendingFlashcardCommand(null)
    setSavingArtifactTurnRef(null)
    setComposerOverrides(emptyComposerOverrides())
    setMobileSourcesOpen(false)
    setAttachmentMenuOpen(false)
    setDocPickerOpen(false)
    setTreatmentPickerOpen(false)
  }, [activeSessionId])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)')
    const handleChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches)
      setSidebarOpen(!event.matches)
    }

    setIsMobile(media.matches)
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', handleChange)
      return () => media.removeEventListener('change', handleChange)
    }
    media.addListener(handleChange)
    return () => media.removeListener(handleChange)
  }, [])

  useEffect(() => {
    if (!isMobile) {
      setMobileViewportInset(0)
      return
    }

    const updateInset = () => {
      const vv = window.visualViewport
      if (!vv) {
        setMobileViewportInset(0)
        return
      }
      const delta = window.innerHeight - vv.height - vv.offsetTop
      setMobileViewportInset(Math.max(0, Math.round(delta)))
    }

    updateInset()
    const vv = window.visualViewport
    vv?.addEventListener('resize', updateInset)
    vv?.addEventListener('scroll', updateInset)
    window.addEventListener('orientationchange', updateInset)
    window.addEventListener('resize', updateInset)

    return () => {
      vv?.removeEventListener('resize', updateInset)
      vv?.removeEventListener('scroll', updateInset)
      window.removeEventListener('orientationchange', updateInset)
      window.removeEventListener('resize', updateInset)
    }
  }, [isMobile])

  useEffect(() => {
    if (!isMobile) return
    if (activeSources.length > 0) {
      setMobileSourcesOpen(true)
    }
  }, [activeSources, isMobile])

  useEffect(() => {
    const textarea = composerTextareaRef.current
    if (!textarea) return

    const maxHeight = isMobile ? 188 : 236
    textarea.style.height = '0px'
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [input, isMobile, selectedDocs.length])

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  useEffect(() => {
    if (!docs) return

    const contextDocIds = new Set(activeContext.active_doc_ids)
    const contextDocNames = new Set(activeContext.active_doc_names)
    const hydrated = docs.filter(doc =>
      contextDocIds.has(doc.doc_id) || contextDocNames.has(doc.file_name)
    )

    setSelectedDocs(prev => {
      const prevIds = prev.map(doc => doc.doc_id).join('|')
      const nextIds = hydrated.map(doc => doc.doc_id).join('|')
      return prevIds === nextIds ? prev : hydrated
    })
  }, [activeContext.active_doc_ids, activeContext.active_doc_names, docs])

  useEffect(() => {
    if (!isStrictGroundingEnabled && strictGrounding) {
      setStrictGrounding(false)
    }
  }, [isStrictGroundingEnabled, strictGrounding])

  function appendAssistantMessage(message: Message) {
    setSessions(prev =>
      prev.map(s =>
        s.id === activeSessionId
          ? { ...s, messages: [...s.messages, message] }
          : s
      )
    )
  }

  function updateSessionActiveContext(sessionId: string, nextContext: ChatActiveContext) {
    setSessions(prev =>
      prev.map(s =>
        s.id === sessionId
          ? { ...s, activeContext: normalizeActiveContext(nextContext) }
          : s
      )
    )
  }

  function updateActiveContext(nextContext: ChatActiveContext) {
    updateSessionActiveContext(activeSessionId, nextContext)
  }

  function addDocToActiveContext(docToAdd: DocItem) {
    if (selectedDocs.some(item => item.doc_id === docToAdd.doc_id)) {
      setAttachmentMenuOpen(false)
      setDocPickerOpen(false)
      setTreatmentPickerOpen(false)
      return
    }

    const nextDocs = [...selectedDocs, docToAdd]
    setSelectedDocs(nextDocs)
    updateActiveContext(normalizeActiveContext({
      ...activeContext,
      active_doc_ids: nextDocs.map(doc => doc.doc_id),
      active_doc_names: nextDocs.map(doc => doc.file_name),
    }))

    if (pendingFlashcardCommand && pendingFlashcardCommand.docs.length === 0) {
      const scopeLabel = `documento selecionado "${docToAdd.file_name}"`
      setPendingFlashcardCommand({
        ...pendingFlashcardCommand,
        docs: [docToAdd],
        scopeLabel,
        summary: `Vou gerar ${pendingFlashcardCommand.numCards} flashcards para ${scopeLabel}.`,
      })
    }

    setAttachmentMenuOpen(false)
    setDocPickerOpen(false)
    setTreatmentPickerOpen(false)
  }

  function removeDocFromActiveContext(docId: string) {
    const nextDocs = selectedDocs.filter(item => item.doc_id !== docId)
    setSelectedDocs(nextDocs)
    updateActiveContext(normalizeActiveContext({
      ...activeContext,
      active_doc_ids: nextDocs.map(item => item.doc_id),
      active_doc_names: nextDocs.map(item => item.file_name),
    }))
  }

  function appendStreamingAssistantPlaceholder(
    sessionId: string,
    userPrompt: string,
    contextSnapshot: ChatActiveContext,
  ) {
    setSessions(prev =>
      prev.map(s =>
        s.id === sessionId
          ? {
            ...s,
            messages: [
              ...s.messages,
              {
                role: 'assistant',
                content: '',
                prompt_hint: userPrompt,
                streaming: true,
                stream_stage: 'analyzing',
                stream_status_text: STREAM_STAGE_DETAIL_DEFAULT.analyzing,
                stream_interrupted: false,
                active_context_snapshot: normalizeActiveContext(contextSnapshot),
                sources: [],
                intent: 'qa',
                quality_signal: null,
                action_metadata: null,
                calendar_action: null,
              },
            ],
          }
          : s
      )
    )
  }

  function updateStreamingStage(
    sessionId: string,
    rawStage: string | null | undefined,
    detail?: string | null,
  ) {
    const stage = normalizeStreamStage(rawStage)
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId || s.messages.length === 0) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (!last || last.role !== 'assistant' || !last.streaming) return s

        const previousStage = normalizeStreamStage(last.stream_stage ?? null)
        let nextStage = stage ?? previousStage
        if (!nextStage) {
          nextStage = 'analyzing'
        }

        if (
          previousStage
          && STREAM_STAGE_ORDER[nextStage] < STREAM_STAGE_ORDER[previousStage]
        ) {
          nextStage = previousStage
        }

        msgs[msgs.length - 1] = {
          ...last,
          stream_stage: nextStage,
          stream_status_text: detail?.trim() || STREAM_STAGE_DETAIL_DEFAULT[nextStage],
          stream_interrupted: false,
        }
        return { ...s, messages: msgs }
      }),
    )
  }

  function markStreamingInterruption(sessionId: string, guidance: string) {
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId || s.messages.length === 0) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (!last || last.role !== 'assistant') return s
        msgs[msgs.length - 1] = {
          ...last,
          stream_interrupted: true,
          stream_status_text: guidance,
          stream_stage: last.stream_stage ?? 'finalizing',
        }
        return { ...s, messages: msgs }
      }),
    )
  }

  function appendDeltaToStreamingMessage(sessionId: string, delta: string) {
    if (!delta) return
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId || s.messages.length === 0) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (!last || last.role !== 'assistant' || !last.streaming) return s
        msgs[msgs.length - 1] = {
          ...last,
          content: `${last.content}${delta}`,
          stream_stage: 'drafting',
          stream_status_text: STREAM_STAGE_DETAIL_DEFAULT.drafting,
          stream_interrupted: false,
        }
        return { ...s, messages: msgs }
      })
    )
  }

  function finalizeStreamingAssistantMessage(sessionId: string, data: ChatResponse, userPrompt: string) {
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId || s.messages.length === 0) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (!last || last.role !== 'assistant') return s
        const safeAnswer = typeof data.answer === 'string' ? data.answer.trim() : ''
        msgs[msgs.length - 1] = {
          ...last,
          content: safeAnswer ? data.answer : (last.content ?? ''),
          streaming: false,
          stream_stage: null,
          stream_status_text: null,
          stream_interrupted: false,
          prompt_hint: userPrompt,
          active_context_snapshot: normalizeActiveContext(data.active_context ?? last.active_context_snapshot),
          sources: data.sources ?? [],
          intent: data.intent,
          calendar_action: data.calendar_action ?? null,
          quality_signal: data.quality_signal ?? null,
          action_metadata: (data.action_metadata as ChatActionMetadata | null) ?? null,
          needs_confirmation: Boolean(data.needs_confirmation ?? false),
          confirmation_text: data.confirmation_text ?? null,
          suggested_reply: data.suggested_reply ?? null,
        }
        return { ...s, messages: msgs }
      })
    )
  }

  function failStreamingAssistantMessage(sessionId: string, message: string) {
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          const hasPartialContent = Boolean(last.content?.trim())
          const nextContent = hasPartialContent
            ? `${last.content}\n\n${message}`
            : message
          msgs[msgs.length - 1] = {
            ...last,
            content: nextContent,
            streaming: false,
            stream_interrupted: true,
            stream_status_text: 'Conexao interrompida. Reenvie para tentar novamente.',
            stream_stage: 'finalizing',
          }
          return { ...s, messages: msgs }
        }
        return {
          ...s,
          messages: [
            ...msgs,
            {
              role: 'assistant',
              content: message,
              stream_interrupted: true,
              stream_status_text: 'Conexao interrompida. Reenvie para tentar novamente.',
              stream_stage: 'finalizing',
            },
          ],
        }
      })
    )
  }

  function extractStreamFailureDetail(error: unknown): string {
    if (error instanceof ChatStreamError) return error.message
    if (axios.isAxiosError(error)) {
      if (typeof error.response?.data?.detail === 'string') return error.response.data.detail
      return error.message || 'Falha no streaming.'
    }
    if (error instanceof Error) return error.message || 'Falha no streaming.'
    return 'Falha no streaming.'
  }

  function isRecoverableStreamFailure(error: unknown): boolean {
    if (error instanceof ChatStreamError) return error.recoverable
    if ((error as { name?: string } | null)?.name === 'AbortError') return false

    if (axios.isAxiosError(error)) {
      const status = error.response?.status
      if (!status) return true
      return status >= 500 || status === 408 || status === 429
    }

    if (error instanceof Error) {
      const detail = error.message.toLowerCase()
      if (
        detail.includes('timeout')
        || detail.includes('timed out')
        || detail.includes('failed to fetch')
        || detail.includes('network')
        || detail.includes('stream encerrado')
      ) {
        return true
      }
      if (
        detail.includes('401')
        || detail.includes('403')
        || detail.includes('unauthorized')
        || detail.includes('forbidden')
      ) {
        return false
      }
    }

    return true
  }

  const flashcardBatchMut = useMutation({
    mutationFn: async (plan: FlashcardCommandPlan): Promise<FlashcardBatchResult[]> => {
      if (plan.docs.length === 0) return []

      const results: FlashcardBatchResult[] = []
      for (const doc of plan.docs) {
        try {
          const deck = await apiClient.generateFlashcards(
            doc.file_name,
            plan.numCards,
            plan.contentFilter,
            plan.difficultyMode,
            plan.difficultyCustom,
          )
          results.push({ doc, success: true, deck })
        } catch (error) {
          let message = 'Falha ao gerar flashcards.'
          if (axios.isAxiosError(error)) {
            message = typeof error.response?.data?.detail === 'string'
              ? error.response.data.detail
              : error.message || message
          } else if (error instanceof Error) {
            message = error.message || message
          }
          results.push({ doc, success: false, error: message })
        }
      }

      return results
    },
    onSuccess: (results, plan) => {
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      updateActiveContext(normalizeActiveContext({
        ...activeContext,
        active_doc_ids: plan.docs.map(doc => doc.doc_id),
        active_doc_names: plan.docs.map(doc => doc.file_name),
        active_deck_id: results.length === 1 ? results[0].deck?.id ?? null : null,
        active_deck_title: results.length === 1 ? results[0].deck?.title ?? null : null,
        active_intent: 'flashcards_batch',
        last_action: 'flashcards_batch',
        last_card_count: plan.numCards,
        last_difficulty_mix: plan.difficultyCustom,
      }))

      const successCount = results.filter(item => item.success).length
      const failureCount = results.length - successCount
      const deckSummary = results
        .filter(item => item.success && item.deck)
        .map(item => `- ${item.doc.file_name}: ${item.deck?.cards.length ?? plan.numCards} cards`)
      const failureSummary = results
        .filter(item => !item.success)
        .map(item => `- ${item.doc.file_name}: ${item.error ?? 'erro desconhecido'}`)

      const contentLines = [
        successCount > 0
          ? `Gerei ${successCount} deck${successCount !== 1 ? 's' : ''} com sucesso.`
          : 'Nao consegui gerar nenhum deck.',
        '',
        ...(deckSummary.length > 0 ? ['Concluidos:', ...deckSummary, ''] : []),
        ...(failureSummary.length > 0 ? ['Falhas:', ...failureSummary, ''] : []),
        'Abra a pagina de Flashcards para revisar os decks criados.',
      ]

      const actionMetadata: ChatActionMetadata = {
        kind: 'flashcards_batch',
        title: successCount === results.length
          ? 'Flashcards em lote executados'
          : 'Flashcards em lote parcialmente executados',
        summary: `${successCount} deck${successCount !== 1 ? 's' : ''} criado${successCount !== 1 ? 's' : ''} para ${plan.docs.length} documento${plan.docs.length !== 1 ? 's' : ''}.`,
        status: successCount === results.length ? 'executed' : 'failed',
        scope: plan.scopeLabel,
        doc_names: plan.docs.map(doc => doc.file_name),
        doc_count: plan.docs.length,
        card_count: plan.numCards,
        difficulty: plan.difficultyCustom,
        next_steps: [
          'Abra Flashcards para revisar ou continuar o estudo.',
          ...(failureCount > 0 ? ['Revise as falhas abaixo e tente novamente para os documentos restantes.'] : []),
        ],
        links: [
          { label: 'Abrir Flashcards', href: '/flashcards' },
          { label: 'Ver Documentos', href: '/docs' },
        ],
        error: failureCount > 0 ? `${failureCount} documento${failureCount !== 1 ? 's' : ''} falharam.` : null,
      }

      appendAssistantMessage({
        role: 'assistant',
        content: contentLines.join('\n'),
        intent: 'flashcards_batch',
        action_metadata: actionMetadata,
        calendar_action: null,
      })

      if (successCount === results.length) {
        toast.success(`Flashcards gerados para ${plan.docs.length} documento${plan.docs.length !== 1 ? 's' : ''}.`)
      } else if (successCount > 0) {
        toast.warning('Alguns decks foram gerados, mas outros falharam.')
      } else {
        toast.error('Nao consegui gerar os flashcards em lote.')
      }
    },
    onError: (error) => {
      toast.error(error.message || 'Falha ao executar o lote de flashcards.')
      appendAssistantMessage({
        role: 'assistant',
        content: 'Nao consegui executar o lote de flashcards agora. Tente novamente em instantes.',
        intent: 'flashcards_batch',
        action_metadata: {
          kind: 'flashcards_batch',
          title: 'Flashcards em lote falharam',
          summary: 'A execucao em lote nao concluiu.',
          status: 'failed',
          links: [
            { label: 'Abrir Flashcards', href: '/flashcards' },
          ],
          error: error.message || 'Erro inesperado',
        },
        calendar_action: null,
      })
    },
  })

  const mutation = useMutation<ChatResponse, Error, ChatRunPayload>({
    mutationFn: async (payload) => {
      appendStreamingAssistantPlaceholder(payload.sessionId, payload.displayMessage, payload.activeContext)

      if (streamAbortRef.current) {
        streamAbortRef.current.abort()
      }
      const controller = new AbortController()
      streamAbortRef.current = controller
      let fallbackAttempted = false

      try {
        if (!isStreamingEnabled) {
          updateStreamingStage(
            payload.sessionId,
            'retrieving',
            'Streaming indisponivel. Gerando resposta completa.',
          )
          return await apiClient.chat(
            payload.message,
            payload.sessionId,
            undefined,
            payload.docIds,
            payload.strictGrounding && isStrictGroundingEnabled,
            payload.history,
            payload.activeContext,
          )
        }
        return await apiClient.chatStream(
          payload.message,
          payload.sessionId,
          undefined,
          payload.docIds,
          payload.strictGrounding && isStrictGroundingEnabled,
          payload.history,
          payload.activeContext,
          {
            onStart: () => updateStreamingStage(payload.sessionId, 'analyzing'),
            onStatus: status => updateStreamingStage(payload.sessionId, status.stage, status.detail),
            onDelta: delta => appendDeltaToStreamingMessage(payload.sessionId, delta),
            onError: detail => {
              markStreamingInterruption(
                payload.sessionId,
                `${detail}. Alternando para modo de recuperacao.`,
              )
            },
          },
          controller.signal,
        )
      } catch (streamError: any) {
        if (controller.signal.aborted || streamError?.name === 'AbortError') {
          throw streamError
        }
        if (!isRecoverableStreamFailure(streamError) || fallbackAttempted) {
          throw streamError
        }
        fallbackAttempted = true

        const streamFailureDetail = extractStreamFailureDetail(streamError)
        markStreamingInterruption(
          payload.sessionId,
          `${streamFailureDetail} Continuando em modo padrao.`,
        )
        updateStreamingStage(
          payload.sessionId,
          'finalizing',
          'Recuperando resposta final sem streaming.',
        )
        try {
          return await apiClient.chat(
            payload.message,
            payload.sessionId,
            undefined,
            payload.docIds,
            payload.strictGrounding && isStrictGroundingEnabled,
            payload.history,
            payload.activeContext,
            { streamFallback: true },
          )
        } catch (fallbackError: any) {
          const fallbackDetail = extractStreamFailureDetail(fallbackError)
          markStreamingInterruption(
            payload.sessionId,
            `${fallbackDetail} Nao consegui recuperar automaticamente. Reenvie a pergunta para tentar de novo.`,
          )
          throw fallbackError
        }
      } finally {
        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null
        }
      }
    },
    onSuccess: (data, variables) => {
      finalizeStreamingAssistantMessage(variables.sessionId, data, variables.displayMessage)
      updateSessionActiveContext(variables.sessionId, normalizeActiveContext(data.active_context))
      setChatDone(true)

      if (data.sources.length > 0) {
        setActiveSources(data.sources)
        setSelectedSource(null)
      }
      if (data.calendar_action) {
        qc.invalidateQueries({ queryKey: ['calendar-reminders'] })
        qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
        qc.invalidateQueries({ queryKey: ['calendar-overview'] })
      }
    },
    onError: (err: any, variables) => {
      if (err?.name === 'AbortError') return
      const errorText = err?.response?.data?.detail ?? err?.message ?? 'Erro ao consultar o agente'
      toast.error(errorText)
      failStreamingAssistantMessage(
        variables.sessionId,
        'Nao consegui concluir esta resposta agora. Verifique sua conexao e clique em enviar novamente.',
      )
    },
  })

  function handleUpgradeIntent(touchpoint: string, source: 'link' | 'refresh_access' = 'link') {
    setLastUpgradeTouchpoint(touchpoint)
    trackUpgradeInitiated({
      touchpoint,
      capability: 'premium_chat_to_artifact',
      metadata: { surface: 'chat', source },
    })
  }

  function handleProactiveUpgradeIntent(
    touchpoint = 'chat.proactive_starters',
    source: 'link' | 'refresh_access' = 'link',
  ) {
    setLastProactiveUpgradeTouchpoint(touchpoint)
    trackUpgradeInitiated({
      touchpoint,
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'chat', source },
    })
  }

  async function handleRefreshPremiumAccess(touchpoint = 'chat.chat_to_artifact_cta') {
    handleUpgradeIntent(touchpoint, 'refresh_access')
    await capabilities.refresh()
    toast.info('Acesso premium atualizado. Se o upgrade ja foi aplicado, recarregamos suas capacidades.')
  }

  async function handleRefreshProactiveAccess(touchpoint = 'chat.proactive_starters') {
    handleProactiveUpgradeIntent(touchpoint, 'refresh_access')
    await capabilities.refresh()
    await proactiveRecommendationsQuery.refetch()
    toast.info('Acesso premium atualizado. Se o upgrade ja foi aplicado, recarregamos suas capacidades.')
  }

  const saveChatArtifactMut = useMutation({
    mutationFn: async (payload: {
      turnRef: string
      message: Message
      userPrompt: string
      sessionId: string
    }) => {
      const contextSnapshot = normalizeActiveContext(
        payload.message.active_context_snapshot ?? activeContext,
      )
      const mergedDocIds = Array.from(
        new Set([
          ...selectedDocs.map(doc => doc.doc_id),
          ...contextSnapshot.active_doc_ids,
        ].map(value => String(value || '').trim()).filter(Boolean)),
      )
      const mergedDocNames = Array.from(
        new Set([
          ...selectedDocs.map(doc => doc.file_name),
          ...contextSnapshot.active_doc_names,
        ].map(value => String(value || '').trim()).filter(Boolean)),
      )

      return apiClient.createArtifactFromChat({
        answer: payload.message.content,
        title: payload.userPrompt || 'Resumo aprofundado do chat',
        user_prompt: payload.userPrompt,
        session_id: payload.sessionId,
        turn_ref: payload.turnRef,
        doc_ids: mergedDocIds,
        doc_names: mergedDocNames,
        artifact_type: 'summary',
        generation_profile: 'chat:deep_summary:one_click',
        confidence_level: payload.message.quality_signal?.level ?? undefined,
        confidence_score: payload.message.quality_signal?.score ?? undefined,
      })
    },
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      qc.invalidateQueries({ queryKey: ['artifact-filter-options'] })
      trackPremiumFeatureActivation({
        touchpoint: 'chat.chat_to_artifact_save',
        capability: 'premium_chat_to_artifact',
        metadata: { surface: 'chat', artifact_filename: result.filename },
      }, false)
      setArtifactSavedFromChat(true)
      toast.success(`Artefato salvo: ${result.filename}`)
      setSavingArtifactTurnRef(null)
    },
    onError: (error: any) => {
      const lockedDetail = extractLockedFeatureDetail(error)
      if (lockedDetail) {
        toast.error(
          `Salvar como artefato bloqueado: ${lockedDetail.capability} exige plano ${lockedDetail.required_tier}.`
        )
        setSavingArtifactTurnRef(null)
        void handleRefreshPremiumAccess()
        return
      }
      const detail = error?.response?.data?.detail ?? error?.message ?? 'Falha ao salvar artefato.'
      toast.error(String(detail))
      setSavingArtifactTurnRef(null)
    },
  })

  const proactiveRecommendationActionMutation = useMutation({
    mutationFn: (payload: ProactiveRecommendationActionPayload) =>
      apiClient.recordProactiveRecommendationAction(payload),
    onSuccess: (_result, payload) => {
      const successMessage = RECOMMENDATION_ACTION_TOAST[payload.action]
      if (successMessage) {
        toast.success(successMessage)
      }
      void proactiveRecommendationsQuery.refetch()
    },
    onError: (error: unknown) => {
      const lockedDetail = extractLockedFeatureDetail(error)
      if (lockedDetail?.capability === 'premium_proactive_copilot') {
        toast.error(
          `Recomendacoes proativas bloqueadas: ${lockedDetail.capability} exige plano ${lockedDetail.required_tier}.`,
        )
        void handleRefreshProactiveAccess()
        return
      }
      toast.error(getApiErrorDetail(error, 'Nao foi possivel registrar a acao da recomendacao.'))
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, mutation.isPending, flashcardBatchMut.isPending, pendingFlashcardCommand])

  // Cleanup stream on unmount
  useEffect(
    () => () => {
      if (streamAbortRef.current) {
        streamAbortRef.current.abort()
      }
    },
    [],
  )

  function confirmFlashcardCommand() {
    if (!pendingFlashcardCommand) return
    if (pendingFlashcardCommand.docs.length === 0) {
      // Open document picker so user can select a document right here
      setAttachmentMenuOpen(false)
      setTreatmentPickerOpen(false)
      setDocPickerOpen(true)
      return
    }

    const plan = pendingFlashcardCommand
    setPendingFlashcardCommand(null)
    flashcardBatchMut.mutate(plan)
  }

  function cancelFlashcardCommand() {
    setPendingFlashcardCommand(null)
    appendAssistantMessage({
      role: 'assistant',
      content: 'Comando de flashcards cancelado. Se quiser, reenvie com os documentos selecionados ou diga "todos os documentos".',
      intent: 'action_confirmation',
      action_metadata: {
        kind: 'action_confirmation',
        title: 'Comando cancelado',
        summary: 'A acao foi descartada.',
        status: 'preview',
        links: [
          { label: 'Abrir Flashcards', href: '/flashcards' },
        ],
      },
      calendar_action: null,
    })
  }

  function handleSend() {
    const text = input.trim()
    if (!text || mutation.isPending || flashcardBatchMut.isPending) return
    // Block send only when there's a pending command WITH docs (awaiting confirmation)
    if (pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0) return
    // If there's a pending command with no docs, cancel it and process new message
    if (pendingFlashcardCommand && pendingFlashcardCommand.docs.length === 0) {
      setPendingFlashcardCommand(null)
    }

    const userMsg: Message = { role: 'user', content: text }
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== activeSessionId) return s
        const updated = { ...s, messages: [...s.messages, userMsg] }
        if (s.messages.length === 0) {
          updated.title = text.length > 40 ? text.slice(0, 40) + '…' : text
        }
        return updated
      })
    )
    setInput('')

    const draft = parseFlashcardCommandPlan(text, docs ?? [], selectedDocs)
    if (draft) {
      setPendingFlashcardCommand(draft)
      // Persist the assistant response as a real message so it survives navigation
      appendAssistantMessage({
        role: 'assistant',
        content: draft.docs.length > 0
          ? draft.summary
          : 'Encontrei um pedido de flashcards, mas preciso que você selecione um documento nas opções abaixo ou diga "todos os documentos".',
        intent: 'action_confirmation',
        action_metadata: {
          kind: 'flashcards_batch',
          title: draft.docs.length > 0 ? 'Confirme o comando de flashcards' : 'Preciso do escopo dos flashcards',
          summary: draft.summary,
          status: 'needs_confirmation',
          scope: draft.scopeLabel,
          doc_count: draft.docs.length,
          card_count: draft.numCards,
          difficulty: draft.difficultyCustom,
          doc_names: draft.docs.map(d => d.file_name),
        },
        calendar_action: null,
      })
      return
    }

    const targetSession = activeSession
    const recentHistory = (targetSession?.messages ?? [])
      .filter(m => !m.streaming)
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }))
    const strictGroundingFromPreferences = (
      isPersonalizationUnlocked
      && resolvedComposerPreferences.strictness_preference === 'strict'
      && isStrictGroundingEnabled
    )
    const strictGroundingForRequest = (
      isStrictGroundingEnabled
      && (strictGrounding || strictGroundingFromPreferences)
    )
    const messageForBackend = isPersonalizationUnlocked
      ? `${text}${buildPreferenceInstructionBlock(resolvedComposerPreferences)}`
      : text

    mutation.mutate({
      message: messageForBackend,
      displayMessage: text,
      sessionId: targetSession?.id ?? activeSessionId,
      docIds: selectedDocs.map(doc => doc.doc_id),
      strictGrounding: strictGroundingForRequest,
      history: recentHistory,
      activeContext: targetSession?.activeContext ?? emptyActiveContext(),
    })
    setComposerOverrides(emptyComposerOverrides())
  }

  function pauseCurrentGeneration() {
    setSessions(prev =>
      prev.map(session => {
        const msgs = [...session.messages]
        for (let i = msgs.length - 1; i >= 0; i -= 1) {
          const msg = msgs[i]
          if (msg.role === 'assistant' && msg.streaming) {
            const hasPartialContent = Boolean(msg.content?.trim())
            msgs[i] = {
              ...msg,
              content: hasPartialContent
                ? msg.content
                : 'Geracao pausada. Clique em enviar para fazer uma nova pergunta.',
              streaming: false,
              stream_interrupted: true,
              stream_status_text: 'Geracao pausada por voce.',
              stream_stage: msg.stream_stage ?? 'finalizing',
            }
            return { ...session, messages: msgs }
          }
        }
        return session
      }),
    )

    if (streamAbortRef.current) {
      streamAbortRef.current.abort()
      streamAbortRef.current = null
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function createNewSession() {
    const s = newSession()
    setSessions(prev => [s, ...prev])
    setActiveSessionId(s.id)
    setActiveSources([])
    setSelectedSource(null)
    setSelectedDocs([])
  }

  function deleteSession(id: string) {
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      if (next.length === 0) {
        const fresh = newSession()
        setActiveSessionId(fresh.id)
        return [fresh]
      }
      if (id === activeSessionId) setActiveSessionId(next[0].id)
      return next
    })
  }

  function handleUseRecommendationInChat(recommendation: ProactiveRecommendationItem) {
    const prompt = buildRecommendationPrompt(recommendation, activeContext)
    setInput(prompt)
    toast.info('Sugestao aplicada ao campo de mensagem.')
  }

  function handleExecuteRecommendation(recommendation: ProactiveRecommendationItem) {
    trackPremiumFeatureActivation({
      touchpoint: 'chat.proactive_starters.execute',
      capability: 'premium_proactive_copilot',
      metadata: {
        surface: 'chat',
        recommendation_id: recommendation.id,
        category: recommendation.category,
        action_to: recommendation.action_to,
      },
    }, false)
    window.location.href = recommendation.action_to
  }

  async function handleRecordRecommendationAction(payload: ProactiveRecommendationActionPayload) {
    await proactiveRecommendationActionMutation.mutateAsync(payload)
  }

  const hasSources = activeSources.length > 0
  const isStreaming = messages.some(m => m.streaming)
  const isPending = mutation.isPending || flashcardBatchMut.isPending
  const isChatRequestActive = mutation.isPending || isStreaming
  const isComposerBlocked = (
    flashcardBatchMut.isPending
    || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)
  )
  const isPersonalizationLoading = isPersonalizationUnlocked && preferencesQuery.isLoading
  const personalizationLoadFailed = isPersonalizationUnlocked && preferencesQuery.isError
  const personalizationBannerText = !isPersonalizationEnabled
    ? ''
    : isPersonalizationLocked
      ? `Memoria premium bloqueada no plano atual (${capabilities.entitlementTier}).`
    : isPersonalizationLoading
      ? 'Carregando suas preferencias...'
      : personalizationLoadFailed
        ? 'Nao foi possivel carregar preferencias. Usando defaults seguros.'
        : `Usando suas preferencias: ${DEPTH_LABELS[resolvedComposerPreferences.default_depth]}, `
          + `${TONE_LABELS[resolvedComposerPreferences.tone]}, `
          + `rigor ${STRICTNESS_LABELS[resolvedComposerPreferences.strictness_preference]} `
          + `e rotina ${SCHEDULE_LABELS[userPreferences.schedule_preference]}.`
  const normalizedSessionSearch = normalizeForMatch(sessionSearch)
  const visibleSessions = sessions.filter(session => {
    if (!normalizedSessionSearch) return true
    const scope = `${session.title} ${getSessionPreview(session)}`
    return normalizeForMatch(scope).includes(normalizedSessionSearch)
  })
  const proactiveRecommendations = proactiveRecommendationsQuery.data?.recommendations ?? []
  const hasProactiveTouchpoint = (
    isProactiveCopilotEnabled
    && (isProactiveCopilotLocked || proactiveRecommendations.length > 0)
  )
  const hasArtifactUnlockPrompt = isChatToArtifactLocked && messages.some((msg, i) => {
    if (msg.role !== 'assistant') return false
    const previousUserPrompt = [...messages.slice(0, i)]
      .reverse()
      .find(item => item.role === 'user')
      ?.content ?? msg.prompt_hint ?? ''
    return shouldOfferChatArtifactCTA({
      ...msg,
      prompt_hint: previousUserPrompt,
    })
  })

  useEffect(() => {
    if (!hasArtifactUnlockPrompt) return
    trackPremiumTouchpointViewed({
      touchpoint: 'chat.chat_to_artifact_cta',
      capability: 'premium_chat_to_artifact',
      metadata: { surface: 'chat' },
    })
  }, [hasArtifactUnlockPrompt])

  useEffect(() => {
    if (!hasProactiveTouchpoint) return
    trackPremiumTouchpointViewed({
      touchpoint: 'chat.proactive_starters',
      capability: 'premium_proactive_copilot',
      metadata: { surface: 'chat' },
    })
  }, [hasProactiveTouchpoint])

  useEffect(() => {
    if (wasChatToArtifactLocked && !isChatToArtifactLocked) {
      trackUpgradeCompleted({
        touchpoint: lastUpgradeTouchpoint,
        capability: 'premium_chat_to_artifact',
        metadata: { surface: 'chat' },
      })
      trackPremiumFeatureActivation({
        touchpoint: 'chat.chat_to_artifact_cta',
        capability: 'premium_chat_to_artifact',
        metadata: { surface: 'chat', source: 'unlock_transition' },
      })
    }
    setWasChatToArtifactLocked(isChatToArtifactLocked)
  }, [isChatToArtifactLocked, lastUpgradeTouchpoint, wasChatToArtifactLocked])

  useEffect(() => {
    if (wasProactiveCopilotLocked && !isProactiveCopilotLocked) {
      trackUpgradeCompleted({
        touchpoint: lastProactiveUpgradeTouchpoint,
        capability: 'premium_proactive_copilot',
        metadata: { surface: 'chat' },
      })
      trackPremiumFeatureActivation({
        touchpoint: 'chat.proactive_starters',
        capability: 'premium_proactive_copilot',
        metadata: { surface: 'chat', source: 'unlock_transition' },
      })
    }
    setWasProactiveCopilotLocked(isProactiveCopilotLocked)
  }, [isProactiveCopilotLocked, lastProactiveUpgradeTouchpoint, wasProactiveCopilotLocked])

  useEffect(() => {
    if (!(isProactiveCopilotUnlocked && !proactiveRecommendationsQuery.isLoading && !proactiveRecommendationsQuery.isError)) return
    if (proactiveRecommendations.length <= 0) return
    trackPremiumFeatureActivation({
      touchpoint: 'chat.proactive_starters',
      capability: 'premium_proactive_copilot',
      metadata: {
        surface: 'chat',
        source: 'starters_loaded',
        recommendation_count: proactiveRecommendations.length,
      },
    })
  }, [
    isProactiveCopilotUnlocked,
    proactiveRecommendations.length,
    proactiveRecommendationsQuery.isError,
    proactiveRecommendationsQuery.isLoading,
  ])

  useEffect(() => {
    if (!(isPersonalizationUnlocked && !preferencesQuery.isLoading && !preferencesQuery.isError)) return
    trackPremiumFeatureActivation({
      touchpoint: 'chat.personalization_memory',
      capability: 'premium_personalization',
      metadata: { surface: 'chat', source: 'memory_banner' },
    })
  }, [isPersonalizationUnlocked, preferencesQuery.isError, preferencesQuery.isLoading])

  return (
    <>
    <SectionIntro sectionId="chat" className="mx-2 mt-2" />
    <div className={cn(
      'chat-no-glass relative flex h-[calc(100svh-3.5rem)] overflow-hidden bg-transparent md:h-[100dvh]',
      isMobile
        ? 'rounded-none shadow-none'
        : 'rounded-[1.4rem] shadow-[0_26px_70px_rgba(0,0,0,0.45)]',
    )}>
      {/* ── Sidebar de sessões ────────────────────────────────────────────── */}
      {sidebarOpen && (
        <>
          {isMobile ? (
            <button
              type="button"
              aria-label="Fechar conversas"
              onClick={() => setSidebarOpen(false)}
              className="absolute inset-0 z-30 bg-black/72 backdrop-blur-[2px]"
            />
          ) : null}
          <aside className={cn(
            'z-40 flex flex-col',
            isMobile
              ? 'absolute inset-y-0 left-0 w-[88vw] max-w-[22rem] border-r border-[color:var(--ui-border-soft)] bg-[#0b1119] shadow-[0_24px_54px_rgba(0,0,0,0.6)]'
              : 'w-[19rem] shrink-0 bg-[color:var(--ui-surface)]',
          )}>
          <div className={cn(
            'border-b border-[color:var(--ui-border-soft)]',
            isMobile ? 'px-4 pb-4 pt-4' : 'px-6 pb-5 pt-6',
          )}>
            <div className="mb-6 flex items-center justify-between">
              <h2 className={cn(
                'font-headline font-extrabold tracking-tight text-[color:var(--ui-text)]',
                isMobile ? 'text-lg' : 'text-xl',
              )}>
                Conversas
              </h2>
              <button
                onClick={() => {
                  createNewSession()
                  if (isMobile) setSidebarOpen(false)
                }}
                className={cn(
                  'inline-flex h-9 w-9 items-center justify-center rounded-xl text-[color:var(--ui-accent)] transition-colors',
                  isMobile ? 'bg-[#1a2538] hover:bg-[#21304a]' : 'bg-[color:var(--ui-surface-2)] hover:bg-[color:var(--ui-surface-3)]',
                )}
                title="Nova conversa"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>

            <label htmlFor="session-search" className="sr-only">
              Buscar conversa
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--ui-text-meta)]" />
              <input
                id="session-search"
                type="text"
                value={sessionSearch}
                onChange={event => setSessionSearch(event.target.value)}
                placeholder="Buscar conversas..."
                className={cn(
                  'h-10 w-full rounded-xl border border-[color:var(--ui-border-soft)] pl-10 pr-3 text-sm text-[color:var(--ui-text)] outline-none transition-all placeholder:text-[color:var(--ui-text-meta)] focus:border-[color:var(--ui-accent)] focus:ring-2 focus:ring-[color:var(--ui-accent)]/20',
                  isMobile ? 'bg-[#101a2a]' : 'bg-[color:var(--ui-surface-container-lowest)]',
                )}
              />
            </div>
          </div>
          <div className={cn(
            'flex-1 space-y-2 overflow-y-auto px-4',
            isMobile ? 'pb-4 pt-3' : 'py-4',
          )}>
            {visibleSessions.map(session => {
              const isActive = session.id === activeSessionId
              const messageCount = session.messages.filter(message => !message.streaming).length
              const isRunning = session.messages.some(message => message.streaming)
              const status = isActive ? 'ACTIVE' : (isRunning ? 'RUNNING' : messageCount > 1 ? 'ARCHIVED' : 'DRAFT')

              return (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setActiveSessionId(session.id)
                    setActiveSources([])
                    setSelectedSource(null)
                    if (isMobile) setSidebarOpen(false)
                  }}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setActiveSessionId(session.id)
                      setActiveSources([])
                      setSelectedSource(null)
                      if (isMobile) setSidebarOpen(false)
                    }
                  }}
                  className={cn(
                    'group cursor-pointer rounded-2xl p-4 transition-all duration-200',
                    isActive
                      ? (isMobile
                        ? 'bg-[#172437] ring-1 ring-[color:var(--ui-accent)]/25'
                        : 'bg-[color:var(--ui-surface-container-low)] ring-1 ring-[color:var(--ui-accent)]/25')
                      : (isMobile
                        ? 'bg-transparent hover:bg-[#152236]'
                        : 'bg-transparent hover:bg-[color:var(--ui-surface-container-low)]/60'),
                  )}
                >
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <span className={cn(
                      'rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide',
                      isActive
                        ? 'bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]'
                        : (isMobile ? 'bg-[#1a2538] text-[color:var(--ui-text-meta)]' : 'bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-meta)]'),
                    )}
                    >
                      {status}
                    </span>
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-[color:var(--ui-text-meta)]">{formatSessionAge(session.createdAt)}</span>
                      <button
                        onClick={event => {
                          event.stopPropagation()
                          deleteSession(session.id)
                        }}
                        className="opacity-0 text-[color:var(--ui-text-meta)] transition-colors group-hover:opacity-100 hover:text-rose-300"
                        title="Excluir conversa"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <h3 className={cn(
                    'line-clamp-2 text-sm font-bold leading-tight',
                    isActive ? 'text-[color:var(--ui-text)]' : 'text-[color:var(--ui-text-dim)] group-hover:text-[color:var(--ui-text)]',
                  )}
                  >
                    {session.title}
                  </h3>
                  <p className="mt-1 line-clamp-2 text-xs text-[color:var(--ui-text-meta)]">
                    {getSessionPreview(session)}
                  </p>
                  <div className="mt-3 flex items-center gap-2 text-[10px] text-[color:var(--ui-text-meta)]">
                    <span className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      isRunning ? 'animate-pulse bg-amber-300' : 'bg-[color:var(--ui-accent)]/55',
                    )}
                    />
                    {messageCount} mensagem{messageCount !== 1 ? 'ens' : ''}
                  </div>
                </div>
              )
            })}
            {visibleSessions.length === 0 && (
              <div className={cn(
                'rounded-2xl p-4 text-xs text-[color:var(--ui-text-meta)]',
                isMobile ? 'bg-[#152236]' : 'bg-[color:var(--ui-surface-container-low)]',
              )}>
                Nenhuma conversa encontrada para este filtro.
              </div>
            )}
          </div>
          <div className="border-t border-[color:var(--ui-border-soft)] px-6 py-3 text-[11px] text-[color:var(--ui-text-meta)]">
            <Clock className="mr-1.5 inline h-3 w-3" />
            Salvo localmente
          </div>
        </aside>
        </>
      )}

      {/* ── Área principal ────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-transparent">
        {/* Header */}
        <div className={cn(
          'flex items-center gap-3 border-b border-[color:var(--ui-border-soft)] bg-transparent',
          isMobile ? 'h-14 px-3' : 'h-16 px-6',
        )}>
          <button
            onClick={() => setSidebarOpen(v => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-[color:var(--ui-text-meta)] transition-colors hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]"
            title="Conversas"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className={cn(
            'shrink-0 items-center justify-center rounded-md bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
            isMobile ? 'hidden' : 'flex h-8 w-8',
          )}>
            <FileText className="h-4 w-4" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-bold text-[color:var(--ui-text)]">
              {activeSession?.title ?? 'Nova conversa'}
            </p>
            <div className={cn('items-center gap-2', isMobile ? 'hidden' : 'flex')}>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-300" />
              <p className="truncate text-[10px] font-medium text-[color:var(--ui-text-meta)]">
                DocOps Agent processando contexto
              </p>
            </div>
          </div>
          {isMobile ? (
            <button
              type="button"
              onClick={() => {
                createNewSession()
                setSidebarOpen(false)
              }}
              className="inline-flex h-8 items-center justify-center gap-1 rounded-lg bg-[color:var(--ui-accent)] px-2.5 text-[11px] font-semibold text-[color:var(--ui-bg)] shadow-[0_14px_34px_-18px_rgba(59,130,246,0.68)]"
              title="Criar nova conversa"
              aria-label="Criar nova conversa"
            >
              <Plus className="h-3.5 w-3.5" />
              Nova
            </button>
          ) : null}
          {!isMobile && messages.length > 0 && (
            <Badge
              variant="secondary"
              className="border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[10px] text-[color:var(--ui-text-dim)]"
            >
              {messages.filter(m => !m.streaming).length} msgs
            </Badge>
          )}
          {hasSources ? (
            <button
              type="button"
              onClick={() => setMobileSourcesOpen(true)}
              className={cn(
                'inline-flex items-center justify-center rounded-lg text-[color:var(--ui-text-meta)] transition-colors hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]',
                isMobile ? 'h-8 w-8' : 'h-8 w-8',
              )}
              title="Fontes citadas"
            >
              <FileText className="h-4 w-4" />
            </button>
          ) : null}
          {!isMobile ? (
            <button className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[color:var(--ui-text-meta)] transition-colors hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]">
              <MoreHorizontal className="h-4 w-4" />
            </button>
          ) : null}
        </div>
        {isPersonalizationEnabled && !isMobile && (
          <div className="border-b border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-container-lowest)] px-6 py-2.5">
            <div className="flex items-start gap-2 rounded-xl bg-[color:var(--ui-surface-container-low)] px-3 py-2 text-xs text-[color:var(--ui-text-meta)]">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--ui-accent)]" />
            <div className="min-w-0">
              <p className="font-medium text-[color:var(--ui-text)]">Memoria ativa</p>
              <p>{personalizationBannerText}</p>
            </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className={cn(
          'flex-1 overflow-y-auto',
          isMobile ? 'px-3 pt-5' : 'px-4 py-6 sm:px-6 sm:py-8',
        )}
        style={isMobile ? { paddingBottom: `${156 + mobileViewportInset}px` } : undefined}>
          <div className="flex w-full flex-col gap-8">
            <ChatProactiveStartersPanel
              recommendations={proactiveRecommendations}
              featureEnabled={isProactiveCopilotEnabled}
              capabilityUnlocked={isProactiveCopilotUnlocked}
              loading={proactiveRecommendationsQuery.isLoading}
              actionPending={proactiveRecommendationActionMutation.isPending}
              entitlementTier={capabilities.entitlementTier}
              onRefreshAccess={() => { void handleRefreshProactiveAccess() }}
              onUpgradeIntent={() => {
                handleProactiveUpgradeIntent('chat.proactive_starters', 'link')
                window.location.href = '/settings'
              }}
              onExecute={handleExecuteRecommendation}
              onUseInChat={handleUseRecommendationInChat}
              onRecordAction={handleRecordRecommendationAction}
              compact={isMobile}
            />

            {messages.length === 0 && (
              <>
                {isMobile ? (
                  <div className="mx-auto mt-[15vh] flex max-w-[16rem] flex-col items-center text-center">
                    <h3 className="font-headline text-[2rem] font-semibold leading-tight text-[color:var(--ui-text)]">
                      No que você está pensando hoje?
                    </h3>
                  </div>
                ) : (
                  <div className="mx-auto flex max-w-md flex-col items-center text-center">
                    <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-[color:var(--ui-surface-container-low)]">
                      <Bot className="h-6 w-6 text-[color:var(--ui-text-meta)]" />
                    </div>
                    <h3 className="font-headline text-xl font-bold text-[color:var(--ui-text)]">Qual o proximo objetivo?</h3>
                    <p className="mt-2 text-sm text-[color:var(--ui-text-meta)]">
                      Pergunte sobre os seus documentos, crie artefatos, agenda ou tarefas sem sair do chat.
                    </p>
                  </div>
                )}
              </>
            )}

          {messages.map((msg, i) => {
            const previousUserPrompt = [...messages.slice(0, i)]
              .reverse()
              .find(item => item.role === 'user')
              ?.content ?? msg.prompt_hint ?? ''
            const turnRef = `${activeSessionId}:${i}`
            const shouldOfferArtifactCta = shouldOfferChatArtifactCTA({
              ...msg,
              prompt_hint: previousUserPrompt,
            })
            const canSaveAsArtifact = isChatToArtifactUnlocked && shouldOfferArtifactCta
            const showArtifactUnlockCta = isChatToArtifactLocked && shouldOfferArtifactCta

            return (
              <MessageBubble
                key={i}
                message={{ ...msg, prompt_hint: previousUserPrompt }}
                canSaveAsArtifact={canSaveAsArtifact}
                showArtifactUnlockCta={showArtifactUnlockCta}
                artifactEntitlementTier={capabilities.entitlementTier}
                savingAsArtifact={savingArtifactTurnRef === turnRef}
                onSaveAsArtifact={() => {
                  if (!canSaveAsArtifact || saveChatArtifactMut.isPending) return
                  setSavingArtifactTurnRef(turnRef)
                  saveChatArtifactMut.mutate({
                    turnRef,
                    message: { ...msg, prompt_hint: previousUserPrompt },
                    userPrompt: previousUserPrompt,
                    sessionId: activeSessionId,
                  })
                }}
                onRefreshArtifactAccess={() => { void handleRefreshPremiumAccess() }}
                onUpgradeIntent={() => {
                  handleUpgradeIntent('chat.chat_to_artifact_cta', 'link')
                  window.location.href = '/settings'
                }}
                onSourceClick={sources => {
                  setActiveSources(sources)
                  setSelectedSource(null)
                }}
                onCitationClick={(source, sources) => {
                  setActiveSources(sources)
                  setSelectedSource(source)
                }}
              />
            )
          })}

          {pendingFlashcardCommand && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
                <Bot className="h-4 w-4" />
              </div>
              <div className="max-w-[88%] space-y-2">
                <ActionSummaryCard
                  action={{
                    kind: 'flashcards_batch',
                    title: pendingFlashcardCommand.docs.length > 0
                      ? 'Confirme o comando de flashcards'
                      : 'Preciso do escopo dos flashcards',
                    summary: pendingFlashcardCommand.summary,
                    status: 'needs_confirmation',
                    scope: pendingFlashcardCommand.scopeLabel,
                    doc_names: pendingFlashcardCommand.docs.map(doc => doc.file_name),
                    doc_count: pendingFlashcardCommand.docs.length,
                    card_count: pendingFlashcardCommand.numCards,
                    difficulty: pendingFlashcardCommand.difficultyCustom,
                    next_steps: pendingFlashcardCommand.docs.length > 0
                      ? [
                          'Confirmar para gerar um deck por documento.',
                          'Cancelar para editar o pedido.',
                        ]
                      : [
                          'Selecione documentos na area de opcoes ou diga "todos os documentos".',
                        ],
                    links: pendingFlashcardCommand.docs.length > 0
                      ? [{ label: 'Abrir Flashcards', href: '/flashcards' }]
                      : [
                          { label: 'Ver Documentos', href: '/docs' },
                          { label: 'Abrir Flashcards', href: '/flashcards' },
                        ],
                  }}
                  confirmLabel={pendingFlashcardCommand.docs.length > 0 ? 'Confirmar e gerar' : 'Selecionar Documento'}
                  cancelLabel="Descartar"
                  onConfirm={confirmFlashcardCommand}
                  onCancel={cancelFlashcardCommand}
                />
              </div>
            </div>
          )}

          {flashcardBatchMut.isPending && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
                <Bot className="h-4 w-4" />
              </div>
              <div className="rounded-xl bg-[color:var(--ui-surface-container-low)] px-4 py-3 text-xs text-[color:var(--ui-text-dim)]">
                Gerando flashcards em lote...
              </div>
            </div>
          )}

          {isPending && !isStreaming && !flashcardBatchMut.isPending && <TypingIndicator />}

            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input area */}
        <div className={cn(
          'relative border-t border-[color:var(--ui-border-soft)]',
          isMobile
            ? 'absolute inset-x-0 z-20 bg-transparent px-3 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2'
            : 'px-4 pb-4 pt-3 sm:px-6 sm:pb-5',
        )}
        style={isMobile ? { bottom: `${Math.max(6, mobileViewportInset)}px` } : undefined}>
          <div className="w-full">
            <div data-tour-id="chat-composer" className={cn(
              'border border-[color:var(--ui-border-soft)] backdrop-blur',
              isMobile
                ? 'rounded-[1.6rem] bg-[linear-gradient(135deg,rgba(12,17,24,0.94)_0%,rgba(16,22,31,0.9)_65%,rgba(20,28,39,0.86)_100%)] p-1.5 shadow-[0_16px_34px_rgba(0,0,0,0.38)]'
                : 'rounded-2xl bg-[color:var(--ui-surface-container-low)]/85 p-2 shadow-[0_18px_40px_rgba(0,0,0,0.28)]',
            )}>

          {attachmentMenuOpen && (
            <>
              <button
                type="button"
                className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[1px]"
                onClick={() => setAttachmentMenuOpen(false)}
                aria-label="Fechar menu de anexo"
              />
              <div className="absolute bottom-full left-0 z-40 mb-2 w-[min(16.5rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-[#2f3136] shadow-[0_22px_48px_rgba(0,0,0,0.58)]">
                <button
                  type="button"
                  onClick={() => {
                    setAttachmentMenuOpen(false)
                    setDocPickerOpen(true)
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-[#f1f3f5] transition-colors hover:bg-[#3a3d43]"
                >
                  <Paperclip className="h-4 w-4 text-[#d5d8de]" />
                  <span className="flex-1 font-medium">Adicionar documento</span>
                  <ChevronRight className="h-4 w-4 text-[#aab0bb]" />
                </button>
                {isPersonalizationUnlocked && (
                  <button
                    type="button"
                    onClick={() => {
                      setAttachmentMenuOpen(false)
                      setTreatmentPickerOpen(true)
                    }}
                    className="flex w-full items-center gap-3 border-t border-white/10 px-4 py-3 text-left text-sm text-[#f1f3f5] transition-colors hover:bg-[#3a3d43]"
                  >
                    <Sparkles className="h-4 w-4 text-[#d5d8de]" />
                    <span className="flex-1 font-medium">Escolher tratamento</span>
                    <ChevronRight className="h-4 w-4 text-[#aab0bb]" />
                  </button>
                )}
              </div>
            </>
          )}

          {docPickerOpen && (
            <>
              <button
                type="button"
                className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[1px]"
                onClick={() => setDocPickerOpen(false)}
                aria-label="Fechar seletor de documentos"
              />
              <div className="absolute bottom-full left-0 z-40 mb-2 w-[min(21rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-[#2f3136] shadow-[0_22px_52px_rgba(0,0,0,0.62)]">
                <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#3a3d43] text-[#d5d8de]">
                    <FileText className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-[#f1f3f5]">Selecionar documento</p>
                    <p className="text-[11px] text-[#aab0bb]">{(docs ?? []).length} arquivo(s) disponíveis</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDocPickerOpen(false)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#aab0bb] transition-colors hover:bg-[#3a3d43] hover:text-[#f1f3f5]"
                    title="Fechar"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className={cn('overflow-y-auto', isMobile ? 'max-h-[34svh]' : 'max-h-72')}>
                  {!docs || docs.length === 0 ? (
                    <div className="px-4 py-5 text-sm text-[#aab0bb]">
                      Nenhum arquivo indexado ainda. Envie documentos em <b>Inserção</b>.
                    </div>
                  ) : (
                    <div className="divide-y divide-white/10">
                      {docs.map(doc => {
                        const alreadySelected = selectedDocs.some(item => item.doc_id === doc.doc_id)
                        return (
                          <button
                            key={doc.doc_id}
                            type="button"
                            onClick={() => addDocToActiveContext(doc)}
                            disabled={alreadySelected || isComposerBlocked}
                            className={cn(
                              'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
                              alreadySelected ? 'cursor-default bg-[#3a3d43]/75' : 'hover:bg-[#3a3d43]/75',
                              isComposerBlocked && !alreadySelected && 'opacity-50',
                            )}
                          >
                            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#3a3d43] text-[#c7ccd5]">
                              <FileText className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1 truncate text-sm text-[#f1f3f5]">{doc.file_name}</span>
                            {alreadySelected && (
                              <span className="rounded-full border border-[#7aa8ff55] bg-[#7aa8ff1f] px-2 py-0.5 text-[10px] font-medium text-[#b9d2ff]">
                                Adicionado
                              </span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div data-tour-id="chat-grounding" className="border-t border-white/10 px-4 py-3">
                  <label className="flex cursor-pointer items-center gap-2 text-xs text-[#c0c6d0]">
                    <input
                      type="checkbox"
                      checked={strictGrounding}
                      onChange={e => setStrictGrounding(e.target.checked)}
                      disabled={isComposerBlocked || !isStrictGroundingEnabled}
                      className="accent-[color:var(--ui-accent)]"
                    />
                    Modo strict grounding (respostas so com evidencia forte)
                  </label>
                </div>
              </div>
            </>
          )}

          {treatmentPickerOpen && isPersonalizationUnlocked && (
            <>
              <button
                type="button"
                className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[1px]"
                onClick={() => setTreatmentPickerOpen(false)}
                aria-label="Fechar seletor de tratamento"
              />
              <div className="absolute bottom-full left-0 z-40 mb-2 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-[#2f3136] shadow-[0_22px_52px_rgba(0,0,0,0.62)]">
                <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#3a3d43] text-[#d5d8de]">
                    <Sparkles className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-[#f1f3f5]">Escolher tratamento</p>
                    <p className="text-[11px] text-[#aab0bb]">Override so para a proxima mensagem</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTreatmentPickerOpen(false)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#aab0bb] transition-colors hover:bg-[#3a3d43] hover:text-[#f1f3f5]"
                    title="Fechar"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className={cn('space-y-3 overflow-y-auto px-4 py-4', isMobile ? 'max-h-[40svh]' : 'max-h-80')}>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-[#c0c6d0]">
                      {composerHasOverrides ? 'Overrides ativos para esta mensagem.' : 'Use os controles abaixo para ajustar a resposta.'}
                    </p>
                    <button
                      type="button"
                      onClick={() => setComposerOverrides(emptyComposerOverrides())}
                      disabled={flashcardBatchMut.isPending || !composerHasOverrides}
                      className="text-[11px] text-[#aab0bb] transition-colors hover:text-[#f1f3f5] disabled:opacity-50"
                    >
                      Limpar
                    </button>
                  </div>

                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-[#aab0bb]">Profundidade</span>
                      {DEPTH_OPTIONS.map(option => {
                        const active = (composerOverrides.default_depth ?? userPreferences.default_depth) === option.value
                        const overridden = composerOverrides.default_depth === option.value
                        return (
                          <button
                            key={`depth-${option.value}`}
                            type="button"
                            disabled={flashcardBatchMut.isPending}
                            onClick={() => setComposerOverrides(prev => ({
                              ...prev,
                              default_depth: prev.default_depth === option.value ? null : option.value,
                            }))}
                            className={cn(
                              'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                              active ? 'border-[color:var(--ui-accent)]/45 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]' : 'border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-meta)]',
                              overridden && 'ring-1 ring-[color:var(--ui-accent)]/45',
                            )}
                          >
                            {DEPTH_LABELS[option.value]}
                          </button>
                        )
                      })}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-[#aab0bb]">Tom</span>
                      {TONE_OPTIONS.map(option => {
                        const active = (composerOverrides.tone ?? userPreferences.tone) === option.value
                        const overridden = composerOverrides.tone === option.value
                        return (
                          <button
                            key={`tone-${option.value}`}
                            type="button"
                            disabled={flashcardBatchMut.isPending}
                            onClick={() => setComposerOverrides(prev => ({
                              ...prev,
                              tone: prev.tone === option.value ? null : option.value,
                            }))}
                            className={cn(
                              'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                              active ? 'border-[color:var(--ui-accent)]/45 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]' : 'border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-meta)]',
                              overridden && 'ring-1 ring-[color:var(--ui-accent)]/45',
                            )}
                          >
                            {TONE_LABELS[option.value]}
                          </button>
                        )
                      })}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-[#aab0bb]">Rigor</span>
                      {STRICTNESS_OPTIONS.map(option => {
                        const active = (composerOverrides.strictness_preference ?? userPreferences.strictness_preference) === option.value
                        const overridden = composerOverrides.strictness_preference === option.value
                        return (
                          <button
                            key={`strictness-${option.value}`}
                            type="button"
                            disabled={flashcardBatchMut.isPending}
                            onClick={() => setComposerOverrides(prev => ({
                              ...prev,
                              strictness_preference: prev.strictness_preference === option.value ? null : option.value,
                            }))}
                            className={cn(
                              'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                              active ? 'border-[color:var(--ui-accent)]/45 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]' : 'border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-meta)]',
                              overridden && 'ring-1 ring-[color:var(--ui-accent)]/45',
                            )}
                          >
                            {STRICTNESS_LABELS[option.value]}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {selectedDocs.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {selectedDocs.map(doc => (
                <span
                  key={doc.doc_id}
                  className="inline-flex items-center gap-1 rounded-full border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] px-2 py-0.5 text-[11px] text-[color:var(--ui-text-dim)]"
                >
                  <FileText className="h-3 w-3 text-[color:var(--ui-text-meta)]" />
                  <span className="max-w-[11rem] truncate">{doc.file_name}</span>
                  <button
                    type="button"
                    onClick={() => removeDocFromActiveContext(doc.doc_id)}
                    className="text-[color:var(--ui-text-meta)] transition-colors hover:text-rose-300"
                    title="Remover arquivo"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div
            className={cn(
              'flex gap-2',
              isMobile
                ? 'items-end rounded-[1.15rem] border border-[color:var(--ui-border-soft)]/85 bg-[color:var(--ui-surface-container-lowest)]/90 px-1.5 py-1'
                : 'items-center',
            )}
          >
            <button
              data-tour-id="chat-attachment"
              type="button"
              onClick={() => {
                setDocPickerOpen(false)
                setTreatmentPickerOpen(false)
                setAttachmentMenuOpen(v => !v)
              }}
              className={cn(
                'inline-flex shrink-0 items-center justify-center rounded-full text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text)]',
                isMobile
                  ? 'h-8 w-8 border border-transparent hover:bg-[color:var(--ui-surface-2)]'
                  : 'h-7 w-7 rounded-lg hover:bg-[color:var(--ui-surface-2)]',
                (attachmentMenuOpen || docPickerOpen || treatmentPickerOpen || composerHasOverrides) && 'bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
              )}
              title="Documentos e tratamento"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </button>
            <textarea
              ref={composerTextareaRef}
              placeholder="Pergunte ao agente..."
              value={input}
              rows={1}
              onChange={event => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isComposerBlocked}
              className={cn(
                'flex-1 resize-none overflow-y-hidden text-sm text-[color:var(--ui-text)] outline-none transition-colors placeholder:text-[color:var(--ui-text-meta)]',
                isMobile
                  ? 'min-h-[34px] rounded-xl border-0 bg-transparent px-1.5 py-1.5 text-[13px] leading-5 focus:ring-0'
                  : 'min-h-[44px] rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-container-lowest)] px-3 py-2 focus:border-[color:var(--ui-accent)] focus:ring-2 focus:ring-[color:var(--ui-accent)]/20',
              )}
            />
            <Button
              onClick={isChatRequestActive ? pauseCurrentGeneration : handleSend}
              disabled={!isChatRequestActive && (!input.trim() || isComposerBlocked)}
              size="icon"
              className={cn(
                isMobile
                  ? 'h-9 w-9 rounded-full border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-accent-soft)] hover:text-[color:var(--ui-accent)]'
                  : 'h-11 w-11 rounded-xl bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]',
              )}
              title={isChatRequestActive ? 'Pausar geracao' : 'Enviar mensagem'}
            >
              {isChatRequestActive ? (
                <Pause className="h-4 w-4" />
              ) : flashcardBatchMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Painel de fontes — desktop ────────────────── */}
      {hasSources && !isMobile && (
        <aside className="flex w-80 shrink-0 flex-col border-l border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface)]/96">
          <div className="flex items-center gap-2 border-b border-[color:var(--ui-border-soft)] px-5 py-4">
            <FileText className="h-4 w-4 text-[color:var(--ui-accent)]" />
            <p className="text-sm font-semibold text-[color:var(--ui-text)]">Fontes citadas</p>
            <Badge
              variant="secondary"
              className="ml-auto border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[10px] text-[color:var(--ui-text-dim)]"
            >
              {activeSources.length}
            </Badge>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <SourcePanel
              sources={activeSources}
              selected={selectedSource}
              onSelect={source => setSelectedSource(prev => prev?.fonte_n === source.fonte_n ? null : source)}
            />
          </div>
        </aside>
      )}

      {/* ── Painel de fontes — mobile bottom sheet ────────────────── */}
      {hasSources && isMobile && mobileSourcesOpen && (
        <>
          <button
            type="button"
            className="absolute inset-0 z-40 bg-black/45"
            onClick={() => setMobileSourcesOpen(false)}
            aria-label="Fechar painel de fontes"
          />
          <aside className="absolute inset-x-0 bottom-0 z-50 max-h-[70dvh] rounded-t-3xl border-t border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface)]">
            <div className="flex items-center gap-2 border-b border-[color:var(--ui-border-soft)] px-4 py-3">
              <FileText className="h-4 w-4 text-[color:var(--ui-accent)]" />
              <p className="text-sm font-semibold text-[color:var(--ui-text)]">Fontes citadas</p>
              <Badge
                variant="secondary"
                className="ml-auto border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)] text-[10px] text-[color:var(--ui-text-dim)]"
              >
                {activeSources.length}
              </Badge>
              <button
                type="button"
                onClick={() => setMobileSourcesOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[color:var(--ui-text-meta)] hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]"
                title="Fechar fontes"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="overflow-y-auto px-4 py-4" style={{ maxHeight: 'calc(70dvh - 3.5rem)' }}>
              <SourcePanel
                sources={activeSources}
                selected={selectedSource}
                onSelect={source => setSelectedSource(prev => prev?.fonte_n === source.fonte_n ? null : source)}
              />
            </div>
          </aside>
        </>
      )}

    </div>
    </>
  )
}


