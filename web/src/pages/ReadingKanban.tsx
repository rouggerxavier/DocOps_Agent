import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileText, BookOpen, CheckCircle2, Clock, ChevronRight, ChevronLeft, GraduationCap, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type DocItem, type ReadingStatus, type GapAnalysisResponse } from '@/api/client'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────────────────────────

type Column = { key: ReadingStatus; label: string; icon: React.ComponentType<{ className?: string }>; color: string; bg: string }

const COLUMNS: Column[] = [
  { key: 'to_read',  label: 'Para Ler',   icon: Clock,        color: 'text-zinc-400',   bg: 'bg-zinc-800/50' },
  { key: 'reading',  label: 'Lendo',      icon: BookOpen,     color: 'text-blue-400',   bg: 'bg-blue-950/30' },
  { key: 'done',     label: 'Lido',       icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-950/30' },
]

// ── Gap Analysis Modal ─────────────────────────────────────────────────────────

function GapAnalysisModal({ onClose }: { onClose: () => void }) {
  const [result, setResult] = useState<GapAnalysisResponse | null>(null)

  const mutation = useMutation({
    mutationFn: () => apiClient.runGapAnalysis([]),
    onSuccess: data => setResult(data),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro na análise'),
  })

  const priColor = (p: string) =>
    p === 'high' ? 'text-red-400 border-red-800/60 bg-red-950/20'
    : p === 'low' ? 'text-zinc-500 border-zinc-800 bg-zinc-900'
    : 'text-yellow-400 border-yellow-800/60 bg-yellow-950/20'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-amber-400" />
            <h2 className="font-semibold text-zinc-100">Análise de Gaps</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-xl leading-none">×</button>
        </div>

        <div className="overflow-y-auto flex-1 p-6 space-y-4">
          {!result && !mutation.isPending && (
            <div className="text-center space-y-3">
              <p className="text-sm text-zinc-400">
                O agente analisa seus documentos, flashcards e tarefas para identificar tópicos que você ainda não cobriu.
              </p>
              <Button onClick={() => mutation.mutate()} className="gap-2">
                <Zap className="h-4 w-4" /> Analisar agora
              </Button>
            </div>
          )}

          {mutation.isPending && (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
              <p className="text-center text-xs text-zinc-500 animate-pulse">Analisando gaps de aprendizado...</p>
            </div>
          )}

          {result && (
            <>
              <p className="text-xs text-zinc-500">
                {result.docs_analyzed} documento(s) analisado(s) · {result.gaps.length} gaps encontrado(s)
              </p>
              {result.gaps.length === 0 && (
                <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4 text-center">
                  <CheckCircle2 className="mx-auto h-6 w-6 text-emerald-400 mb-2" />
                  <p className="text-sm text-emerald-300 font-medium">Nenhum gap identificado!</p>
                  <p className="text-xs text-zinc-500 mt-1">Seus documentos parecem bem cobertos por flashcards e tarefas.</p>
                </div>
              )}
              {result.gaps.map((gap, i) => (
                <div key={i} className={cn('rounded-lg border p-4 space-y-1.5', priColor(gap.prioridade))}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-zinc-100 text-sm">{gap.topico}</p>
                    <span className={cn('text-[10px] font-semibold uppercase rounded-full px-2 py-0.5 border', priColor(gap.prioridade))}>
                      {gap.prioridade}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400">{gap.descricao}</p>
                  <p className="text-xs text-zinc-500 border-t border-zinc-800 pt-1.5">
                    💡 {gap.sugestao}
                  </p>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => { setResult(null); mutation.reset() }}>
                Analisar novamente
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Doc Card ──────────────────────────────────────────────────────────────────

function DocCard({
  doc,
  status,
  onMove,
}: {
  doc: DocItem
  status: ReadingStatus
  onMove: (dir: 'prev' | 'next') => void
}) {
  const colIdx = COLUMNS.findIndex(c => c.key === status)

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 space-y-2 group">
      <div className="flex items-start gap-2 min-w-0">
        <FileText className="h-4 w-4 shrink-0 text-zinc-500 mt-0.5" />
        <p className="text-sm font-medium text-zinc-100 leading-snug truncate flex-1" title={doc.file_name}>
          {doc.file_name}
        </p>
      </div>
      <p className="text-[10px] text-zinc-600">{doc.chunk_count} chunks</p>
      <div className="flex items-center gap-1 pt-1">
        <button
          onClick={() => onMove('prev')}
          disabled={colIdx === 0}
          className="rounded p-1 text-zinc-600 hover:text-zinc-300 disabled:opacity-20 transition-colors"
          title="Mover para coluna anterior"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => onMove('next')}
          disabled={colIdx === COLUMNS.length - 1}
          className="rounded p-1 text-zinc-600 hover:text-zinc-300 disabled:opacity-20 transition-colors"
          title="Mover para próxima coluna"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function ReadingKanban() {
  const qc = useQueryClient()
  const [gapOpen, setGapOpen] = useState(false)

  const { data: docs = [], isLoading: docsLoading } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const { data: statusMap = {}, isLoading: statusLoading } = useQuery<Record<string, ReadingStatus>>({
    queryKey: ['reading-status'],
    queryFn: apiClient.getReadingStatus,
  })

  const moveMut = useMutation({
    mutationFn: ({ docId, status }: { docId: string; status: ReadingStatus }) =>
      apiClient.updateReadingStatus(docId, status),
    onSuccess: ({ doc_id, status }) => {
      qc.setQueryData<Record<string, ReadingStatus>>(['reading-status'], old => ({
        ...old,
        [doc_id]: status,
      }))
    },
    onError: () => toast.error('Erro ao mover documento'),
  })

  const isLoading = docsLoading || statusLoading

  // Distribui docs pelas colunas (default: to_read)
  const byStatus: Record<ReadingStatus, DocItem[]> = { to_read: [], reading: [], done: [] }
  for (const doc of docs) {
    const s = statusMap[doc.doc_id] ?? 'to_read'
    byStatus[s].push(doc)
  }

  function moveDoc(docId: string, currentStatus: ReadingStatus, dir: 'prev' | 'next') {
    const colIdx = COLUMNS.findIndex(c => c.key === currentStatus)
    const newIdx = dir === 'next' ? colIdx + 1 : colIdx - 1
    if (newIdx < 0 || newIdx >= COLUMNS.length) return
    moveMut.mutate({ docId, status: COLUMNS[newIdx].key })
  }

  const counts = { to_read: byStatus.to_read.length, reading: byStatus.reading.length, done: byStatus.done.length }

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Kanban de Leitura</h1>
            <p className="mt-0.5 text-sm text-zinc-500">
              {isLoading ? 'Carregando...' : `${docs.length} documentos · ${counts.done} lidos`}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setGapOpen(true)}
            className="gap-2 border-amber-800/60 text-amber-400 hover:text-amber-300 hover:bg-amber-950/30"
          >
            <Zap className="h-4 w-4" /> Análise de Gaps
          </Button>
        </div>

        {/* Progresso */}
        {!isLoading && docs.length > 0 && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 flex items-center gap-4">
            <div className="flex-1 space-y-1">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>{counts.done} de {docs.length} lidos</span>
                <span>{Math.round((counts.done / docs.length) * 100)}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800">
                <div
                  className="h-1.5 rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${(counts.done / docs.length) * 100}%` }}
                />
              </div>
            </div>
            <GraduationCap className="h-5 w-5 text-zinc-600 shrink-0" />
          </div>
        )}

        {/* Kanban columns */}
        {isLoading ? (
          <div className="grid grid-cols-3 gap-4">
            {COLUMNS.map(col => (
              <div key={col.key} className="space-y-3">
                <Skeleton className="h-8 w-full" />
                {[1, 2].map(i => <Skeleton key={i} className="h-20 w-full" />)}
              </div>
            ))}
          </div>
        ) : docs.length === 0 ? (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-8 text-center">
            <FileText className="mx-auto h-8 w-8 text-zinc-600 mb-3" />
            <p className="text-sm text-zinc-400 font-medium">Nenhum documento inserido ainda</p>
            <p className="text-xs text-zinc-600 mt-1">Insira documentos na página de Inserção para gerenciar sua leitura aqui.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {COLUMNS.map(col => {
              const Icon = col.icon
              const colDocs = byStatus[col.key]
              return (
                <div key={col.key} className={cn('rounded-xl border border-zinc-800 p-4 space-y-3', col.bg)}>
                  {/* Column header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className={cn('h-4 w-4', col.color)} />
                      <span className={cn('text-sm font-semibold', col.color)}>{col.label}</span>
                    </div>
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
                      {colDocs.length}
                    </span>
                  </div>

                  {/* Cards */}
                  <div className="space-y-2 min-h-[80px]">
                    {colDocs.map(doc => (
                      <DocCard
                        key={doc.doc_id}
                        doc={doc}
                        status={col.key}
                        onMove={dir => moveDoc(doc.doc_id, col.key, dir)}
                      />
                    ))}
                    {colDocs.length === 0 && (
                      <p className="text-center text-xs text-zinc-700 py-4">Vazio</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {gapOpen && <GapAnalysisModal onClose={() => setGapOpen(false)} />}
    </>
  )
}
