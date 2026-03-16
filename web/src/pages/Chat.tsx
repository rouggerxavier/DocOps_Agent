import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Send, Bot, User, FileText, ChevronRight, Loader2, X,
  Plus, MessageSquare, Clock, CalendarCheck, Trash2
} from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { apiClient, type ChatResponse, type SourceItem, type DocItem } from '@/api/client'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
  intent?: string
  calendar_action?: Record<string, any> | null
}

interface ChatSession {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
}

const STORAGE_KEY = 'docops_chat_sessions'

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
  } catch {}
}

function newSession(): ChatSession {
  return {
    id: `session_${Date.now()}`,
    title: 'Nova conversa',
    messages: [],
    createdAt: new Date(),
  }
}

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
            'rounded-2xl px-4 py-3 text-sm',
            isUser
              ? 'rounded-tr-sm bg-blue-600 text-white'
              : 'rounded-tl-sm bg-zinc-800 text-zinc-100'
          )}
          style={{ userSelect: 'text', cursor: 'text' }}
        >
          {isUser ? (
            <p style={{ userSelect: 'text' }}>{message.content}</p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none" style={{ userSelect: 'text' }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Calendar action badge */}
        {!isUser && message.calendar_action && (
          <CalendarActionBadge action={message.calendar_action} />
        )}

        {/* Sources chip */}
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

        {!isUser && message.intent && !['qa', 'calendar', 'calendar_create_reminder', 'calendar_create_schedule'].includes(message.intent) && (
          <Badge variant="secondary" className="text-xs">
            {message.intent}
          </Badge>
        )}
      </div>
    </div>
  )
}

export function Chat() {
  const qc = useQueryClient()
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
  const bottomRef = useRef<HTMLDivElement>(null)

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? sessions[0]
  const messages = activeSession?.messages ?? []

  // Persist sessions to localStorage
  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const mutation = useMutation({
    mutationFn: (message: string) =>
      apiClient.chat(
        message,
        activeSession?.id,
        undefined,
        selectedDocs.map(doc => doc.doc_id),
        strictGrounding
      ),
    onSuccess: (data: ChatResponse) => {
      const botMsg: Message = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources,
        intent: data.intent,
        calendar_action: data.calendar_action,
      }
      setSessions(prev =>
        prev.map(s =>
          s.id === activeSessionId
            ? { ...s, messages: [...s.messages, botMsg] }
            : s
        )
      )
      if (data.sources.length > 0) {
        setActiveSources(data.sources)
        setSelectedSource(null)
      }
      // Invalidate calendar queries if a calendar action was performed
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
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  { role: 'assistant', content: 'Ocorreu um erro ao processar sua mensagem.' },
                ],
              }
            : s
        )
      )
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, mutation.isPending])

  function handleSend() {
    const text = input.trim()
    if (!text || mutation.isPending) return

    const userMsg: Message = { role: 'user', content: text }
    setSessions(prev =>
      prev.map(s => {
        if (s.id !== activeSessionId) return s
        const updated = { ...s, messages: [...s.messages, userMsg] }
        // Auto-title the session from first message
        if (s.messages.length === 0) {
          updated.title = text.length > 40 ? text.slice(0, 40) + '…' : text
        }
        return updated
      })
    )
    setInput('')
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
      if (id === activeSessionId) {
        setActiveSessionId(next[0].id)
      }
      return next
    })
  }

  const hasSources = activeSources.length > 0

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-0 overflow-hidden">
      {/* ── Sidebar: histórico de sessões ─────────────────────────────────── */}
      {sidebarOpen && (
        <div className="flex w-56 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-3">
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
          <div className="border-t border-zinc-800 px-3 py-2">
            <p className="text-[10px] text-zinc-600">
              <Clock className="mr-1 inline h-3 w-3" />
              Salvo localmente
            </p>
          </div>
        </div>
      )}

      {/* ── Área principal do chat ────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-950 px-4 py-3">
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
              {messages.length} msgs
            </Badge>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto bg-zinc-950 px-4 py-4 space-y-4">
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

          {mutation.isPending && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-700">
                <Bot className="h-4 w-4 text-zinc-300" />
              </div>
              <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-zinc-800 px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                <span className="text-sm text-zinc-400">Processando...</span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-3 space-y-2">
            <div className="flex gap-2">
              <select
                value={selectedDoc}
                onChange={e => setSelectedDoc(e.target.value)}
                disabled={mutation.isPending}
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
                disabled={!selectedDoc || mutation.isPending}
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
                    title={`${doc.file_name} · ${doc.chunk_count} chunks`}
                  >
                    <FileText className="h-3 w-3 text-zinc-500" />
                    {doc.file_name}
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedDocs(prev => prev.filter(item => item.doc_id !== doc.doc_id))
                      }
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
                disabled={mutation.isPending}
                className="accent-blue-600"
              />
              Modo strict grounding (respostas só com evidência forte)
            </label>
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="Faça uma pergunta sobre seus documentos ou crie um lembrete..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={mutation.isPending}
              className="flex-1 bg-zinc-900 border-zinc-700"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || mutation.isPending}
              size="icon"
            >
              {mutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* ── Painel de fontes ─────────────────────────────────────────────── */}
      <div
        className={cn(
          'w-56 shrink-0 border-l border-zinc-800 bg-zinc-950 transition-all duration-300',
          hasSources ? 'opacity-100' : 'opacity-40'
        )}
      >
        <CardHeader className="border-b border-zinc-800 py-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <FileText className="h-4 w-4 text-blue-400" />
            Fontes Citadas
            {hasSources && (
              <Badge variant="secondary" className="ml-auto">
                {activeSources.length}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <div className="p-3 overflow-y-auto" style={{ maxHeight: 'calc(100% - 4rem)' }}>
          {!hasSources ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <FileText className="h-8 w-8 text-zinc-700" />
              <p className="text-xs text-zinc-600">
                As fontes aparecem aqui após o chat
              </p>
            </div>
          ) : (
            <SourcePanel
              sources={activeSources}
              selected={selectedSource}
              onSelect={s =>
                setSelectedSource(prev =>
                  prev?.fonte_n === s.fonte_n ? null : s
                )
              }
            />
          )}
        </div>
      </div>
    </div>
  )
}
