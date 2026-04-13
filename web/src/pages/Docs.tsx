import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { toast } from 'sonner'
import { Brain, Database, Eye, FileText, GitCompare, GraduationCap, Loader2, Search, Trash2, X, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { api, apiClient, type DocItem } from '@/api/client'
import { cn } from '@/lib/utils'

function parseErrorMessage(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function fileAccent(fileName: string) {
  const lower = fileName.toLowerCase()
  if (lower.endsWith('.pdf')) return 'text-[#90caf9]'
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'text-[#ffd9ae]'
  if (lower.endsWith('.xlsx') || lower.endsWith('.csv')) return 'text-[#b4c9de]'
  return 'text-[#c1c7cf]'
}

function formatChunkCount(count: number) {
  if (count < 1000) return String(count)
  const value = count >= 1_000_000 ? `${(count / 1_000_000).toFixed(1)}M` : `${(count / 1000).toFixed(1)}k`
  return value.replace('.0', '')
}

function CompareDialog({ doc1, docs, onClose }: { doc1: string; docs: DocItem[]; onClose: () => void }) {
  const [doc2, setDoc2] = useState('')
  const [result, setResult] = useState('')
  const compareMut = useMutation({
    mutationFn: () => apiClient.compare(doc1, doc2, false),
    onSuccess: data => setResult(data.answer),
    onError: error => toast.error(parseErrorMessage(error, 'Erro ao comparar documentos.')),
  })
  const options = docs.filter(doc => doc.file_name !== doc1)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[86vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-[#41474e] bg-[#131313]">
        <div className="flex items-center justify-between border-b border-[#41474e]/45 px-5 py-4">
          <p className="truncate font-headline text-lg font-bold text-[#e5e2e1]">Comparar: {doc1}</p>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-[#8b9199] hover:bg-[#2a2a2a]"><X className="h-4 w-4" /></button>
        </div>
        <div className="space-y-4 p-5">
          {!result ? (
            <>
              <select value={doc2} onChange={event => setDoc2(event.target.value)} className="h-11 w-full rounded-xl border border-[#41474e] bg-[#1c1b1b] px-3 text-sm text-[#e5e2e1]">
                <option value="">Selecione um documento</option>
                {options.map(doc => <option key={doc.doc_id} value={doc.file_name}>{doc.file_name}</option>)}
              </select>
              <Button onClick={() => compareMut.mutate()} disabled={!doc2 || compareMut.isPending} className="h-10 w-full rounded-lg border-0 bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] text-[#03263b]">
                {compareMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompare className="h-4 w-4" />}
                <span>{compareMut.isPending ? 'Comparando...' : 'Comparar'}</span>
              </Button>
            </>
          ) : (
            <div className="prose prose-invert prose-sm max-h-[52vh] max-w-none overflow-y-auto rounded-xl bg-[#1c1b1b] p-4">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SmartOpsDialog({ doc, onClose }: { doc: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [result, setResult] = useState('')
  const [hoursPerDay, setHoursPerDay] = useState(2)
  const [deadlineDate, setDeadlineDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 14); return d.toISOString().split('T')[0]
  })
  const digestMut = useMutation({
    mutationFn: () => apiClient.digestDocument(doc, { generateFlashcards: true, extractTasks: true, numCards: 10, maxTasks: 8, scheduleReviews: false }),
    onSuccess: data => {
      setResult(data.summary)
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      toast.success('Smart Digest concluido.')
    },
    onError: error => toast.error(parseErrorMessage(error, 'Erro no Smart Digest.')),
  })
  const planMut = useMutation({
    mutationFn: () => apiClient.createStudyPlanFromDoc(doc, hoursPerDay, deadlineDate, true, 15),
    onSuccess: data => {
      setResult(data.plan_text)
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['reminders'] })
      qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      toast.success('Plano de estudos criado.')
    },
    onError: error => toast.error(parseErrorMessage(error, 'Erro ao criar plano de estudos.')),
  })
  const isPending = digestMut.isPending || planMut.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[86vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-[#41474e] bg-[#131313]">
        <div className="flex items-center justify-between border-b border-[#41474e]/45 px-5 py-4">
          <p className="truncate font-headline text-lg font-bold text-[#e5e2e1]">{doc}</p>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-[#8b9199] hover:bg-[#2a2a2a]"><X className="h-4 w-4" /></button>
        </div>
        <div className="space-y-3 p-5">
          {!result && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Button onClick={() => digestMut.mutate()} disabled={isPending} className="h-10 rounded-lg border-0 bg-gradient-to-r from-[#ffd9ae] to-[#f6b868] text-[#402300]">
                  <Brain className="h-4 w-4" />
                  Smart Digest
                </Button>
                <Button onClick={() => planMut.mutate()} disabled={isPending || !deadlineDate} className="h-10 rounded-lg border-0 bg-gradient-to-r from-[#8ad6a0] to-[#6bbf84] text-[#0f2a19]">
                  <GraduationCap className="h-4 w-4" />
                  Plano de Estudos
                </Button>
              </div>
              <div className="rounded-xl bg-[#1c1b1b] p-3">
                <p className="mb-1 text-xs text-[#aab2bc]">Horas por dia: {hoursPerDay}h</p>
                <input type="range" min={0.5} max={8} step={0.5} value={hoursPerDay} onChange={event => setHoursPerDay(Number(event.target.value))} className="w-full accent-[#8ad6a0]" />
              </div>
              <input type="date" value={deadlineDate} min={new Date(Date.now() + 86400000).toISOString().split('T')[0]} onChange={event => setDeadlineDate(event.target.value)} className="h-11 w-full rounded-xl border border-[#41474e] bg-[#1c1b1b] px-3 text-sm text-[#e5e2e1]" />
            </>
          )}
          {isPending && (
            <div className="flex flex-col items-center gap-2 py-6 text-[#c1c7cf]">
              <Loader2 className="h-8 w-8 animate-spin" />
              Processando...
            </div>
          )}
          {result && (
            <div className="prose prose-invert prose-sm max-h-[52vh] max-w-none overflow-y-auto rounded-xl bg-[#1c1b1b] p-4">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function FileViewerModal({ doc, onClose }: { doc: DocItem; onClose: () => void }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [markdownText, setMarkdownText] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const isMarkdown = doc.file_name.toLowerCase().endsWith('.md')

  useEffect(() => {
    let objectUrl: string | null = null
    setBlobUrl(null); setMarkdownText(null); setLoading(true)
    if (isMarkdown) {
      api.get(`/api/docs/${doc.doc_id}/file`, { responseType: 'text' }).then(response => setMarkdownText(response.data)).finally(() => setLoading(false))
    } else {
      api.get(`/api/docs/${doc.doc_id}/file`, { responseType: 'blob' }).then(response => {
        objectUrl = URL.createObjectURL(response.data); setBlobUrl(objectUrl)
      }).finally(() => setLoading(false))
    }
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [doc.doc_id, isMarkdown])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#0e0e0e]">
      <header className="flex items-center justify-between border-b border-[#41474e]/45 px-5 py-3">
        <p className="truncate text-sm font-medium text-[#e5e2e1]">{doc.file_name}</p>
        <Button variant="ghost" size="sm" onClick={onClose} className="text-[#c1c7cf]">Fechar</Button>
      </header>
      <div className="flex-1 overflow-hidden">
        {loading ? <div className="flex h-full items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-[#8b9199]" /></div> : null}
        {!loading && markdownText !== null ? <div className="h-full overflow-y-auto px-8 py-6"><div className="prose prose-invert prose-sm mx-auto max-w-4xl"><ReactMarkdown>{markdownText}</ReactMarkdown></div></div> : null}
        {!loading && blobUrl ? <iframe src={blobUrl} title={doc.file_name} className="h-full w-full border-0" /> : null}
      </div>
    </div>
  )
}

export function Docs() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [compareDoc, setCompareDoc] = useState<string | null>(null)
  const [opsDoc, setOpsDoc] = useState<string | null>(null)
  const [viewDoc, setViewDoc] = useState<DocItem | null>(null)

  const { data: docs = [], isLoading, error } = useQuery<DocItem[]>({ queryKey: ['docs'], queryFn: apiClient.listDocs, retry: 1 })
  const deleteMut = useMutation({
    mutationFn: (docId: string) => apiClient.deleteDoc(docId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['docs'] }); toast.success('Documento removido.') },
    onError: () => toast.error('Erro ao remover documento.'),
  })

  const normalized = search.trim().toLowerCase()
  const filtered = useMemo(() => docs.filter(doc => doc.file_name.toLowerCase().includes(normalized)), [docs, normalized])
  const totalChunks = useMemo(() => docs.reduce((acc, doc) => acc + doc.chunk_count, 0), [docs])
  const usage = totalChunks > 0 ? Math.min(100, Math.round((totalChunks / 1600) * 100)) : 0

  return (
    <>
      <div className="relative space-y-8">
        <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_82%_10%,rgba(144,202,249,0.12),transparent_42%),radial-gradient(circle_at_14%_16%,rgba(201,139,94,0.08),transparent_48%)]" />
        <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div><h1 className="font-headline text-4xl font-extrabold tracking-tight text-[#e5e2e1]">Documentos Indexados</h1><p className="text-sm text-[#c1c7cf]">Gerencie e opere sobre seus documentos</p></div>
          <div className="relative w-full lg:w-96"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8b9199]" /><Input value={search} onChange={event => setSearch(event.target.value)} placeholder="Buscar artefatos..." className="h-11 border-[#41474e] bg-[#0e0e0e] pl-10 text-[#e5e2e1]" /></div>
        </header>

        <div className="grid grid-cols-1 gap-8 xl:grid-cols-12">
          <section className="space-y-5 xl:col-span-4">
            <article className="rounded-2xl bg-[#1c1b1b] p-6">
              <div className="mb-5 flex items-start justify-between"><div><p className="font-headline text-3xl font-extrabold text-[#e5e2e1]">{formatChunkCount(totalChunks)}</p><p className="text-xs uppercase tracking-[0.14em] text-[#8b9199]">Total chunks</p></div><div className="rounded-xl bg-[#203142] p-3"><Database className="h-5 w-5 text-[#c5e3ff]" /></div></div>
              <div className="space-y-1.5"><div className="flex items-center justify-between text-xs text-[#aab2bc]"><span>Storage usage</span><span>{usage}%</span></div><div className="h-1.5 overflow-hidden rounded-full bg-[#0e0e0e]"><div className="h-full rounded-full bg-[#90caf9]" style={{ width: `${usage}%` }} /></div></div>
            </article>
            <article className="rounded-2xl bg-[#0f0f0f] p-5"><h3 className="font-headline text-sm font-bold text-[#e5e2e1]">Status do agente</h3><div className="mt-3 flex items-center gap-2 text-sm text-[#c1c7cf]"><span className="h-2 w-2 rounded-full bg-[#ffd9ae] shadow-[0_0_8px_rgba(255,217,174,0.6)] animate-pulse" />Pronto para novas operacoes</div></article>
          </section>

          <section className="xl:col-span-8">
            {error ? <div className="rounded-xl border border-[#7f2f33] bg-[#3b181b] px-4 py-3 text-sm text-[#ffb4ab]">Erro ao carregar documentos.</div> : null}
            {isLoading ? <div className="space-y-3">{[1, 2, 3].map(item => <Skeleton key={item} className="h-28 w-full rounded-2xl bg-[#2a2a2a]" />)}</div> : null}
            {!isLoading && filtered.length === 0 && !error ? <div className="rounded-2xl bg-[#1c1b1b] p-10 text-center"><FileText className="mx-auto mb-3 h-10 w-10 text-[#8b9199]" /><p className="font-headline text-xl font-bold text-[#e5e2e1]">{normalized ? 'Nenhum documento encontrado' : 'Nenhum documento indexado'}</p></div> : null}
            {!isLoading && filtered.length > 0 ? (
              <div className="space-y-3">
                {filtered.map(doc => (
                  <article key={doc.doc_id} className="group flex flex-col gap-4 rounded-2xl bg-[#1c1b1b] p-4 transition-all hover:bg-[#2a2a2a] sm:flex-row sm:items-center">
                    <div className={cn('flex h-16 w-14 shrink-0 items-center justify-center rounded-xl bg-[#0e0e0e]', fileAccent(doc.file_name))}><FileText className="h-6 w-6" /></div>
                    <div className="min-w-0 flex-1"><h3 className="truncate font-headline text-lg font-bold tracking-tight text-[#e5e2e1]">{doc.file_name}</h3><p className="mt-1 text-xs text-[#aab2bc]">{formatChunkCount(doc.chunk_count)} chunks indexados</p></div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button variant="outline" size="sm" onClick={() => setViewDoc(doc)} className="h-8 border-[#41474e] bg-[#131313] text-[#c1c7cf]"><Eye className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" onClick={() => setOpsDoc(doc.file_name)} className="h-8 rounded-lg border-0 bg-[#203142] text-[#c5e3ff]"><Zap className="mr-1 h-3.5 w-3.5" />Ops</Button>
                      {docs.length > 1 ? <Button variant="outline" size="sm" onClick={() => setCompareDoc(doc.file_name)} className="h-8 border-[#41474e] bg-[#131313] text-[#c1c7cf]"><GitCompare className="h-3.5 w-3.5" /></Button> : null}
                      <Button variant="outline" size="sm" onClick={() => { if (window.confirm(`Remover "${doc.file_name}"?`)) deleteMut.mutate(doc.doc_id) }} disabled={deleteMut.isPending} className="h-8 border-[#7f2f33]/40 bg-[#2a1517] text-[#ffb4ab]"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        </div>

        <button type="button" onClick={() => navigate('/ingest')} className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] px-5 py-3 font-headline text-sm font-bold text-[#03263b]">
          <FileText className="h-4 w-4" />
          Novo artefato
        </button>
      </div>

      {compareDoc ? <CompareDialog doc1={compareDoc} docs={docs} onClose={() => setCompareDoc(null)} /> : null}
      {opsDoc ? <SmartOpsDialog doc={opsDoc} onClose={() => setOpsDoc(null)} /> : null}
      {viewDoc ? <FileViewerModal doc={viewDoc} onClose={() => setViewDoc(null)} /> : null}
    </>
  )
}
