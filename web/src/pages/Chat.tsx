import { useState, useRef, useEffect } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import {
  Send, Bot, User, FileText, ChevronRight, Loader2, X,
  Plus, MessageSquare, Clock, CalendarCheck, Trash2,
  SlidersHorizontal, ChevronDown,
} from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  apiClient,
  type ChatResponse,
  type ChatQualitySignal,
  type SourceItem,
  type DocItem,
  type FlashcardDeck,
} from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  content: string
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
  sessionId: string
  docIds: string[]
  strictGrounding: boolean
  history: Array<{ role: 'user' | 'assistant'; content: string }>
  activeContext: ChatActiveContext
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

function normalizeForMatch(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[_-]+/g, ' ')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

function formatDifficultyMix(mix: FlashcardDifficultyMix) {
  return `${mix.facil} faceis, ${mix.media} medias e ${mix.dificil} dificeis`
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
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-700">
        <Bot className="h-4 w-4 text-zinc-300" />
      </div>
      <div className="flex items-center rounded-2xl rounded-tl-sm bg-zinc-800 px-4 py-3">
        <span className="flex gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-bounce [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-bounce [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-bounce [animation-delay:300ms]" />
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
            'w-full rounded-lg border p-3 text-left transition-colors',
            selected?.fonte_n === src.fonte_n
              ? 'border-blue-600 bg-blue-600/10'
              : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700'
          )}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold text-blue-400">[Fonte {src.fonte_n}]</span>
            <span className="text-xs text-zinc-400 truncate">{src.file_name}</span>
          </div>
          {src.page !== 'N/A' && (
            <span className="text-xs text-zinc-500">p. {src.page}</span>
          )}
          {selected?.fonte_n === src.fonte_n && (
            <p className="mt-2 text-xs text-zinc-300 line-clamp-4">{src.snippet}</p>
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
        : 'border-amber-800/50 bg-amber-950/20 text-amber-100'

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
  high: 'border-emerald-700/40 bg-emerald-600/10 text-emerald-200',
  medium: 'border-amber-700/40 bg-amber-600/10 text-amber-100',
  low: 'border-red-700/40 bg-red-600/10 text-red-100',
}

function QualitySignalCard({ signal }: { signal: ChatQualitySignal }) {
  const scorePct = Math.round(Math.max(0, Math.min(1, signal.score)) * 100)
  return (
    <div
      data-testid="chat-quality-signal"
      className={cn(
        'rounded-xl border px-3 py-2 text-[11px] leading-5',
        QUALITY_TONE_CLASS[signal.level],
      )}
    >
      <p className="font-semibold">
        Confiabilidade: {signal.label} ({scorePct}%)
      </p>
      {signal.suggested_action && (
        <p className="mt-1 text-[11px] opacity-95">{signal.suggested_action}</p>
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
          ? 'border-amber-700/40 bg-amber-700/10 text-amber-100'
          : 'border-blue-700/40 bg-blue-600/10 text-blue-100',
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
  message, onSourceClick, onCitationClick,
}: {
  message: Message
  onSourceClick?: (sources: SourceItem[]) => void
  onCitationClick?: (source: SourceItem, allSources: SourceItem[]) => void
}) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-blue-600' : 'bg-zinc-700'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-white" />
        ) : (
          <Bot className="h-4 w-4 text-zinc-300" />
        )}
      </div>

      <div className={cn('max-w-[75%] space-y-2', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'select-text rounded-2xl px-4 py-3 text-sm transition-all duration-200 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.08)]',
            isUser
              ? 'rounded-tr-sm bg-blue-600 text-white hover:bg-blue-500 selection:bg-sky-200 selection:text-zinc-950'
              : 'rounded-tl-sm bg-zinc-800 text-zinc-100 hover:bg-zinc-700 selection:bg-amber-200 selection:text-zinc-950'
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
            <div className="prose prose-invert prose-sm max-w-none select-text selection:bg-amber-200 selection:text-zinc-950" style={{ userSelect: 'text', WebkitUserSelect: 'text' }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {message.streaming && (
                <span className="ml-1 inline-flex h-[1.05em] w-[2px] animate-pulse rounded-full bg-blue-300/80 align-[-0.15em] shadow-[0_0_10px_rgba(96,165,250,0.55)]" />
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

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="space-y-2">
            <button
              onClick={() => onSourceClick?.(message.sources!)}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-blue-400 transition-colors"
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
                  className="rounded-full border border-blue-600/40 bg-blue-600/10 px-2 py-0.5 text-[11px] text-blue-300 hover:bg-blue-600/20"
                >
                  [Fonte {src.fonte_n}]
                </button>
              ))}
            </div>
          </div>
        )}

        {!isUser && (message.intent || message.action_metadata?.kind) && (
          <Badge variant="secondary" className="text-xs">
            {INTENT_LABELS[message.intent ?? message.action_metadata?.kind ?? ''] ?? 'Ação'}
          </Badge>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────

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
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])
  const [strictGrounding, setStrictGrounding] = useState(false)
  const [activeSources, setActiveSources] = useState<SourceItem[]>([])
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [pendingFlashcardCommand, setPendingFlashcardCommand] = useState<FlashcardCommandPlan | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const streamAbortRef = useRef<AbortController | null>(null)

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? sessions[0]
  const messages = activeSession?.messages ?? EMPTY_MESSAGES
  const activeContext = activeSession?.activeContext ?? emptyActiveContext()
  const isStreamingEnabled = capabilities.isEnabled('chat_streaming_enabled')
  const isStrictGroundingEnabled = capabilities.isEnabled('strict_grounding_enabled')

  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  useEffect(() => {
    setPendingFlashcardCommand(null)
  }, [activeSessionId])

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

  function appendStreamingAssistantPlaceholder(sessionId: string) {
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
                streaming: true,
                stream_stage: 'analyzing',
                stream_status_text: STREAM_STAGE_DETAIL_DEFAULT.analyzing,
                stream_interrupted: false,
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

  function finalizeStreamingAssistantMessage(sessionId: string, data: ChatResponse) {
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId || s.messages.length === 0) return s
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (!last || last.role !== 'assistant') return s
        msgs[msgs.length - 1] = {
          ...last,
          content: data.answer ?? last.content ?? '',
          streaming: false,
          stream_stage: null,
          stream_status_text: null,
          stream_interrupted: false,
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
      appendStreamingAssistantPlaceholder(payload.sessionId)

      if (streamAbortRef.current) {
        streamAbortRef.current.abort()
      }
      const controller = new AbortController()
      streamAbortRef.current = controller

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
        markStreamingInterruption(
          payload.sessionId,
          'Conexao instavel no streaming. Continuando em modo padrao.',
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
          markStreamingInterruption(
            payload.sessionId,
            'Nao consegui recuperar automaticamente. Reenvie a pergunta para tentar de novo.',
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
      finalizeStreamingAssistantMessage(variables.sessionId, data)
      updateSessionActiveContext(variables.sessionId, normalizeActiveContext(data.active_context))

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
      const errorText = err?.response?.data?.detail ?? err?.message ?? 'Erro ao consultar o agente'
      toast.error(errorText)
      failStreamingAssistantMessage(
        variables.sessionId,
        'Nao consegui concluir esta resposta agora. Verifique sua conexao e clique em enviar novamente.',
      )
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
      // Open filters panel so user can select a document right here
      setFiltersOpen(true)
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

    mutation.mutate({
      message: text,
      sessionId: targetSession?.id ?? activeSessionId,
      docIds: selectedDocs.map(doc => doc.doc_id),
      strictGrounding,
      history: recentHistory,
      activeContext: targetSession?.activeContext ?? emptyActiveContext(),
    })
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

  const hasSources = activeSources.length > 0
  const isStreaming = messages.some(m => m.streaming)
  const isPending = mutation.isPending || flashcardBatchMut.isPending
  const contextLabels = [
    ...activeContext.active_doc_names.slice(0, 2).map(name => ({ key: `doc-${name}`, label: name, tone: 'doc' as const })),
    activeContext.active_deck_title ? { key: `deck-${activeContext.active_deck_title}`, label: `Deck: ${activeContext.active_deck_title}`, tone: 'deck' as const } : null,
    activeContext.active_task_title ? { key: `task-${activeContext.active_task_title}`, label: `Tarefa: ${activeContext.active_task_title}`, tone: 'task' as const } : null,
    activeContext.active_note_title ? { key: `note-${activeContext.active_note_title}`, label: `Nota: ${activeContext.active_note_title}`, tone: 'note' as const } : null,
  ].filter(Boolean) as Array<{ key: string; label: string; tone: 'doc' | 'deck' | 'task' | 'note' }>
  const hasActiveContext = contextLabels.length > 0 || !!activeContext.last_action

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-0 overflow-hidden rounded-2xl border app-divider bg-[color:var(--ui-bg-alt)] shadow-[0_16px_36px_rgba(2,4,8,0.3)]">
      {/* ── Sidebar de sessões ────────────────────────────────────────────── */}
      {sidebarOpen && (
        <div className="flex w-56 shrink-0 flex-col border-r app-divider bg-[color:var(--ui-bg)]">
          <div className="flex items-center justify-between border-b app-divider px-3 py-3">
            <span className="text-xs font-semibold text-zinc-400">Conversas</span>
            <button
              onClick={createNewSession}
              className="flex h-6 w-6 items-center justify-center rounded-md border border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
              title="Nova conversa"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
            {sessions.map(s => (
              <div
                key={s.id}
                className={cn(
                  'group flex items-center gap-2 rounded-lg px-2 py-2 cursor-pointer transition-colors',
                  s.id === activeSessionId
                    ? 'bg-zinc-800 text-zinc-100'
                    : 'text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300'
                )}
                onClick={() => {
                  setActiveSessionId(s.id)
                  setActiveSources([])
                  setSelectedSource(null)
                }}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="flex-1 truncate text-xs">{s.title}</span>
                <button
                  onClick={e => { e.stopPropagation(); deleteSession(s.id) }}
                  className="shrink-0 opacity-0 text-zinc-600 hover:text-red-400 group-hover:opacity-100 transition-opacity"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
          <div className="border-t app-divider px-3 py-2">
            <p className="text-[10px] text-zinc-600">
              <Clock className="mr-1 inline h-3 w-3" />
              Salvo localmente
            </p>
          </div>
        </div>
      )}

      {/* ── Área principal ────────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 border-b app-divider bg-[color:var(--ui-bg)] px-4 py-3">
          <button
            onClick={() => setSidebarOpen(v => !v)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
          >
            <MessageSquare className="h-4 w-4" />
          </button>
          <Bot className="h-5 w-5 text-blue-400" />
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-semibold text-zinc-100">
              {activeSession?.title ?? 'DocOps Chat'}
            </p>
            <p className="text-xs text-zinc-500">RAG com Gemini + Chroma</p>
          </div>
          {messages.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {messages.filter(m => !m.streaming).length} msgs
            </Badge>
          )}
        </div>

        {hasActiveContext && (
          <div className="flex flex-wrap items-center gap-2 border-b app-divider bg-[color:var(--ui-bg)] px-4 py-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-zinc-500">
              Contexto ativo
            </span>
            {contextLabels.map(item => (
              <span
                key={item.key}
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px]',
                  item.tone === 'doc' && 'border-blue-900 bg-blue-950/50 text-blue-200',
                  item.tone === 'deck' && 'border-amber-900 bg-amber-950/50 text-amber-200',
                  item.tone === 'task' && 'border-emerald-900 bg-emerald-950/50 text-emerald-200',
                  item.tone === 'note' && 'border-fuchsia-900 bg-fuchsia-950/50 text-fuchsia-200',
                )}
              >
                {item.label}
              </span>
            ))}
            {activeContext.last_action && (
              <span className="text-xs text-zinc-500">
                ultima acao: {activeContext.last_action}
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                updateActiveContext(emptyActiveContext())
                setSelectedDocs([])
              }}
              className="ml-auto text-xs text-zinc-500 transition-colors hover:text-zinc-200"
            >
              Limpar contexto
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto bg-[color:var(--ui-bg-alt)] px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <Bot className="h-12 w-12 text-zinc-700" />
              <p className="text-sm font-medium text-zinc-400">Olá! Como posso ajudar?</p>
              <p className="text-xs text-zinc-600 max-w-xs">
                Faça perguntas sobre seus documentos indexados. Ou diga algo como{' '}
                <span className="text-zinc-500">"quero um lembrete às 17h amanhã"</span>{' '}
                para criar eventos no calendário.
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble
              key={i}
              message={msg}
              onSourceClick={sources => {
                setActiveSources(sources)
                setSelectedSource(null)
              }}
              onCitationClick={(source, sources) => {
                setActiveSources(sources)
                setSelectedSource(source)
              }}
            />
          ))}

          {pendingFlashcardCommand && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-700">
                <Bot className="h-4 w-4 text-zinc-300" />
              </div>
              <div className="max-w-[75%] space-y-2">
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
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-700">
                <Bot className="h-4 w-4 text-zinc-300" />
              </div>
              <div className="flex items-center rounded-2xl rounded-tl-sm bg-zinc-800 px-4 py-3 text-xs text-zinc-300">
                Gerando flashcards em lote...
              </div>
            </div>
          )}

          {isPending && !isStreaming && !flashcardBatchMut.isPending && <TypingIndicator />}

          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="border-t app-divider bg-[color:var(--ui-bg)] p-4 space-y-2">
          {/* Filtros colapsáveis */}
          <button
            onClick={() => setFiltersOpen(v => !v)}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <SlidersHorizontal className="h-3 w-3" />
            Opções avançadas
            <ChevronDown className={cn('h-3 w-3 transition-transform', filtersOpen && 'rotate-180')} />
            {(selectedDocs.length > 0 || strictGrounding) && (
              <span className="ml-1 h-1.5 w-1.5 rounded-full bg-blue-500" />
            )}
          </button>

          {filtersOpen && (
            <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="flex gap-2">
                <select
                  value={selectedDoc}
                  onChange={e => setSelectedDoc(e.target.value)}
                  disabled={isPending || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)}
                  className="flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 min-w-0"
                >
                  <option value="">Filtrar por documento (opcional)</option>
                  {(docs ?? [])
                    .filter(doc => !selectedDocs.some(item => item.doc_id === doc.doc_id))
                    .map(doc => (
                      <option key={doc.doc_id} value={doc.doc_id}>
                        {doc.file_name} ({doc.chunk_count} chunks)
                      </option>
                    ))}
                </select>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!selectedDoc || isPending || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)}
                  onClick={() => {
                    const docToAdd = (docs ?? []).find(doc => doc.doc_id === selectedDoc)
                    if (!docToAdd || selectedDocs.some(item => item.doc_id === docToAdd.doc_id)) return
                    const nextDocs = [...selectedDocs, docToAdd]
                    setSelectedDocs(nextDocs)
                    updateActiveContext(normalizeActiveContext({
                      ...activeContext,
                      active_doc_ids: nextDocs.map(doc => doc.doc_id),
                      active_doc_names: nextDocs.map(doc => doc.file_name),
                    }))
                    setSelectedDoc('')
                    // If there's a pending flashcard command with no docs, resolve it with the newly selected doc
                    if (pendingFlashcardCommand && pendingFlashcardCommand.docs.length === 0) {
                      const scopeLabel = `documento selecionado "${docToAdd.file_name}"`
                      setPendingFlashcardCommand({
                        ...pendingFlashcardCommand,
                        docs: [docToAdd],
                        scopeLabel,
                        summary: `Vou gerar ${pendingFlashcardCommand.numCards} flashcards para ${scopeLabel}.`,
                      })
                    }
                  }}
                >
                  Adicionar
                </Button>
              </div>
              {selectedDocs.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedDocs.map(doc => (
                    <span
                      key={doc.doc_id}
                      className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-200"
                    >
                      <FileText className="h-3 w-3 text-zinc-500" />
                      {doc.file_name}
                      <button
                        type="button"
                        onClick={() => {
                          const nextDocs = selectedDocs.filter(item => item.doc_id !== doc.doc_id)
                          setSelectedDocs(nextDocs)
                          updateActiveContext(normalizeActiveContext({
                            ...activeContext,
                            active_doc_ids: nextDocs.map(item => item.doc_id),
                            active_doc_names: nextDocs.map(item => item.file_name),
                          }))
                        }}
                        className="text-zinc-400 hover:text-red-400"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <label className="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">
                <input
                  type="checkbox"
                  checked={strictGrounding}
                  onChange={e => setStrictGrounding(e.target.checked)}
                  disabled={
                    !isStrictGroundingEnabled
                    || isPending
                    || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)
                  }
                  className="accent-blue-600"
                />
                Modo strict grounding (respostas só com evidência forte)
              </label>
              {!isStrictGroundingEnabled && (
                <p className="text-[11px] text-zinc-500">
                  Strict grounding está desativado por configuração do workspace.
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <Input
              placeholder="Faça uma pergunta sobre seus documentos ou crie um lembrete..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isPending || isStreaming || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)}
              className="flex-1 bg-zinc-900 border-zinc-700"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isPending || isStreaming || (!!pendingFlashcardCommand && pendingFlashcardCommand.docs.length > 0)}
              size="icon"
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* ── Painel de fontes — só aparece quando há fontes ────────────────── */}
      {hasSources && (
        <div className="flex w-56 shrink-0 flex-col border-l app-divider bg-[color:var(--ui-bg)]">
          <CardHeader className="border-b app-divider py-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4 text-blue-400" />
              Fontes Citadas
              <Badge variant="secondary" className="ml-auto">
                {activeSources.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <div className="p-3 overflow-y-auto flex-1">
            <SourcePanel
              sources={activeSources}
              selected={selectedSource}
              onSelect={s => setSelectedSource(prev => prev?.fonte_n === s.fonte_n ? null : s)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
