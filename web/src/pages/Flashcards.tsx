import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import {
  Plus, Trash2, ChevronLeft,
  Layers, BookOpen, Loader2, Eye, EyeOff, ThumbsUp, ThumbsDown, Send, AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { PageShell } from '@/components/ui/page-shell'
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

type DiffMode = 'any' | 'only_facil' | 'only_media' | 'only_dificil' | 'custom'

// ── Generate dialog ──────────────────────────────────────────────────────────

function GenerateDialog({
  docs,
  onGenerate,
  generating,
  onClose,
  errorMessage,
}: {
  docs: DocItem[]
  onGenerate: (
    docName: string,
    numCards: number,
    contentFilter: string,
    difficultyMode: DiffMode,
    difficultyCustom: { facil: number; media: number; dificil: number } | null,
  ) => void
  generating: boolean
  onClose: () => void
  errorMessage: string | null
}) {
  const [selectedDoc, setSelectedDoc] = useState(docs[0]?.file_name ?? '')
  const [numCards, setNumCards] = useState(10)
  const [scope, setScope] = useState<'full' | 'specific'>('full')
  const [contentFilter, setContentFilter] = useState('')
  const [diffMode, setDiffMode] = useState<DiffMode>('any')
  const [custom, setCustom] = useState({ facil: 4, media: 4, dificil: 2 })

  const customTotal = custom.facil + custom.media + custom.dificil
  const effectiveTotal = diffMode === 'custom' ? customTotal : numCards

  function handleSubmit() {
    onGenerate(
      selectedDoc,
      effectiveTotal,
      scope === 'specific' ? contentFilter : '',
      diffMode,
      diffMode === 'custom' ? custom : null,
    )
  }

  const canSubmit =
    !!selectedDoc &&
    !(scope === 'specific' && !contentFilter.trim()) &&
    !(diffMode === 'custom' && customTotal < 1)

  const DIFF_MODE_OPTIONS: { value: DiffMode; label: string }[] = [
    { value: 'any', label: 'Misto' },
    { value: 'only_facil', label: 'Só Fáceis' },
    { value: 'only_media', label: 'Só Médias' },
    { value: 'only_dificil', label: 'Só Difíceis' },
    { value: 'custom', label: 'Personalizado' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <h2 className="text-base font-semibold text-zinc-100 mb-4">Gerar Flashcards</h2>

        <div className="space-y-4">
          {/* Documento */}
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

          {/* Escopo */}
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

          {/* Dificuldade */}
          <div className="space-y-2">
            <label className="text-xs text-zinc-400">Dificuldade dos cards</label>
            <div className="flex flex-wrap gap-1.5">
              {DIFF_MODE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setDiffMode(opt.value)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                    diffMode === opt.value
                      ? 'border-blue-600 bg-blue-600/20 text-blue-300'
                      : 'border-zinc-700 bg-zinc-900 text-zinc-500 hover:text-zinc-300',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Custom distribution */}
            {diffMode === 'custom' && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
                {(['facil', 'media', 'dificil'] as const).map(key => (
                  <div key={key} className="flex items-center gap-3">
                    <span className={cn(
                      'w-16 text-xs font-medium',
                      key === 'facil' ? 'text-emerald-400' : key === 'media' ? 'text-yellow-400' : 'text-red-400',
                    )}>
                      {DIFFICULTY_LABELS[key]}
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={20}
                      value={custom[key]}
                      onChange={e => setCustom(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                      className="flex-1 accent-current"
                    />
                    <span className="w-6 text-right text-xs text-zinc-300 font-mono">{custom[key]}</span>
                  </div>
                ))}
                <p className="text-right text-[10px] text-zinc-500 pt-1">
                  Total: <span className="text-zinc-300 font-semibold">{customTotal}</span> cards
                </p>
              </div>
            )}
          </div>

          {/* Quantidade (só quando não é custom) */}
          {diffMode !== 'custom' && (
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
          )}
        </div>

        {errorMessage && (
          <div className="mt-4 rounded-xl border border-amber-800/50 bg-amber-950/20 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div className="space-y-1">
                <p className="text-xs font-semibold text-amber-300">Nao foi possivel concluir a geracao</p>
                <p className="text-xs leading-5 text-amber-100/90">{errorMessage}</p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={generating}>
            Cancelar
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={generating || !canSubmit}>
            {generating && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            Gerar {effectiveTotal > 0 ? `(${effectiveTotal})` : ''}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Evaluation result config ─────────────────────────────────────────────────

const VERDICT_CONFIG = {
  correta: {
    label: 'Correta!',
    color: 'text-emerald-400',
    border: 'border-emerald-800/50',
    bg: 'bg-emerald-950/30',
    icon: '✓',
  },
  parcial: {
    label: 'Parcialmente correta',
    color: 'text-yellow-400',
    border: 'border-yellow-800/50',
    bg: 'bg-yellow-950/30',
    icon: '◑',
  },
  incorreta: {
    label: 'Incorreta',
    color: 'text-red-400',
    border: 'border-red-800/50',
    bg: 'bg-red-950/30',
    icon: '✗',
  },
} as const

type Evaluation = { verdict: string; feedback: string; highlight: string }

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
  const [diffVote, setDiffVote] = useState<'agree' | 'disagree' | null>(null)
  const [correctedDiff, setCorrectedDiff] = useState<string | null>(null)
  // resposta do usuário e resultado da avaliação
  const [userAnswer, setUserAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const cards = deck.cards

  const reviewMut = useMutation({
    mutationFn: ({ cardId, ease }: { cardId: number; ease: number }) =>
      apiClient.reviewFlashcard(cardId, ease),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flashcard-deck', deck.id] }),
  })

  const difficultyMut = useMutation({
    mutationFn: ({ cardId, difficulty }: { cardId: number; difficulty: string }) =>
      apiClient.updateFlashcardDifficulty(cardId, difficulty),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['flashcard-deck', deck.id] })
      toast.success(`Dificuldade atualizada para ${DIFFICULTY_LABELS[data.difficulty] ?? data.difficulty}!`)
    },
    onError: () => toast.error('Erro ao atualizar dificuldade.'),
  })

  const evaluateMut = useMutation({
    mutationFn: ({ cardId, answer }: { cardId: number; answer: string }) =>
      apiClient.evaluateFlashcard(cardId, answer),
    onSuccess: (data) => {
      setEvaluation(data)
      setFlipped(true)
    },
    onError: () => toast.error('Erro ao avaliar resposta.'),
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
  const activeDiff = correctedDiff ?? card.difficulty
  const diffLabel = DIFFICULTY_LABELS[activeDiff] ?? 'Média'
  const diffStyle = DIFFICULTY_STYLES[activeDiff] ?? DIFFICULTY_STYLES.media

  function advanceCard() {
    setFlipped(false)
    setDiffVote(null)
    setCorrectedDiff(null)
    setUserAnswer('')
    setEvaluation(null)
    if (!isLast) {
      setIdx(i => i + 1)
    } else {
      toast.success('Sessão concluída!')
      setIdx(0)
    }
  }

  function handleRate(ease: number) {
    reviewMut.mutate({ cardId: card.id, ease })
    advanceCard()
  }

  function handleAgree() {
    setDiffVote('agree')
    toast.success(`Dificuldade "${diffLabel}" confirmada.`)
  }

  function handleDisagree() {
    setDiffVote('disagree')
  }

  function handleCorrectDiff(newDiff: string) {
    setCorrectedDiff(newDiff)
    setDiffVote('agree')
    difficultyMut.mutate({ cardId: card.id, difficulty: newDiff })
  }

  const verdictCfg = evaluation
    ? (VERDICT_CONFIG[evaluation.verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.parcial)
    : null

  return (
    <div className="space-y-4">
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
        onClick={() => !flipped && !evaluateMut.isPending && setFlipped(true)}
        className={cn(
          'relative rounded-2xl border p-8 min-h-[200px] flex flex-col items-center justify-center text-center transition-all',
          flipped
            ? 'border-emerald-800/50 bg-emerald-950/20'
            : 'border-zinc-800 bg-zinc-900 cursor-pointer hover:border-zinc-700',
        )}
      >
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
            <p className="mt-4 text-[10px] text-zinc-700">Clique para ver a resposta diretamente</p>
          </>
        ) : (
          <>
            <p className="text-xs text-emerald-600 mb-3 uppercase tracking-wider">Resposta oficial</p>
            <p className="text-base text-zinc-200 leading-relaxed">{card.back}</p>
          </>
        )}
      </div>

      {/* ── Aba de resposta do estudante (antes de virar) ─────────────────── */}
      {!flipped && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
          <p className="text-xs text-zinc-500">Sua resposta <span className="text-zinc-700">(opcional — ou clique no card para ver direto)</span></p>
          <textarea
            value={userAnswer}
            onChange={e => setUserAnswer(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && userAnswer.trim()) {
                e.preventDefault()
                evaluateMut.mutate({ cardId: card.id, answer: userAnswer.trim() })
              }
            }}
            placeholder="Digite sua resposta aqui..."
            rows={3}
            className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-700 outline-none focus:border-zinc-500 transition-colors"
          />
          <div className="flex justify-end">
            <button
              onClick={() => evaluateMut.mutate({ cardId: card.id, answer: userAnswer.trim() })}
              disabled={!userAnswer.trim() || evaluateMut.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-blue-800/50 bg-blue-950/20 px-3 py-1.5 text-xs font-medium text-blue-400 hover:bg-blue-950/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {evaluateMut.isPending
                ? <><Loader2 className="h-3 w-3 animate-spin" /> Avaliando...</>
                : <><Send className="h-3 w-3" /> Avaliar <span className="text-zinc-600 ml-1">Ctrl+Enter</span></>
              }
            </button>
          </div>
        </div>
      )}

      {/* ── Resultado da avaliação (após avaliar) ────────────────────────── */}
      {flipped && evaluation && verdictCfg && (
        <div className={cn('rounded-xl border p-4 space-y-3', verdictCfg.border, verdictCfg.bg)}>
          {/* Verdict */}
          <div className="flex items-center gap-2">
            <span className={cn('text-lg font-bold', verdictCfg.color)}>{verdictCfg.icon}</span>
            <span className={cn('text-sm font-semibold', verdictCfg.color)}>{verdictCfg.label}</span>
          </div>

          {/* Resposta do usuário */}
          <div className="rounded-lg border border-zinc-700/50 bg-zinc-900/50 px-3 py-2">
            <p className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1">Sua resposta</p>
            <p className="text-xs text-zinc-400 italic">"{userAnswer}"</p>
          </div>

          {/* Feedback */}
          <div>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Avaliação</p>
            <p className="text-xs text-zinc-300 leading-relaxed">{evaluation.feedback}</p>
          </div>

          {/* Highlight */}
          {evaluation.highlight && (
            <div className="flex items-start gap-2 rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-3 py-2">
              <span className="text-yellow-500 text-xs mt-0.5">💡</span>
              <p className="text-xs text-zinc-400">{evaluation.highlight}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Seção de dificuldade + ease (após virar) ─────────────────────── */}
      {flipped && (
        <div className="space-y-3">
          {/* LLM difficulty vote */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            {diffVote === null && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400">
                  A IA classificou como{' '}
                  <span className={cn('font-semibold', diffStyle.split(' ').pop())}>{diffLabel}</span>.
                  {' '}Você concorda?
                </span>
                <div className="flex gap-1 ml-3 shrink-0">
                  <button
                    onClick={handleAgree}
                    className="flex items-center gap-1 rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-2.5 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-950/40 transition-colors"
                  >
                    <ThumbsUp className="h-3 w-3" /> Sim
                  </button>
                  <button
                    onClick={handleDisagree}
                    className="flex items-center gap-1 rounded-lg border border-red-800/50 bg-red-950/20 px-2.5 py-1.5 text-xs font-medium text-red-400 hover:bg-red-950/40 transition-colors"
                  >
                    <ThumbsDown className="h-3 w-3" /> Não
                  </button>
                </div>
              </div>
            )}
            {diffVote === 'agree' && (
              <p className="text-xs text-zinc-500 text-center">
                ✓ Dificuldade <span className={cn('font-semibold', (DIFFICULTY_STYLES[activeDiff] ?? DIFFICULTY_STYLES.media).split(' ').pop())}>{DIFFICULTY_LABELS[activeDiff]}</span> confirmada.
              </p>
            )}
            {diffVote === 'disagree' && (
              <div className="space-y-2">
                <p className="text-xs text-zinc-400 text-center">Qual é a dificuldade correta?</p>
                <div className="flex gap-2 justify-center">
                  {(['facil', 'media', 'dificil'] as const).map(d => (
                    <button
                      key={d}
                      onClick={() => handleCorrectDiff(d)}
                      disabled={difficultyMut.isPending}
                      className={cn(
                        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                        DIFFICULTY_STYLES[d],
                        d === card.difficulty && 'opacity-40 cursor-default',
                        d !== card.difficulty && 'hover:opacity-80',
                      )}
                    >
                      {DIFFICULTY_LABELS[d]}
                    </button>
                  ))}
                </div>
              </div>
            )}
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
  const [generateError, setGenerateError] = useState<string | null>(null)

  function getGenerateFlashcardsErrorMessage(error: unknown): string {
    if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
      return 'A geracao demorou mais que o esperado. O deck ainda pode estar sendo criado no servidor. Vou atualizar a lista automaticamente. Se ele aparecer, basta fechar esta janela e abrir o deck.'
    }

    const detail = axios.isAxiosError(error) && typeof error.response?.data?.detail === 'string'
      ? error.response.data.detail
      : null

    if (detail?.includes('distribuicao pedida') && detail?.includes('flashcards unicos')) {
      return 'Nao consegui montar a distribuicao exata de dificuldades sem repetir perguntas. Tente pedir menos cards, ampliar o conteudo usado ou deixar a distribuicao menos rigida.'
    }

    if (detail?.includes('distribuicao pedida')) {
      return 'Nao consegui atingir a distribuicao de dificuldades que voce pediu com seguranca. Tente reduzir a quantidade total ou usar uma combinacao menos restritiva.'
    }

    if (detail?.includes('flashcards unicos')) {
      return 'Nao encontrei perguntas unicas suficientes nesse recorte do conteudo. Tente pedir menos cards ou usar o documento inteiro.'
    }

    return detail ?? 'Ocorreu um erro ao gerar flashcards. Tente novamente em instantes.'
  }

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
    mutationFn: ({
      docName,
      numCards,
      contentFilter,
      difficultyMode,
      difficultyCustom,
    }: {
      docName: string
      numCards: number
      contentFilter: string
      difficultyMode: DiffMode
      difficultyCustom: { facil: number; media: number; dificil: number } | null
    }) => {
      setGenerateError(null)
      return apiClient.generateFlashcards(docName, numCards, contentFilter, difficultyMode, difficultyCustom)
    },
    onSuccess: (deck) => {
      setGenerateError(null)
      qc.setQueryData<FlashcardDeckListItem[]>(['flashcard-decks'], (current = []) => {
        const nextItem: FlashcardDeckListItem = {
          id: deck.id,
          title: deck.title,
          source_doc: deck.source_doc,
          card_count: deck.cards.length,
          created_at: deck.created_at,
        }
        return [nextItem, ...current.filter(item => item.id !== deck.id)]
      })
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      setShowGenerate(false)
      toast.success('Flashcards gerados!')
    },
    onError: (error) => {
      const message = getGenerateFlashcardsErrorMessage(error)
      setGenerateError(message)
      const timedOut = axios.isAxiosError(error) && error.code === 'ECONNABORTED'

      if (timedOut) {
        toast.error(message)
        void qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
        window.setTimeout(() => {
          void qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
        }, 4000)
        return
      }

      toast.error(message)
    },
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
    <PageShell className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-center flex-1">
          <h1 className="text-2xl font-bold text-zinc-100">Flashcards</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Revisão espaçada a partir dos seus documentos</p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setGenerateError(null)
            setShowGenerate(true)
          }}
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
            <p className="text-sm text-zinc-500">Insira documentos primeiro para gerar flashcards.</p>
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
          onGenerate={(docName, numCards, contentFilter, difficultyMode, difficultyCustom) =>
            generateMut.mutate({ docName, numCards, contentFilter, difficultyMode, difficultyCustom })
          }
          generating={generateMut.isPending}
          onClose={() => {
            setGenerateError(null)
            setShowGenerate(false)
          }}
          errorMessage={generateError}
        />
      )}
    </PageShell>
  )
}
