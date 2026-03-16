import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, Bot, User, FileText, ChevronRight, Loader2, X } from 'lucide-react'
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
}

function SourcePanel({
  sources,
  selected,
  onSelect,
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

function MessageBubble({
  message,
  onSourceClick,
}: {
  message: Message
  onSourceClick?: (sources: SourceItem[]) => void
}) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
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

      {/* Content */}
      <div className={cn('max-w-[75%] space-y-2', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-3 text-sm',
            isUser
              ? 'rounded-tr-sm bg-blue-600 text-white'
              : 'rounded-tl-sm bg-zinc-800 text-zinc-100'
          )}
        >
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Sources chip */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <button
            onClick={() => onSourceClick?.(message.sources!)}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-blue-400 transition-colors"
          >
            <FileText className="h-3 w-3" />
            {message.sources.length} fonte(s) citada(s)
            <ChevronRight className="h-3 w-3" />
          </button>
        )}

        {!isUser && message.intent && message.intent !== 'qa' && (
          <Badge variant="secondary" className="text-xs">
            {message.intent}
          </Badge>
        )}
      </div>
    </div>
  )
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])
  const [activeSources, setActiveSources] = useState<SourceItem[]>([])
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const sessionId = useRef(`session_${Date.now()}`)

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const mutation = useMutation({
    mutationFn: (message: string) =>
      apiClient.chat(
        message,
        sessionId.current,
        undefined,
        selectedDocs.map(doc => doc.doc_id)
      ),
    onSuccess: (data: ChatResponse) => {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          intent: data.intent,
        },
      ])
      if (data.sources.length > 0) {
        setActiveSources(data.sources)
        setSelectedSource(null)
      }
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao consultar o agente')
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: 'Ocorreu um erro ao processar sua mensagem. Verifique o servidor.',
        },
      ])
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, mutation.isPending])

  function handleSend() {
    const text = input.trim()
    if (!text || mutation.isPending) return

    setMessages(prev => [...prev, { role: 'user', content: text }])
    setInput('')
    mutation.mutate(text)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const hasSources = activeSources.length > 0

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Chat area */}
      <div className="flex flex-1 flex-col rounded-xl border border-zinc-800 bg-zinc-900">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-3">
          <Bot className="h-5 w-5 text-blue-400" />
          <div>
            <p className="text-sm font-semibold text-zinc-100">DocOps Chat</p>
            <p className="text-xs text-zinc-500">RAG com Gemini + Chroma</p>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <Bot className="h-12 w-12 text-zinc-600" />
              <p className="text-sm font-medium text-zinc-400">OlÃ¡! Como posso ajudar?</p>
              <p className="text-xs text-zinc-600">
                FaÃ§a perguntas sobre seus documentos indexados.
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
        <div className="border-t border-zinc-800 p-4">
          <div className="mb-3 space-y-2">
            <div className="flex gap-2">
              <select
                value={selectedDoc}
                onChange={e => setSelectedDoc(e.target.value)}
                disabled={mutation.isPending}
                className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
              >
                <option value="">Selecionar documento (opcional)</option>
                {(docs ?? [])
                  .filter(doc => !selectedDocs.some(item => item.doc_id === doc.doc_id))
                  .map(doc => (
                    <option key={doc.doc_id} value={doc.doc_id}>
                      {doc.file_name}
                    </option>
                  ))}
              </select>
              <Button
                type="button"
                variant="outline"
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
                  >
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
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="FaÃ§a uma pergunta sobre seus documentos..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={mutation.isPending}
              className="flex-1"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || mutation.isPending}
              size="icon"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Sources panel */}
      <div
        className={cn(
          'w-72 shrink-0 rounded-xl border border-zinc-800 bg-zinc-900 transition-all duration-300',
          hasSources ? 'opacity-100' : 'opacity-50'
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
              <FileText className="h-8 w-8 text-zinc-600" />
              <p className="text-xs text-zinc-500">
                As fontes aparecerÃ£o aqui apÃ³s o chat
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
