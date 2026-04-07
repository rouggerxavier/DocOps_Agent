import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { apiClient, type ChatResponse, type SourceItem, type DocItem, type FlashcardDeck } from '@/api/client'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
  intent?: string
  calendar_action?: Record<string, any> | null
  action_metadata?: ChatActionMetadata | null
  needs_confirmation?: boolean
  confirmation_text?: string | null
  suggested_reply?: string | null
  streaming?: boolean
}

interface ChatSession {
  id: string
  title: string
  messages: Message[]
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

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatSession[]
    return parsed.map(s => ({ ...s, createdAt: new Date(s.createdAt) }))
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
    messages: [],
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
              ? 'rounded-tr-sm bg-blue-600 text-white hover:bg-blue-500'
              : 'rounded-tl-sm bg-zinc-800 text-zinc-100 hover:bg-zinc-700'
          )}
          style={{ userSelect: 'text', WebkitUserSelect: 'text', cursor: 'text' }}
        >
          {isUser ? (
            <div
              className="select-text whitespace-pre-wrap break-words leading-relaxed"
              style={{ userSelect: 'text', WebkitUserSelect: 'text' }}
            >
              {message.content}
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none select-text" style={{ userSelect: 'text', WebkitUserSelect: 'text' }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {message.streaming && (
                <span className="inline-block h-4 w-0.5 animate-pulse bg-zinc-400 ml-0.5 align-text-bottom" />
              )}
            </div>
          )}
        </div>

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
  const navigate = useNavigate()
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
  const streamTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? sessions[0]
  const messages = activeSession?.messages ?? EMPTY_MESSAGES

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

  function appendAssistantMessage(message: Message) {
    setSessions(prev =>
      prev.map(s =>
        s.id === activeSessionId
          ? { ...s, messages: [...s.messages, message] }
          : s
      )
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

  // Pseudo-streaming: reveals text char by char after response arrives
  const streamMessage = useCallback((
    fullText: string,
    sources: SourceItem[],
    intent: string,
    calendarAction: any,
    actionMetadata: ChatActionMetadata | null,
  ) => {
    const charsPerTick = 6
    const intervalMs = 16
    let pos = 0

    // Add placeholder streaming message
    setSessions(prev =>
      prev.map(s =>
        s.id === activeSessionId
          ? { ...s, messages: [...s.messages, { role: 'assistant', content: '', streaming: true, sources: [], intent, action_metadata: null }] }
          : s
      )
    )

    function tick() {
      pos = Math.min(pos + charsPerTick, fullText.length)
      const chunk = fullText.slice(0, pos)
      const done = pos >= fullText.length

      setSessions(prev =>
        prev.map(s => {
          if (s.id !== activeSessionId) return s
          const msgs = [...s.messages]
          const last = msgs[msgs.length - 1]
          if (!last || last.role !== 'assistant') return s
          msgs[msgs.length - 1] = {
            ...last,
            content: chunk,
            streaming: !done,
            sources: done ? sources : [],
            calendar_action: done ? calendarAction : null,
            action_metadata: done ? actionMetadata : null,
          }
          return { ...s, messages: msgs }
        })
      )

      if (!done) {
        streamTimerRef.current = setTimeout(tick, intervalMs)
      } else {
        if (sources.length > 0) {
          setActiveSources(sources)
          setSelectedSource(null)
        }
      }
    }

    tick()
  }, [activeSessionId])

  const mutation = useMutation({
    mutationFn: (message: string) => {
      // Envia as últimas 6 mensagens como histórico para o backend resolver referências anafóricas
      const recentHistory = (activeSession?.messages ?? [])
        .filter(m => !m.streaming)
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }))
      return apiClient.chat(
        message,
        activeSession?.id,
        undefined,
        selectedDocs.map(doc => doc.doc_id),
        strictGrounding,
        recentHistory
      )
    },
    onSuccess: (data: ChatResponse) => {
      if (streamTimerRef.current) clearTimeout(streamTimerRef.current)
      streamMessage(
        data.answer,
        data.sources,
        data.intent,
        data.calendar_action ?? null,
        (data.action_metadata as ChatActionMetadata | null) ?? null,
      )
      if (data.calendar_action) {
        qc.invalidateQueries({ queryKey: ['calendar-reminders'] })
        qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
        qc.invalidateQueries({ queryKey: ['calendar-overview'] })
      }
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao consultar o agente')
      setSessions(prev =>
        prev.map(s =>
          s.id === activeSessionId
            ? { ...s, messages: [...s.messages, { role: 'assistant', content: 'Ocorreu um erro ao processar sua mensagem.' }] }
            : s
        )
      )
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, mutation.isPending, flashcardBatchMut.isPending, pendingFlashcardCommand])

  // Cleanup stream on unmount
  useEffect(() => () => { if (streamTimerRef.current) clearTimeout(streamTimerRef.current) }, [])

  function confirmFlashcardCommand() {
    if (!pendingFlashcardCommand) return
    if (pendingFlashcardCommand.docs.length === 0) {
      setPendingFlashcardCommand(null)
      navigate('/docs')
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
    if (!text || mutation.isPending || flashcardBatchMut.isPending || pendingFlashcardCommand) return

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
      return
    }

    mutation.mutate(text)
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
                  confirmLabel={pendingFlashcardCommand.docs.length > 0 ? 'Confirmar e gerar' : 'Ir para Documentos'}
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
                  disabled={isPending || !!pendingFlashcardCommand}
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
                  disabled={!selectedDoc || isPending || !!pendingFlashcardCommand}
                  onClick={() => {
                    const docToAdd = (docs ?? []).find(doc => doc.doc_id === selectedDoc)
                    if (!docToAdd || selectedDocs.some(item => item.doc_id === docToAdd.doc_id)) return
                    setSelectedDocs(prev => [...prev, docToAdd])
                    setSelectedDoc('')
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
                        onClick={() => setSelectedDocs(prev => prev.filter(item => item.doc_id !== doc.doc_id))}
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
                  disabled={isPending || !!pendingFlashcardCommand}
                  className="accent-blue-600"
                />
                Modo strict grounding (respostas só com evidência forte)
              </label>
            </div>
          )}

          <div className="flex gap-2">
            <Input
              placeholder="Faça uma pergunta sobre seus documentos ou crie um lembrete..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isPending || isStreaming || !!pendingFlashcardCommand}
              className="flex-1 bg-zinc-900 border-zinc-700"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isPending || isStreaming || !!pendingFlashcardCommand}
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
