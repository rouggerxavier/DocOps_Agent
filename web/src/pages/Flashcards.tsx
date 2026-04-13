import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import {
  Plus, Trash2, ChevronLeft, ChevronDown,
  Layers, Loader2, ThumbsUp, ThumbsDown, Send, AlertTriangle,
  ArrowRight, FileText, X, Bot, Sparkles, Brain,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

function normalizeFront(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function dedupeDeckCards(cards: FlashcardDeck['cards']): FlashcardDeck['cards'] {
  const ordered = [...cards].sort((a, b) => a.id - b.id)
  const seen = new Set<string>()
  const unique: FlashcardDeck['cards'] = []
  for (const card of ordered) {
    const key = normalizeFront(card.front ?? '')
    if (!key || seen.has(key)) continue
    seen.add(key)
    unique.push(card)
  }
  return unique
}

type DiffMode = 'any' | 'only_facil' | 'only_media' | 'only_dificil' | 'custom'

function formatDeckDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

// ── Doc selector (custom dropdown) ──────────────────────────────────────────

function DocSelector({
  docs,
  value,
  onChange,
}: {
  docs: DocItem[]
  value: string
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selected = docs.find(d => d.file_name === value)

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [])

  return (
    <div className="space-y-3">
      <label className="block text-xs font-semibold tracking-widest text-primary uppercase">
        Documento fonte
      </label>
      <div ref={ref} className="relative">
        {/* Trigger */}
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="w-full bg-[#0a0a0a] rounded-lg p-4 flex items-center justify-between transition-colors hover:bg-[#111111]"
          style={{ border: '1px solid rgba(65,71,78,0.15)' }}
        >
          <div className="flex items-center gap-4 min-w-0">
            <div className="p-2 bg-primary/10 rounded-lg shrink-0">
              <FileText className="text-primary w-5 h-5" />
            </div>
            <div className="flex flex-col min-w-0 text-left">
              <span className="text-on-surface font-medium text-sm truncate">
                {selected?.file_name ?? 'Selecione um documento'}
              </span>
              <span className="text-xs text-on-surface-variant mt-0.5">
                {selected?.chunk_count ?? 0} chunks indexados
              </span>
            </div>
          </div>
          <ChevronDown
            className={cn('text-on-surface-variant w-5 h-5 shrink-0 transition-transform duration-200', open && 'rotate-180')}
          />
        </button>

        {/* Dropdown list */}
        {open && (
          <div
            className="absolute left-0 right-0 top-full mt-1 z-50 rounded-lg overflow-hidden"
            style={{
              background: '#111111',
              border: '1px solid rgba(65,71,78,0.20)',
              boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
            }}
          >
            {docs.map(d => (
              <button
                key={d.file_name}
                type="button"
                onClick={() => { onChange(d.file_name); setOpen(false) }}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
                  d.file_name === value
                    ? 'bg-primary/10 text-primary'
                    : 'text-on-surface hover:bg-[#1e1e1e]',
                )}
              >
                <FileText className="w-4 h-4 shrink-0 opacity-60" />
                <span className="text-sm truncate">{d.file_name}</span>
                <span className="ml-auto text-[10px] text-on-surface-variant shrink-0">{d.chunk_count}c</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Generate dialog ──────────────────────────────────────────────────────────

function GenerateDialog({
  docs,
  decks,
  onGenerate,
  generating,
  onClose,
  errorMessage,
}: {
  docs: DocItem[]
  decks: FlashcardDeckListItem[]
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

  const recentDecks = decks.slice(0, 3)

  const trackPercent = ((numCards - 3) / (30 - 3)) * 100

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6">
      <div className="w-full max-w-4xl rounded-2xl bg-[#0e0e0e] shadow-[0_40px_100px_rgba(0,0,0,0.6)] overflow-hidden flex flex-col max-h-[90vh]"
        style={{ border: '1px solid rgba(65,71,78,0.15)' }}>

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-10 py-6"
          style={{ borderBottom: '1px solid rgba(65,71,78,0.10)' }}>
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-primary/10 rounded-lg">
              <Layers className="w-4 h-4 text-primary" />
            </div>
            <h2 className="font-headline font-bold text-lg text-[#c5e3ff] tracking-tight">
              Flashcard Generator
            </h2>
          </div>
          <button
            onClick={onClose}
            disabled={generating}
            className="text-neutral-500 hover:text-neutral-200 transition-colors p-1 rounded-lg hover:bg-white/5"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="overflow-y-auto flex-1 px-10 py-8">
          <div className="grid grid-cols-12 gap-8 items-start">

            {/* ── Left: Form (8 cols) ── */}
            <section className="col-span-8 space-y-8">

              {/* Documento fonte */}
              <DocSelector docs={docs} value={selectedDoc} onChange={setSelectedDoc} />

              {/* Escopo */}
              <div className="space-y-3">
                <label className="block text-xs font-semibold tracking-widest text-primary uppercase">
                  Escopo do conteúdo
                </label>
                <div className="flex p-1 bg-[#0a0a0a] rounded-xl w-fit"
                  style={{ border: '1px solid rgba(65,71,78,0.15)' }}>
                  <button
                    onClick={() => { setScope('full'); setContentFilter('') }}
                    className={cn(
                      'px-5 py-2 rounded-lg text-sm font-semibold transition-all',
                      scope === 'full'
                        ? 'bg-surface-container-high text-on-surface shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface font-medium',
                    )}
                  >
                    Documento inteiro
                  </button>
                  <button
                    onClick={() => setScope('specific')}
                    className={cn(
                      'px-5 py-2 rounded-lg text-sm font-semibold transition-all',
                      scope === 'specific'
                        ? 'bg-surface-container-high text-on-surface shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface font-medium',
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
                    className="mt-2 bg-[#0a0a0a] text-sm"
                    style={{ border: '1px solid rgba(65,71,78,0.15)' }}
                  />
                )}
              </div>

              {/* Dificuldade */}
              <div className="space-y-3">
                <label className="block text-xs font-semibold tracking-widest text-primary uppercase">
                  Dificuldade dos cards
                </label>
                <div className="flex flex-wrap gap-2">
                  {DIFF_MODE_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setDiffMode(opt.value)}
                      className={cn(
                        'px-5 py-2 rounded-full text-sm font-semibold transition-all',
                        diffMode === opt.value
                          ? 'bg-[#93C5FD] text-[#001e30] font-bold shadow-lg ring-2 ring-[#93C5FD]/40'
                          : 'bg-[#1e1e1e] text-on-surface-variant hover:bg-[#282828] hover:text-on-surface',
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>

                {/* Custom distribution */}
                {diffMode === 'custom' && (
                  <div className="rounded-xl p-4 space-y-3 mt-1"
                    style={{ background: '#0e0e0e', border: '1px solid rgba(65,71,78,0.15)' }}>
                    {(['facil', 'media', 'dificil'] as const).map(key => (
                      <div key={key} className="flex items-center gap-3">
                        <span className={cn(
                          'w-16 text-xs font-semibold',
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
                          className="flex-1 h-1 appearance-none rounded-full cursor-pointer"
                          style={{
                            background: `linear-gradient(to right, ${key === 'facil' ? '#34d399' : key === 'media' ? '#fbbf24' : '#f87171'} ${(custom[key] / 20) * 100}%, #282828 ${(custom[key] / 20) * 100}%)`,
                          }}
                        />
                        <span className="w-6 text-right text-xs text-on-surface font-mono">{custom[key]}</span>
                      </div>
                    ))}
                    <p className="text-right text-[10px] text-on-surface-variant pt-1">
                      Total: <span className="text-on-surface font-semibold">{customTotal}</span> cards
                    </p>
                  </div>
                )}
              </div>

              {/* Quantidade */}
              {diffMode !== 'custom' && (
                <div className="space-y-5 pt-2">
                  <div className="flex justify-between items-end">
                    <label className="block text-xs font-semibold tracking-widest text-primary uppercase">
                      Quantidade
                    </label>
                    <span className="text-3xl font-headline font-extrabold text-on-surface leading-none">
                      {numCards}{' '}
                      <span className="text-xs font-normal text-on-surface-variant uppercase tracking-widest ml-1">
                        cards
                      </span>
                    </span>
                  </div>
                  <div className="relative py-2">
                    <input
                      type="range"
                      min={3}
                      max={30}
                      value={numCards}
                      onChange={e => setNumCards(Number(e.target.value))}
                      className="w-full h-1 appearance-none rounded-full cursor-pointer"
                      style={{
                        background: `linear-gradient(to right, #93C5FD ${trackPercent}%, #282828 ${trackPercent}%)`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-on-surface-variant font-bold tracking-tighter px-0.5">
                    <span>3</span>
                    <span>10</span>
                    <span>20</span>
                    <span>30</span>
                  </div>
                </div>
              )}

              {/* Error */}
              {errorMessage && (
                <div className="rounded-xl p-4" style={{ border: '1px solid rgba(217,119,6,0.3)', background: 'rgba(120,53,15,0.15)' }}>
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-amber-300">Não foi possível concluir a geração</p>
                      <p className="text-xs leading-5 text-amber-100/90">{errorMessage}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* CTA */}
              <div className="pt-2 space-y-4">
                <button
                  onClick={handleSubmit}
                  disabled={generating || !canSubmit}
                  className="w-full py-5 rounded-xl font-headline font-extrabold text-lg tracking-tight text-[#001e30] flex items-center justify-center gap-3 transition-all duration-300 hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
                  style={{
                    background: 'linear-gradient(135deg, #c5e3ff 0%, #90caf9 100%)',
                    boxShadow: '0 20px 50px rgba(197,227,255,0.15)',
                  }}
                >
                  {generating
                    ? <><Loader2 className="h-5 w-5 animate-spin" /> Gerando...</>
                    : <><Layers className="h-5 w-5" /> Gerar Flashcards {effectiveTotal > 0 ? `(${effectiveTotal})` : ''}</>
                  }
                </button>
                <p className="text-center text-xs text-on-surface-variant opacity-50">
                  Estimativa de processamento: ~45 segundos
                </p>
              </div>

            </section>

            {/* ── Right: Summary Panel (4 cols) ── */}
            <aside className="col-span-4 space-y-5 sticky top-0">

              {/* Resumo */}
              <div className="rounded-2xl p-7 relative overflow-hidden"
                style={{
                  background: '#1c1b1b',
                  borderLeft: '4px solid rgba(147,197,253,0.4)',
                }}>
                {/* Glow */}
                <div className="absolute -top-20 -right-20 w-40 h-40 rounded-full pointer-events-none"
                  style={{ background: 'radial-gradient(circle, rgba(147,197,253,0.12) 0%, transparent 70%)' }} />

                <h3 className="font-headline font-bold text-lg text-on-surface mb-6 relative z-10">
                  Resumo da Geração
                </h3>

                <div className="space-y-5 relative z-10">
                  <div className="flex items-start gap-4">
                    <div className="h-1.5 w-1.5 rounded-full bg-primary mt-2 shrink-0" />
                    <div>
                      <p className="text-sm font-bold text-on-surface">Método Heurístico</p>
                      <p className="text-xs text-on-surface-variant leading-relaxed mt-0.5">
                        Extração baseada em conceitos fundamentais e dependências de tópicos.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="h-1.5 w-1.5 rounded-full bg-primary mt-2 shrink-0" />
                    <div>
                      <p className="text-sm font-bold text-on-surface">Repetição Espaçada</p>
                      <p className="text-xs text-on-surface-variant leading-relaxed mt-0.5">
                        Metadados de retenção otimizados para recall ativo.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-8 pt-6 relative z-10"
                  style={{ borderTop: '1px solid rgba(65,71,78,0.10)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-[#f6b868] animate-pulse" />
                    <span className="text-[10px] font-bold text-[#f6b868] uppercase tracking-widest">AI Agent Ready</span>
                  </div>
                  <p className="text-xs italic text-on-surface-variant leading-relaxed">
                    "Preparado para sintetizar o conhecimento em blocos digestíveis."
                  </p>
                </div>
              </div>

              {/* Recentes */}
              {recentDecks.length > 0 && (
                <div className="rounded-2xl p-5"
                  style={{ background: '#0e0e0e', border: '1px solid rgba(65,71,78,0.15)' }}>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Recentes</span>
                    <Bot className="text-on-surface-variant w-4 h-4" />
                  </div>
                  <div className="space-y-2">
                    {recentDecks.map(deck => (
                      <div key={deck.id}
                        className="flex items-center justify-between p-2 rounded-lg hover:bg-surface-container-high transition-colors">
                        <span className="text-sm text-on-surface font-medium truncate pr-3">{deck.title}</span>
                        <span className="text-[10px] text-on-surface-variant whitespace-nowrap shrink-0">
                          {deck.card_count}c
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </aside>

          </div>
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
  const [cards] = useState<FlashcardDeck['cards']>(() => dedupeDeckCards(deck.cards))
  const [idx, setIdx] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [diffVote, setDiffVote] = useState<'agree' | 'disagree' | null>(null)
  const [correctedDiff, setCorrectedDiff] = useState<string | null>(null)
  const [userAnswer, setUserAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)

  const reviewMut = useMutation({
    mutationFn: ({ cardId, ease }: { cardId: number; ease: number }) =>
      apiClient.reviewFlashcard(cardId, ease),
    onError: () => toast.error('Erro ao registrar revisao.'),
  })

  const difficultyMut = useMutation({
    mutationFn: ({ cardId, difficulty }: { cardId: number; difficulty: string }) =>
      apiClient.updateFlashcardDifficulty(cardId, difficulty),
    onSuccess: (data) => {
      toast.success(`Dificuldade atualizada para ${DIFFICULTY_LABELS[data.difficulty] ?? data.difficulty}!`)
    },
    onError: () => toast.error('Erro ao atualizar dificuldade.'),
  })

  const evaluateMut = useMutation({
    mutationFn: ({ cardId, answer }: { cardId: number; answer: string }) =>
      apiClient.evaluateFlashcard(cardId, answer),
    onSuccess: (data) => {
      setEvaluation(data)
      setRevealed(true)
    },
    onError: () => toast.error('Erro ao avaliar resposta.'),
  })

  if (!cards.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-sm text-on-surface-variant">Este deck não tem cards.</p>
        <Button variant="ghost" size="sm" onClick={onBack} className="mt-4">Voltar</Button>
      </div>
    )
  }

  const card = cards[idx]
  const isLast = idx === cards.length - 1
  const activeDiff = correctedDiff ?? card.difficulty
  const diffLabel = DIFFICULTY_LABELS[activeDiff] ?? 'Média'

  function advanceCard() {
    setRevealed(false)
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

  const progressPct = ((idx + 1) / cards.length) * 100

  return (
    <div className="relative min-h-screen pb-36">

      {/* ── Status bar ── */}
      <div className="flex items-center justify-between mb-12">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-on-surface-variant hover:text-on-surface transition-colors text-xs font-medium mr-2"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Decks
          </button>
          <span className={cn(
            'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase font-headline border',
            activeDiff === 'facil'
              ? 'bg-emerald-950/20 text-emerald-400 border-emerald-800/40'
              : activeDiff === 'dificil'
                ? 'bg-red-950/20 text-red-400 border-red-800/40'
                : 'bg-yellow-950/20 text-yellow-400 border-yellow-800/40',
          )}>
            {diffLabel}
          </span>
          <span className="text-on-surface-variant text-xs font-medium tracking-wide hidden sm:block truncate max-w-[200px]">
            {deck.title}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="h-1 w-24 bg-surface-container-highest rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-on-surface-variant">{idx + 1}/{cards.length}</span>
        </div>
      </div>

      {/* ── Question ── */}
      <section className="mb-12">
        <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-5 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 inline-block" />
          Pergunta
        </p>
        <h2
          className="text-3xl md:text-4xl lg:text-5xl font-headline font-extrabold tracking-tighter text-on-surface leading-[1.1] mb-8"
          style={{ textShadow: '0 0 40px rgba(147,197,253,0.15)' }}
        >
          {card.front}
        </h2>
        <div className="h-[2px] w-16 rounded-full bg-primary/40" />
      </section>

      {/* ── Before reveal: textarea + buttons ── */}
      {!revealed && (
        <div className="space-y-3 mb-10">
          <textarea
            value={userAnswer}
            onChange={e => setUserAnswer(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && userAnswer.trim()) {
                e.preventDefault()
                evaluateMut.mutate({ cardId: card.id, answer: userAnswer.trim() })
              }
            }}
            placeholder="Escreva sua resposta aqui... (opcional)"
            rows={4}
            className="w-full resize-none rounded-xl px-5 py-4 text-on-surface placeholder:text-on-surface-variant/30 outline-none transition-colors text-sm leading-relaxed"
            style={{
              background: '#111111',
              border: '1px solid rgba(255,255,255,0.05)',
            }}
            onFocus={e => (e.currentTarget.style.borderColor = 'rgba(147,197,253,0.3)')}
            onBlur={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)')}
          />
          <div className="flex gap-3">
            <button
              onClick={() => setRevealed(true)}
              disabled={evaluateMut.isPending}
              className="flex-1 py-3 rounded-xl text-on-surface-variant hover:text-on-surface text-sm font-medium transition-colors"
              style={{ border: '1px solid rgba(255,255,255,0.08)' }}
            >
              Mostrar resposta
            </button>
            <button
              onClick={() => evaluateMut.mutate({ cardId: card.id, answer: userAnswer.trim() })}
              disabled={!userAnswer.trim() || evaluateMut.isPending}
              className="flex-1 py-3 rounded-xl text-primary font-semibold text-sm transition-all hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              style={{ background: 'rgba(147,197,253,0.08)', border: '1px solid rgba(147,197,253,0.2)' }}
            >
              {evaluateMut.isPending
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Avaliando...</>
                : <><Send className="h-4 w-4" /> Avaliar com IA</>
              }
            </button>
          </div>
        </div>
      )}

      {/* ── After reveal: comparison grid ── */}
      {revealed && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
            {/* Sua resposta */}
            <div className="space-y-3">
              <label className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/50 inline-block" />
                Sua resposta
              </label>
              <div className="rounded-xl px-6 py-5 min-h-[140px]"
                style={{ background: '#111111', border: '1px solid rgba(255,255,255,0.05)' }}>
                {userAnswer
                  ? <p className="text-on-surface leading-relaxed italic text-sm">"{userAnswer}"</p>
                  : <p className="text-on-surface-variant/40 text-sm italic">Sem resposta registrada.</p>
                }
              </div>
            </div>

            {/* Resposta correta */}
            <div className="space-y-3">
              <label className="text-[10px] font-bold uppercase tracking-widest text-primary flex items-center gap-2">
                <span
                  className="w-1.5 h-1.5 rounded-full bg-primary inline-block"
                  style={{ boxShadow: '0 0 8px rgba(147,197,253,0.5)' }}
                />
                Resposta correta
              </label>
              <div className="rounded-xl px-6 py-5 min-h-[140px]"
                style={{ background: '#1e1e1e', border: '1px solid rgba(147,197,253,0.1)' }}>
                <p className="text-on-surface leading-relaxed text-sm">{card.back}</p>
              </div>
            </div>
          </div>

          {/* ── AI Evaluation ── */}
          <section
            className="rounded-2xl p-8 relative overflow-hidden group mb-8"
            style={{
              background: '#050505',
              border: '1px solid rgba(147,197,253,0.06)',
              boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
            }}
          >
            {/* Decorative icon */}
            <div className="absolute top-0 right-0 p-8 opacity-[0.07] group-hover:opacity-[0.14] transition-opacity pointer-events-none">
              <Brain className="w-24 h-24 text-primary" />
            </div>

            <div className="relative z-10">
              <div className="flex items-center gap-2 mb-6">
                <Sparkles className="text-primary w-5 h-5" />
                <h3 className="font-headline font-bold text-lg tracking-tight text-primary">Análise da IA</h3>
              </div>

              {evaluation && verdictCfg ? (
                <div className="flex flex-col md:flex-row gap-8 items-start">
                  <div className="flex-1 space-y-4">
                    <p className="text-on-surface text-lg font-medium leading-snug">
                      <span className={verdictCfg.color}>{verdictCfg.icon} </span>
                      {verdictCfg.label}
                    </p>
                    <p className="text-on-surface-variant text-sm leading-relaxed">
                      {evaluation.feedback}
                    </p>
                    {evaluation.highlight && (
                      <p className="text-xs text-primary/70 leading-relaxed border-l-2 border-primary/30 pl-3">
                        {evaluation.highlight}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col gap-2 md:w-44 shrink-0">
                    <div className="rounded-lg px-3 py-2.5"
                      style={{ background: 'rgba(147,197,253,0.05)', border: '1px solid rgba(147,197,253,0.1)' }}>
                      <span className="text-[9px] uppercase tracking-tighter text-on-surface-variant block mb-1">Veredicto</span>
                      <span className={cn('text-[11px] font-mono font-bold', verdictCfg.color)}>{verdictCfg.label}</span>
                    </div>
                    {userAnswer && (
                      <div className="rounded-lg px-3 py-2.5"
                        style={{ background: 'rgba(147,197,253,0.05)', border: '1px solid rgba(147,197,253,0.1)' }}>
                        <span className="text-[9px] uppercase tracking-tighter text-on-surface-variant block mb-1">Intervalo</span>
                        <span className="text-[11px] font-mono text-primary">
                          {verdictCfg.label === 'Correta!' ? '+7d' : verdictCfg.label === 'Parcialmente correta' ? '+3d' : '+1d'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-on-surface-variant text-sm">
                    {userAnswer
                      ? 'Sua resposta foi registrada. Clique para avaliar:'
                      : 'Escreva sua resposta para receber a análise:'}
                  </p>
                  {!userAnswer && (
                    <textarea
                      value={userAnswer}
                      onChange={e => setUserAnswer(e.target.value)}
                      placeholder="Digite sua resposta aqui..."
                      rows={3}
                      className="w-full resize-none rounded-xl px-4 py-3 text-on-surface placeholder:text-on-surface-variant/30 outline-none text-sm leading-relaxed"
                      style={{ background: '#111111', border: '1px solid rgba(255,255,255,0.06)' }}
                    />
                  )}
                  <button
                    onClick={() => evaluateMut.mutate({ cardId: card.id, answer: userAnswer.trim() })}
                    disabled={!userAnswer.trim() || evaluateMut.isPending}
                    className="flex items-center gap-2 rounded-xl px-5 py-3 text-primary font-semibold text-sm transition-all hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed"
                    style={{ background: 'rgba(147,197,253,0.08)', border: '1px solid rgba(147,197,253,0.2)' }}
                  >
                    {evaluateMut.isPending
                      ? <><Loader2 className="h-4 w-4 animate-spin" /> Avaliando...</>
                      : <><Send className="h-4 w-4" /> Avaliar minha resposta →</>
                    }
                  </button>
                </div>
              )}
            </div>
          </section>

          {/* ── Difficulty vote ── */}
          <div className="rounded-xl px-4 py-3 mb-4"
            style={{ background: '#0e0e0e', border: '1px solid rgba(65,71,78,0.15)' }}>
            {diffVote === null && (
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-on-surface-variant">
                  IA classificou como <span className={cn('font-semibold', activeDiff === 'facil' ? 'text-emerald-400' : activeDiff === 'dificil' ? 'text-red-400' : 'text-yellow-400')}>{diffLabel}</span>. Concorda?
                </span>
                <div className="flex gap-1.5 shrink-0">
                  <button onClick={handleAgree}
                    className="flex items-center gap-1 rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-2.5 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-950/40 transition-colors">
                    <ThumbsUp className="h-3 w-3" /> Sim
                  </button>
                  <button onClick={handleDisagree}
                    className="flex items-center gap-1 rounded-lg border border-red-800/50 bg-red-950/20 px-2.5 py-1.5 text-xs font-medium text-red-400 hover:bg-red-950/40 transition-colors">
                    <ThumbsDown className="h-3 w-3" /> Não
                  </button>
                </div>
              </div>
            )}
            {diffVote === 'agree' && (
              <p className="text-xs text-on-surface-variant/60 text-center">
                ✓ Dificuldade <span className={cn('font-semibold', activeDiff === 'facil' ? 'text-emerald-400' : activeDiff === 'dificil' ? 'text-red-400' : 'text-yellow-400')}>{diffLabel}</span> confirmada.
              </p>
            )}
            {diffVote === 'disagree' && (
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-on-surface-variant">Qual a dificuldade correta?</span>
                <div className="flex gap-1.5">
                  {(['facil', 'media', 'dificil'] as const).map(d => (
                    <button key={d} onClick={() => handleCorrectDiff(d)} disabled={difficultyMut.isPending}
                      className={cn('rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                        DIFFICULTY_STYLES[d], d === card.difficulty && 'opacity-40 cursor-default')}>
                      {DIFFICULTY_LABELS[d]}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Fixed bottom ease buttons (only after reveal) ── */}
      {revealed && (
        <div className="fixed bottom-0 left-0 right-0 z-50 md:pl-64"
          style={{ background: 'linear-gradient(to top, rgba(10,10,10,0.98) 60%, transparent)' }}>
          <div className="max-w-4xl mx-auto px-4 md:px-8 pb-6 pt-4">
            <div className="flex gap-3">
              <button
                onClick={() => handleRate(1)}
                className="flex-1 flex flex-col items-center py-4 rounded-xl transition-all active:scale-95 hover:brightness-110"
                style={{ background: 'rgba(147,0,10,0.15)', border: '1px solid rgba(255,180,171,0.2)' }}
              >
                <span className="text-[10px] font-bold uppercase tracking-widest text-red-400/90 mb-1">Difícil</span>
                <span className="text-[10px] font-mono text-on-surface-variant">+1d</span>
              </button>
              <button
                onClick={() => handleRate(2)}
                className="flex-1 flex flex-col items-center py-4 rounded-xl transition-all active:scale-95 hover:brightness-110"
                style={{ background: 'rgba(246,184,104,0.08)', border: '1px solid rgba(246,184,104,0.2)' }}
              >
                <span className="text-[10px] font-bold uppercase tracking-widest text-[#f6b868]/90 mb-1">Bom</span>
                <span className="text-[10px] font-mono text-on-surface-variant">+3d</span>
              </button>
              <button
                onClick={() => handleRate(3)}
                className="flex-1 flex flex-col items-center py-4 rounded-xl transition-all active:scale-95 hover:brightness-110"
                style={{ background: 'rgba(147,197,253,0.08)', border: '1px solid rgba(147,197,253,0.2)' }}
              >
                <span className="text-[10px] font-bold uppercase tracking-widest text-primary/90 mb-1">Fácil</span>
                <span className="text-[10px] font-mono text-on-surface-variant">+7d</span>
              </button>
            </div>
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
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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

  // ── Study mode ─────────────────────────────────────────────────────────────
  if (studyDeckId !== null && studyDeck) {
    return (
      <div className="max-w-4xl mx-auto">
        <StudySession key={studyDeck.id} deck={studyDeck} onBack={() => setStudyDeckId(null)} />
      </div>
    )
  }

  // ── Main view ──────────────────────────────────────────────────────────────
  return (
    <div className="relative min-h-screen">

      {/* Decorative background blobs */}
      <div className="fixed top-0 right-0 -z-10 w-[600px] h-[600px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(147,197,253,0.06) 0%, transparent 70%)',
          transform: 'translate(50%, -50%)',
        }} />
      <div className="fixed bottom-0 left-0 -z-10 w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(8,32,50,0.3) 0%, transparent 70%)',
          transform: 'translate(-50%, 50%)',
        }} />

      <div className="px-8 py-10 max-w-7xl mx-auto">

        {/* ── Hero section ── */}
        <section className="flex flex-col md:flex-row md:items-end justify-between gap-8 mb-16">
          <div className="max-w-2xl">
            <span className="text-primary font-bold tracking-widest text-xs uppercase mb-3 block">
              Seus Flashcards
            </span>
            <h1 className="text-4xl md:text-5xl font-headline font-extrabold text-on-surface leading-tight tracking-tighter">
              Estude melhor, lembre mais.
            </h1>
            <p className="mt-5 text-on-surface-variant text-lg leading-relaxed max-w-xl">
              Crie cartões de estudo a partir dos seus documentos e revise no seu ritmo. A IA gera as perguntas — você só precisa responder.
            </p>
          </div>

          <button
            onClick={() => { setGenerateError(null); setShowGenerate(true) }}
            disabled={docs.length === 0}
            className="flex items-center gap-3 font-headline font-bold py-4 px-8 rounded-xl transition-all duration-300 hover:scale-[1.02] active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 shrink-0 text-[#001e30]"
            style={{
              background: 'linear-gradient(135deg, #c5e3ff 0%, #90caf9 100%)',
              boxShadow: '0 20px 50px rgba(197,227,255,0.12)',
            }}
          >
            <Plus className="w-5 h-5" />
            Gerar Novo Deck
          </button>
        </section>

        {/* ── Deck grid ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

          {/* Loading skeletons */}
          {isLoading && [1, 2, 3].map(i => (
            <div key={i} className="h-64 rounded-xl animate-pulse" style={{ background: '#111111' }} />
          ))}

          {/* Deck cards */}
          {!isLoading && decks.map(deck => (
            <div
              key={deck.id}
              className="group relative rounded-xl p-6 transition-all duration-300 cursor-pointer flex flex-col justify-between h-64 overflow-hidden"
              style={{ background: '#111111' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#1e1e1e')}
              onMouseLeave={e => (e.currentTarget.style.background = '#111111')}
              onClick={() => setStudyDeckId(deck.id)}
            >
              {/* Decorative bg icon */}
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity pointer-events-none">
                <Layers className="w-20 h-20 text-on-surface" />
              </div>

              <div className="relative z-10">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider"
                    style={{ background: 'rgba(147,197,253,0.1)', color: '#93C5FD' }}>
                    AI Generated
                  </span>
                  <span className="text-on-surface-variant text-xs">{formatDeckDate(deck.created_at)}</span>
                </div>

                <h4 className="text-xl font-headline font-bold text-on-surface group-hover:text-primary transition-colors leading-snug">
                  {deck.title}
                </h4>
                <p className="text-on-surface-variant text-sm mt-2 line-clamp-2 leading-relaxed">
                  {deck.source_doc}
                </p>
              </div>

              <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-2">
                  <Layers className="text-primary w-5 h-5" />
                  <span className="text-on-surface font-semibold text-sm">{deck.card_count} cards</span>
                </div>
                <div className="h-8 w-8 rounded-full flex items-center justify-center transition-all duration-300 group-hover:text-[#001e30]"
                  style={{ background: '#282828' }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = '#93C5FD'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = '#282828'
                  }}>
                  <ArrowRight className="w-4 h-4" />
                </div>
              </div>

              {/* Delete button */}
              <button
                onClick={e => { e.stopPropagation(); deleteMut.mutate(deck.id) }}
                className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-on-surface-variant hover:text-red-400 transition-all p-1 rounded"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}

          {/* Empty state / CTA card */}
          {!isLoading && (
            <div
              onClick={() => { if (docs.length > 0) { setGenerateError(null); setShowGenerate(true) } }}
              className={cn(
                'rounded-xl flex flex-col items-center justify-center p-8 h-64 text-on-surface-variant transition-all group',
                docs.length > 0
                  ? 'cursor-pointer hover:text-on-surface'
                  : 'cursor-not-allowed opacity-50',
              )}
              style={{ border: '2px dashed rgba(65,71,78,0.2)' }}
              onMouseEnter={e => { if (docs.length > 0) (e.currentTarget.style.borderColor = 'rgba(147,197,253,0.4)') }}
              onMouseLeave={e => { (e.currentTarget.style.borderColor = 'rgba(65,71,78,0.2)') }}
            >
              <Plus className="w-10 h-10 mb-4 group-hover:scale-110 transition-transform" />
              <span className="font-headline font-bold text-center">
                {decks.length === 0 ? 'Gere seu primeiro deck' : 'Nova coleção'}
              </span>
              <span className="text-xs text-center mt-2 opacity-60 leading-relaxed">
                {docs.length === 0
                  ? 'Insira documentos primeiro\npara gerar flashcards.'
                  : 'Selecione um documento e\nconfigure o algoritmo.'}
              </span>
            </div>
          )}

        </div>
      </div>

      {/* ── Generate dialog ── */}
      {showGenerate && (
        <GenerateDialog
          docs={docs}
          decks={decks}
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

    </div>
  )
}
