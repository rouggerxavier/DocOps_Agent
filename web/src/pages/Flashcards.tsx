import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, Trash2, ChevronLeft,
  Layers, BookOpen, Loader2, Eye, EyeOff, ThumbsUp, ThumbsDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { apiClient, type FlashcardDeck, type FlashcardDeckListItem, type DocItem } from '@/api/client'
import { cn } from '@/lib/utils'

// ── Difficulty helpers ──────────────────────────────────────────────────────

const DIFFICULTY_LABELS: Record<string, string> = {
  facil: 'Fácil',
  media: 'Média',
  dificil: 'Difícil',
}

const DIFFICULTY_STYLES: Record<string, string> = {
  facil: 'border-emerald-800/50 bg-emerald-950/20 text-emerald-400',
  media: 'border-yellow-800/50 bg-yellow-950/20 text-yellow-400',
  dificil: 'border-red-800/50 bg-red-950/20 text-red-400',
}

// ── Generate dialog ──────────────────────────────────────────────────────────

function GenerateDialog({
  docs,
  onGenerate,
  generating,
  onClose,
}: {
  docs: DocItem[]
  onGenerate: (docName: string, numCards: number, contentFilter: string) => void
  generating: boolean
  onClose: () => void
}) {
  const [selectedDoc, setSelectedDoc] = useState(docs[0]?.file_name ?? '')
  const [numCards, setNumCards] = useState(10)
  const [scope, setScope] = useState<'full' | 'specific'>('full')
  const [contentFilter, setContentFilter] = useState('')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <h2 className="text-base font-semibold text-zinc-100 mb-4">Gerar Flashcards</h2>

        <div className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Documento fonte</label>
            <select
              value={selectedDoc}
              onChange={e => setSelectedDoc(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none"
            >
              {docs.map(d => (
                <option key={d.file_name} value={d.file_name}>{d.file_name}</option>
              ))}
            </select>
          </div>

          {/* Scope: full doc vs specific content */}
          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Escopo do conteúdo</label>
            <div className="flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
              <button
                onClick={() => { setScope('full'); setContentFilter('') }}
                className={cn(
                  'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  scope === 'full' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300',
                )}
              >
                Documento inteiro
              </button>
              <button
                onClick={() => setScope('specific')}
                className={cn(
                  'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  scope === 'specific' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300',
                )}
              >
                Conteúdo específico
              </button>
            </div>
            {scope === 'specific' && (
              <Input
                autoFocus
                value={contentFilter}
                onChange={e => setContentFilter(e.target.value)}
                placeholder="Ex: fotossíntese, capítulo 3, mitose..."
                className="mt-2 bg-zinc-900 border-zinc-800 text-sm"
              />
            )}
          </div>

          <div className="space-y-1">
            <label className="text-xs text-zinc-400">Quantidade de cards</label>
            <input
              type="range"
              min={3}
              max={30}
              value={numCards}
              onChange={e => setNumCards(Number(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-zinc-500 text-right">{numCards} cards</p>
          </div>
        </div>

        <div className="mt-6 flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={generating}>
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={() => onGenerate(selectedDoc, numCards, scope === 'specific' ? contentFilter : '')}
            disabled={generating || !selectedDoc || (scope === 'specific' && !contentFilter.trim())}
          >
            {generating && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            Gerar
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Study session ────────────────────────────────────────────────────────────

function StudySession({
  deck,
  onBack,
}: {
  deck: FlashcardDeck
  onBack: () => void
}) {
  const qc = useQueryClient()
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const cards = deck.cards

  const reviewMut = useMutation({
    mutationFn: ({ cardId, ease }: { cardId: number; ease: number }) =>
      apiClient.reviewFlashcard(cardId, ease),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flashcard-deck', deck.id] }),
  })

  if (!cards.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-sm text-zinc-500">Este deck não tem cards.</p>
        <Button variant="ghost" size="sm" onClick={onBack} className="mt-4">Voltar</Button>
      </div>
    )
  }

  const card = cards[idx]
  const isLast = idx === cards.length - 1
  const diffLabel = DIFFICULTY_LABELS[card.difficulty] ?? 'Média'
  const diffStyle = DIFFICULTY_STYLES[card.difficulty] ?? DIFFICULTY_STYLES.media

  function handleRate(ease: number) {
    reviewMut.mutate({ cardId: card.id, ease })
    setFlipped(false)
    if (!isLast) {
      setIdx(i => i + 1)
    } else {
      toast.success('Sessão concluída!')
      setIdx(0)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
          <ChevronLeft className="h-3.5 w-3.5" /> Voltar
        </button>
        <p className="text-xs text-zinc-600">{idx + 1} / {cards.length}</p>
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full rounded-full bg-zinc-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${((idx + 1) / cards.length) * 100}%` }}
        />
      </div>

      {/* Card */}
      <div
        onClick={() => setFlipped(f => !f)}
        className={cn(
          'relative cursor-pointer rounded-2xl border p-8 min-h-[250px] flex flex-col items-center justify-center text-center transition-all',
          flipped
            ? 'border-emerald-800/50 bg-emerald-950/20'
            : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700',
        )}
      >
        {/* Difficulty badge */}
        <div className="absolute top-3 left-3">
          <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium', diffStyle)}>
            {diffLabel}
          </span>
        </div>
        <div className="absolute top-3 right-3">
          {flipped
            ? <Eye className="h-3.5 w-3.5 text-emerald-500" />
            : <EyeOff className="h-3.5 w-3.5 text-zinc-700" />
          }
        </div>

        {!flipped ? (
          <>
            <p className="text-xs text-zinc-600 mb-3 uppercase tracking-wider">Pergunta</p>
            <p className="text-base font-medium text-zinc-100 leading-relaxed">{card.front}</p>
            <p className="mt-4 text-[10px] text-zinc-700">Clique para ver a resposta</p>
          </>
        ) : (
          <>
            <p className="text-xs text-emerald-600 mb-3 uppercase tracking-wider">Resposta</p>
            <p className="text-base text-zinc-200 leading-relaxed">{card.back}</p>
          </>
        )}
      </div>

      {/* Rating buttons — shown after flipping */}
      {flipped && (
        <div className="space-y-3">
          {/* LLM difficulty assessment */}
          <div className="flex items-center justify-center gap-2 text-xs text-zinc-500">
            <span>A IA classificou como <span className={cn('font-semibold', diffStyle.split(' ').pop())}>{diffLabel}</span>. Concorda?</span>
            <button className="p-1 rounded hover:bg-zinc-800 text-emerald-500 hover:text-emerald-400" title="Concordo">
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button className="p-1 rounded hover:bg-zinc-800 text-red-500 hover:text-red-400" title="Discordo">
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Ease rating */}
          <div className="flex gap-2">
            <button
              onClick={() => handleRate(1)}
              className="flex-1 rounded-xl border border-red-800/50 bg-red-950/20 py-3 text-xs font-medium text-red-400 hover:bg-red-950/40 transition-colors"
            >
              Difícil
            </button>
            <button
              onClick={() => handleRate(2)}
              className="flex-1 rounded-xl border border-yellow-800/50 bg-yellow-950/20 py-3 text-xs font-medium text-yellow-400 hover:bg-yellow-950/40 transition-colors"
            >
              Bom
            </button>
            <button
              onClick={() => handleRate(3)}
              className="flex-1 rounded-xl border border-emerald-800/50 bg-emerald-950/20 py-3 text-xs font-medium text-emerald-400 hover:bg-emerald-950/40 transition-colors"
            >
              Fácil
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function Flashcards() {
  const qc = useQueryClient()
  const [showGenerate, setShowGenerate] = useState(false)
  const [studyDeckId, setStudyDeckId] = useState<number | null>(null)

  const { data: decks = [], isLoading } = useQuery<FlashcardDeckListItem[]>({
    queryKey: ['flashcard-decks'],
    queryFn: apiClient.listFlashcardDecks,
  })

  const { data: docs = [] } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const { data: studyDeck } = useQuery<FlashcardDeck>({
    queryKey: ['flashcard-deck', studyDeckId],
    queryFn: () => apiClient.getFlashcardDeck(studyDeckId!),
    enabled: studyDeckId !== null,
  })

  const generateMut = useMutation({
    mutationFn: ({ docName, numCards, contentFilter }: { docName: string; numCards: number; contentFilter: string }) =>
      apiClient.generateFlashcards(docName, numCards, contentFilter),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      setShowGenerate(false)
      toast.success('Flashcards gerados!')
    },
    onError: () => toast.error('Erro ao gerar flashcards.'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteFlashcardDeck(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      toast.success('Deck excluído.')
    },
  })

  // Study mode — centralized
  if (studyDeckId !== null && studyDeck) {
    return (
      <div className="mx-auto max-w-xl">
        <StudySession deck={studyDeck} onBack={() => setStudyDeckId(null)} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-center flex-1">
          <h1 className="text-2xl font-bold text-zinc-100">Flashcards</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Revisão espaçada a partir dos seus documentos</p>
        </div>
        <Button
          size="sm"
          onClick={() => setShowGenerate(true)}
          disabled={docs.length === 0}
          className="gap-1"
        >
          <Plus className="h-3.5 w-3.5" /> Gerar Deck
        </Button>
      </div>

      {docs.length === 0 && (
        <Card className="border-zinc-800 bg-zinc-900 mx-auto max-w-md">
          <CardContent className="p-6 text-center">
            <BookOpen className="mx-auto h-8 w-8 text-zinc-700 mb-2" />
            <p className="text-sm text-zinc-500">Ingira documentos primeiro para gerar flashcards.</p>
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[1, 2, 3].map(i => <div key={i} className="h-28 rounded-xl bg-zinc-900 animate-pulse" />)}
        </div>
      )}

      {!isLoading && decks.length === 0 && docs.length > 0 && (
        <Card className="border-zinc-800 bg-zinc-900 mx-auto max-w-md">
          <CardContent className="p-6 text-center">
            <Layers className="mx-auto h-8 w-8 text-zinc-700 mb-2" />
            <p className="text-sm text-zinc-500">Nenhum deck ainda. Gere flashcards a partir de um documento!</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {decks.map(deck => (
          <div
            key={deck.id}
            className="group relative rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-700 transition-all cursor-pointer"
            onClick={() => setStudyDeckId(deck.id)}
          >
            <p className="text-sm font-semibold text-zinc-100 pr-6 truncate">{deck.title}</p>
            <p className="mt-1 text-xs text-zinc-500">{deck.card_count} cards</p>
            <p className="mt-0.5 text-[10px] text-zinc-700">
              {new Date(deck.created_at).toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'short',
              })}
            </p>
            <button
              onClick={e => { e.stopPropagation(); deleteMut.mutate(deck.id) }}
              className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-zinc-700 hover:text-red-400 transition-all"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showGenerate && (
        <GenerateDialog
          docs={docs}
          onGenerate={(docName, numCards, contentFilter) => generateMut.mutate({ docName, numCards, contentFilter })}
          generating={generateMut.isPending}
          onClose={() => setShowGenerate(false)}
        />
      )}
    </div>
  )
}
