import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  GraduationCap,
  Sparkles,
  Zap,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageShell } from '@/components/ui/page-shell'
import { apiClient, type DocItem, type GapAnalysisResponse, type ReadingStatus } from '@/api/client'
import { cn } from '@/lib/utils'

type ColumnConfig = {
  key: ReadingStatus
  label: string
  dotClass: string
  labelClass: string
  badgeClass: string
  columnClass: string
}

const COLUMNS: ColumnConfig[] = [
  {
    key: 'to_read',
    label: 'Para Ler',
    dotClass: 'bg-[color:var(--ui-text-meta)]',
    labelClass: 'text-[color:var(--ui-text-dim)]',
    badgeClass: 'bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text-dim)]',
    columnClass: 'bg-[color:var(--ui-surface-1)] border border-[color:var(--ui-border-soft)]',
  },
  {
    key: 'reading',
    label: 'Lendo',
    dotClass: 'bg-[color:var(--ui-accent)]',
    labelClass: 'text-[color:var(--ui-accent)]',
    badgeClass: 'bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
    columnClass: 'bg-[color:var(--ui-bg-alt)] ring-1 ring-[color:var(--ui-accent)]/30',
  },
  {
    key: 'done',
    label: 'Lido',
    dotClass: 'bg-[color:var(--ui-warning)]',
    labelClass: 'text-[color:var(--ui-warning)]',
    badgeClass: 'bg-[color:var(--ui-warning)]/20 text-[color:var(--ui-warning)]',
    columnClass: 'bg-[color:var(--ui-surface-1)] border border-[color:var(--ui-border-soft)]',
  },
]

function compactDocId(docId: string) {
  if (!docId) return 'N/A'
  return docId.length <= 10 ? docId.toUpperCase() : docId.slice(0, 10).toUpperCase()
}

function parseErrorMessage(error: unknown, fallback: string) {
  if (!error || typeof error !== 'object') return fallback
  const maybeResponse = (error as { response?: { data?: { detail?: unknown } } }).response
  const detail = maybeResponse?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function progressByStatus(status: ReadingStatus) {
  if (status === 'done') return 100
  if (status === 'reading') return 54
  return 0
}

function GapAnalysisModal({ onClose }: { onClose: () => void }) {
  const [result, setResult] = useState<GapAnalysisResponse | null>(null)

  const mutation = useMutation({
    mutationFn: () => apiClient.runGapAnalysis([]),
    onSuccess: data => setResult(data),
    onError: error => toast.error(parseErrorMessage(error, 'Erro na analise de gaps.')),
  })

  function priorityClasses(priority: string) {
    if (priority === 'high') return 'border-[#7f2f33] bg-[#3b181b] text-[#ffb4ab]'
    if (priority === 'low') return 'border-[#41474e] bg-[#202426] text-[#c1c7cf]'
    return 'border-[#6f5a2a] bg-[#332b1c] text-[#ffd9ae]'
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[#41474e] bg-[#131313] shadow-[0_24px_48px_rgba(0,0,0,0.48)]">
        <header className="flex items-center justify-between border-b border-[#41474e]/45 px-6 py-4">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-[#ffd9ae]" />
            <h2 className="font-headline text-lg font-bold text-[#e5e2e1]">Analise de Gaps</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#8b9199] transition-colors hover:bg-[#2a2a2a] hover:text-[#e5e2e1]"
            aria-label="Fechar analise de gaps"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {!result && !mutation.isPending && (
            <div className="rounded-xl bg-[#1c1b1b] p-5 text-center">
              <p className="text-sm leading-relaxed text-[#c1c7cf]">
                O agente verifica lacunas entre documentos, tarefas e revisoes para sugerir proximos estudos.
              </p>
              <Button
                onClick={() => mutation.mutate()}
                className="mt-4 h-10 rounded-lg border-0 bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] text-[#03263b] hover:from-[#d6edff] hover:to-[#a6d4fb]"
              >
                Executar analise
              </Button>
            </div>
          )}

          {mutation.isPending && (
            <div className="space-y-3">
              {[1, 2, 3].map(item => <Skeleton key={item} className="h-20 w-full rounded-xl bg-[#2a2a2a]" />)}
              <p className="text-center text-xs uppercase tracking-[0.12em] text-[#8b9199]">Analisando lacunas...</p>
            </div>
          )}

          {result && (
            <div className="space-y-3">
              <p className="text-xs text-[#8b9199]">
                {result.docs_analyzed} documento(s) analisado(s) · {result.gaps.length} gap(s) identificado(s)
              </p>

              {result.gaps.length === 0 ? (
                <div className="rounded-xl border border-[#386445] bg-[#1b2a21] p-4 text-center">
                  <CheckCircle2 className="mx-auto mb-2 h-6 w-6 text-[#8ad6a0]" />
                  <p className="text-sm font-semibold text-[#b6e6c7]">Nenhuma lacuna relevante encontrada.</p>
                </div>
              ) : (
                result.gaps.map((gap, index) => (
                  <article key={`${gap.topico}-${index}`} className={cn('rounded-xl border p-4', priorityClasses(gap.prioridade))}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-[#e5e2e1]">{gap.topico}</h3>
                      <span className="rounded-full border border-current/35 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em]">
                        {gap.prioridade}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-[#c1c7cf]">{gap.descricao}</p>
                    <p className="mt-2 border-t border-current/20 pt-2 text-xs text-[#aab2bc]">
                      Sugestao: {gap.sugestao}
                    </p>
                  </article>
                ))
              )}

              <Button
                variant="outline"
                onClick={() => {
                  mutation.reset()
                  setResult(null)
                }}
                className="border-[#41474e] bg-[#1c1b1b] text-[#e5e2e1] hover:border-[#90caf9]/50 hover:bg-[#252525]"
              >
                Reexecutar
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BoardCard({
  doc,
  status,
  onMove,
  disabled,
}: {
  doc: DocItem
  status: ReadingStatus
  onMove: (direction: 'prev' | 'next') => void
  disabled: boolean
}) {
  const columnIndex = COLUMNS.findIndex(column => column.key === status)
  const progress = progressByStatus(status)
  const isReading = status === 'reading'
  const isDone = status === 'done'

  return (
    <article className={cn(
      'group rounded-xl border-l-4 p-4 transition-all duration-200',
      isReading
        ? 'border-l-[#90caf9] bg-[#2a2a2a] shadow-[0_18px_30px_rgba(0,0,0,0.32)]'
        : isDone
          ? 'border-l-[#ffd9ae]/60 bg-[#1c1b1b] opacity-80'
          : 'border-l-transparent bg-[#1c1b1b] hover:bg-[#262626]',
    )}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <span className="rounded-md bg-[#0e0e0e] px-2 py-1 text-[10px] font-mono text-[#8b9199]">
          ID: {compactDocId(doc.doc_id)}
        </span>
        {isDone ? <CheckCircle2 className="h-4 w-4 text-[#ffd9ae]" /> : isReading ? <BookOpen className="h-4 w-4 text-[#c5e3ff]" /> : <FileText className="h-4 w-4 text-[#8b9199]" />}
      </div>

      <h4 className={cn('font-headline text-base font-bold leading-tight', isReading ? 'text-[#c5e3ff]' : 'text-[#e5e2e1]')}>
        {doc.file_name}
      </h4>

      <div className="mt-3 space-y-2">
        <div className="flex items-center gap-3 text-xs text-[#aab2bc]">
          <span>{isDone ? 'Leitura concluida' : isReading ? 'Leitura em andamento' : 'Pronto para leitura'}</span>
        </div>

        {status !== 'to_read' && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.08em] text-[#8b9199]">
              <span>Progresso</span>
              <span>{progress}%</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-[#131313]">
              <div
                className={cn('h-full rounded-full', isDone ? 'bg-[#ffd9ae]' : 'bg-[#90caf9]')}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center gap-1">
        <button
          type="button"
          onClick={() => onMove('prev')}
          disabled={disabled || columnIndex <= 0}
          className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#8b9199] transition-colors hover:bg-[#353534] hover:text-[#e5e2e1] disabled:opacity-30"
          title="Mover para coluna anterior"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onMove('next')}
          disabled={disabled || columnIndex >= COLUMNS.length - 1}
          className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#8b9199] transition-colors hover:bg-[#353534] hover:text-[#e5e2e1] disabled:opacity-30"
          title="Mover para proxima coluna"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </article>
  )
}

export function ReadingKanban() {
  const queryClient = useQueryClient()
  const [gapOpen, setGapOpen] = useState(false)

  const { data: docs = [], isLoading: docsLoading } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const { data: statusMap = {}, isLoading: statusLoading } = useQuery<Record<string, ReadingStatus>>({
    queryKey: ['reading-status'],
    queryFn: apiClient.getReadingStatus,
  })

  const moveMutation = useMutation({
    mutationFn: ({ docId, status }: { docId: string; status: ReadingStatus }) =>
      apiClient.updateReadingStatus(docId, status),
    onMutate: async ({ docId, status }) => {
      await queryClient.cancelQueries({ queryKey: ['reading-status'] })
      const previous = queryClient.getQueryData<Record<string, ReadingStatus>>(['reading-status']) ?? {}
      queryClient.setQueryData<Record<string, ReadingStatus>>(['reading-status'], {
        ...previous,
        [docId]: status,
      })
      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['reading-status'], context.previous)
      }
      toast.error('Erro ao mover documento.')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['reading-status'] })
    },
  })

  const isLoading = docsLoading || statusLoading

  const grouped = useMemo(() => {
    const result: Record<ReadingStatus, DocItem[]> = {
      to_read: [],
      reading: [],
      done: [],
    }

    for (const doc of docs) {
      const status = statusMap[doc.doc_id] ?? 'to_read'
      result[status].push(doc)
    }

    return result
  }, [docs, statusMap])

  const counts = useMemo(() => ({
    to_read: grouped.to_read.length,
    reading: grouped.reading.length,
    done: grouped.done.length,
  }), [grouped.to_read.length, grouped.reading.length, grouped.done.length])

  const totalDocs = docs.length
  const donePercentage = totalDocs > 0 ? Math.round((counts.done / totalDocs) * 100) : 0

  function moveDoc(docId: string, currentStatus: ReadingStatus, direction: 'prev' | 'next') {
    const currentIndex = COLUMNS.findIndex(column => column.key === currentStatus)
    const nextIndex = direction === 'next' ? currentIndex + 1 : currentIndex - 1
    if (nextIndex < 0 || nextIndex >= COLUMNS.length) return

    moveMutation.mutate({
      docId,
      status: COLUMNS[nextIndex].key,
    })
  }

  return (
    <>
      <PageShell className="space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-5 app-divider">
          <div>
            <h1 className="font-headline text-3xl font-extrabold tracking-tight text-[color:var(--ui-text)]">Kanban de Leitura</h1>
            <p className="mt-1 text-sm text-[color:var(--ui-text-dim)]">
              {isLoading ? 'Carregando board...' : `${counts.done} de ${totalDocs} documentos concluidos · ${donePercentage}%`}
            </p>
          </div>

          <Button
            onClick={() => setGapOpen(true)}
            className="h-10 gap-2 rounded-xl border-0 bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]"
          >
            <Zap className="h-4 w-4" />
            Analise de Gaps
          </Button>
        </header>

        {!isLoading && totalDocs > 0 && (
          <section className="app-surface p-4">
            <div className="mb-2 flex items-center justify-between text-xs text-[color:var(--ui-text-dim)]">
              <span className="inline-flex items-center gap-1">
                <GraduationCap className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
                Progresso global
              </span>
              <span>{counts.done} / {totalDocs}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[color:var(--ui-bg-alt)]">
              <div className="h-full rounded-full bg-[color:var(--ui-accent)]" style={{ width: `${donePercentage}%` }} />
            </div>
          </section>
        )}

        <section>
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {COLUMNS.map(column => (
                <div key={column.key} className="space-y-3 rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] p-4">
                  <Skeleton className="h-6 w-36 rounded-lg bg-[color:var(--ui-surface-3)]" />
                  {[1, 2].map(item => (
                    <Skeleton key={item} className="h-36 w-full rounded-xl bg-[color:var(--ui-surface-3)]" />
                  ))}
                </div>
              ))}
            </div>
          ) : totalDocs === 0 ? (
            <div className="app-surface p-10 text-center">
              <FileText className="mx-auto mb-3 h-9 w-9 text-[color:var(--ui-text-meta)]" />
              <p className="font-headline text-xl font-bold text-[color:var(--ui-text)]">Nenhum documento disponivel</p>
              <p className="mt-1 text-sm text-[color:var(--ui-text-meta)]">Adicione arquivos em Insercao para iniciar seu kanban de leitura.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
              {COLUMNS.map(column => {
                const columnDocs = grouped[column.key]
                return (
                  <section
                    key={column.key}
                    className={cn('flex min-w-0 flex-col rounded-2xl p-4', column.columnClass)}
                  >
                    <header className="mb-4 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={cn('h-1.5 w-1.5 rounded-full', column.dotClass)} />
                        <h2 className={cn('font-headline text-xs font-bold uppercase tracking-[0.16em]', column.labelClass)}>
                          {column.label}
                        </h2>
                      </div>
                      <span className={cn('rounded-md px-2 py-1 text-[11px] font-mono', column.badgeClass)}>
                        {columnDocs.length}
                      </span>
                    </header>

                    <div className="flex-1 space-y-3 overflow-y-auto pr-1">
                      {columnDocs.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-[color:var(--ui-border)]/70 p-6 text-center text-xs text-[color:var(--ui-text-meta)]">
                          Coluna vazia
                        </div>
                      ) : (
                        columnDocs.map(doc => (
                          <BoardCard
                            key={doc.doc_id}
                            doc={doc}
                            status={column.key}
                            disabled={moveMutation.isPending}
                            onMove={direction => moveDoc(doc.doc_id, column.key, direction)}
                          />
                        ))
                      )}
                    </div>
                  </section>
                )
              })}
            </div>
          )}
        </section>

        <div className="app-surface p-4">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[color:var(--ui-warning)] shadow-[0_0_8px_rgba(212,168,108,0.7)] animate-pulse" />
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[color:var(--ui-warning)]">System intelligence ativo</span>
            <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-[color:var(--ui-text-meta)]">
              <Sparkles className="h-3 w-3 text-[color:var(--ui-accent)]" />
              leitura sincronizada
            </span>
          </div>
        </div>
      </PageShell>

      {gapOpen && <GapAnalysisModal onClose={() => setGapOpen(false)} />}
    </>
  )
}
