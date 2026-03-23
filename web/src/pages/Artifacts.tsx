import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Archive, BookOpen, Brain, CheckSquare, Download, Eye,
  FileText, GraduationCap, Loader2, Plus, Trash2, X, Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader, PageShell } from '@/components/ui/page-shell'
import { apiClient, type ArtifactItem, type DocItem } from '@/api/client'
import { formatBytes, formatDate } from '@/lib/utils'

const ARTIFACT_TYPES = [
  { value: 'checklist', label: 'Checklist' },
  { value: 'artifact', label: 'Artefato Livre' },
] as const
const MARKDOWN_FILE_RE = /\.(md|markdown|txt)$/i

function isMarkdownArtifact(filename: string): boolean {
  return MARKDOWN_FILE_RE.test(filename)
}

function toPdfName(filename: string): string {
  return MARKDOWN_FILE_RE.test(filename)
    ? filename.replace(MARKDOWN_FILE_RE, '.pdf')
    : `${filename}.pdf`
}

function downloadBlobFile(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

// ── Resumir Documento Dialog ──────────────────────────────────────────────────

function SummarizeDocDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [selectedDoc, setSelectedDoc] = useState('')
  const [mode, setMode] = useState<'brief' | 'deep'>('brief')
  const [result, setResult] = useState('')
  const [artifactFilename, setArtifactFilename] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<'md' | 'pdf' | null>(null)

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const startJob = useMutation({
    mutationFn: () => apiClient.summarizeAsync(selectedDoc, true, mode),
    onSuccess: data => setJobId(data.job_id),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao iniciar resumo'),
  })

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: query =>
      query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed'
        ? false : 1200,
  })

  useEffect(() => {
    if (!jobId || !jobQuery.data) return
    if (jobQuery.data.status === 'succeeded') {
      const payload = jobQuery.data.result ?? {}
      setResult(String(payload.answer ?? ''))
      setArtifactFilename(payload.artifact_filename ?? null)
      if (payload.artifact_filename) {
        toast.success(`Resumo salvo: ${payload.artifact_filename}`)
        qc.invalidateQueries({ queryKey: ['artifacts'] })
      }
      setJobId(null)
    } else if (jobQuery.data.status === 'failed') {
      toast.error(jobQuery.data.error ?? 'Erro ao gerar resumo')
      setJobId(null)
    }
  }, [jobId, jobQuery.data, qc])

  const modeLabel = mode === 'brief' ? 'Resumo Breve' : 'Resumo Aprofundado'
  const isProcessing = startJob.isPending || !!jobId

  async function handleDownloadMd() {
    if (!artifactFilename) return
    setDownloading('md')
    try {
      const blob = await apiClient.getArtifactBlob(artifactFilename)
      downloadBlobFile(blob, artifactFilename)
    } catch { toast.error('Erro ao baixar .md') } finally { setDownloading(null) }
  }

  async function handleDownloadPdf() {
    if (!artifactFilename) return
    setDownloading('pdf')
    try {
      const blob = await apiClient.getArtifactPdfBlob(artifactFilename)
      downloadBlobFile(blob, toPdfName(artifactFilename))
    } catch { toast.error('Erro ao baixar PDF') } finally { setDownloading(null) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-blue-400" />
            <h2 className="font-semibold text-zinc-100">Resumir Documento</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {!result && !isProcessing && (
            <>
              <p className="text-sm text-zinc-400">
                Gera um resumo analítico do documento com IA e salva nos artefatos para download.
              </p>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Documento</label>
                <select
                  value={selectedDoc}
                  onChange={e => setSelectedDoc(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  <option value="">Selecione um documento</option>
                  {(docs ?? []).map(d => (
                    <option key={d.file_name} value={d.file_name}>{d.file_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-zinc-300">Tipo de resumo:</p>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setMode('brief')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${mode === 'brief' ? 'border-blue-500 bg-blue-500/10 text-blue-300' : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'}`}
                  >
                    <p className="text-sm font-semibold">Resumo Breve</p>
                    <p className="mt-0.5 text-xs opacity-70">Síntese concisa — até 300 palavras com os pontos essenciais</p>
                  </button>
                  <button
                    onClick={() => setMode('deep')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${mode === 'deep' ? 'border-violet-500 bg-violet-500/10 text-violet-300' : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'}`}
                  >
                    <p className="text-sm font-semibold">Resumo Aprofundado</p>
                    <p className="mt-0.5 text-xs opacity-70">Análise completa seção por seção com detalhes técnicos</p>
                  </button>
                </div>
              </div>
              <Button
                onClick={() => startJob.mutate()}
                disabled={!selectedDoc || isProcessing}
                className="w-full bg-blue-600 hover:bg-blue-700"
              >
                <BookOpen className="mr-2 h-4 w-4" />
                Gerar {modeLabel}
              </Button>
            </>
          )}
          {isProcessing && (
            <div className="flex flex-col items-center justify-center gap-3 py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
              <span className="text-sm text-zinc-400">
                {mode === 'deep' ? 'Analisando documento em profundidade...' : 'Gerando resumo breve...'}
              </span>
              <div className="w-full max-w-md rounded-md border border-zinc-700 bg-zinc-800 p-2">
                <div className="mb-1 flex justify-between text-[11px] text-zinc-400">
                  <span>{jobQuery.data?.stage ?? 'iniciando'}</span>
                  <span>{jobQuery.data?.progress ?? 5}%</span>
                </div>
                <div className="h-2 rounded bg-zinc-700">
                  <div className="h-2 rounded bg-blue-500 transition-all" style={{ width: `${jobQuery.data?.progress ?? 5}%` }} />
                </div>
              </div>
            </div>
          )}
          {result && (
            <>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${mode === 'brief' ? 'bg-blue-500/15 text-blue-300' : 'bg-violet-500/15 text-violet-300'}`}>
                  {modeLabel} — {selectedDoc}
                </span>
                <Button variant="ghost" size="sm" className="text-xs text-zinc-500" onClick={() => { setResult(''); setArtifactFilename(null); startJob.reset() }}>
                  Gerar outro
                </Button>
              </div>
              {artifactFilename && (
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={handleDownloadMd} disabled={downloading !== null}>
                    <Download className="mr-2 h-4 w-4" />{downloading === 'md' ? 'Baixando...' : 'Exportar .md'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading !== null}>
                    <FileText className="mr-2 h-4 w-4" />{downloading === 'pdf' ? 'Baixando...' : 'Exportar PDF'}
                  </Button>
                </div>
              )}
              <div className="prose prose-invert prose-sm max-w-none max-h-[32rem] overflow-y-auto">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Smart Digest Dialog ───────────────────────────────────────────────────────

function SmartDigestDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [selectedDoc, setSelectedDoc] = useState('')
  const [genFlashcards, setGenFlashcards] = useState(true)
  const [extractTasks, setExtractTasks] = useState(true)
  const [scheduleReviews, setScheduleReviews] = useState(false)
  const [numCards, setNumCards] = useState(10)
  const [digestResult, setDigestResult] = useState<{
    summary: string; deck_id: number | null; tasks_created: number
    task_titles: string[]; reviews_scheduled: number
  } | null>(null)

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const digestMutation = useMutation({
    mutationFn: () =>
      apiClient.digestDocument(selectedDoc, { generateFlashcards: genFlashcards, extractTasks, numCards, maxTasks: 8, scheduleReviews }),
    onSuccess: data => {
      setDigestResult(data)
      if (data.deck_id) qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      if (data.tasks_created > 0) qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Smart Digest concluído!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro no Smart Digest'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-amber-400" />
            <h2 className="font-semibold text-zinc-100">Smart Digest</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {!digestResult && !digestMutation.isPending && (
            <>
              <p className="text-sm text-zinc-400">
                Analisa o documento com IA e gera em uma operação: <strong>resumo analítico</strong>, <strong>flashcards</strong> para revisão espaçada e <strong>tarefas</strong> extraídas automaticamente.
              </p>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Documento</label>
                <select
                  value={selectedDoc}
                  onChange={e => setSelectedDoc(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  <option value="">Selecione um documento</option>
                  {(docs ?? []).map(d => (
                    <option key={d.file_name} value={d.file_name}>{d.file_name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-3">
                <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                  <input type="checkbox" checked={genFlashcards} onChange={e => setGenFlashcards(e.target.checked)} className="h-4 w-4 accent-blue-500" />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">Gerar Flashcards</p>
                    <p className="text-xs text-zinc-500">Cria um deck de flashcards para revisão espaçada</p>
                  </div>
                </label>
                {genFlashcards && (
                  <div className="ml-7 flex items-center gap-3">
                    <span className="text-xs text-zinc-400 shrink-0">Quantidade de cards:</span>
                    <input type="range" min={5} max={30} step={5} value={numCards} onChange={e => setNumCards(Number(e.target.value))} className="flex-1" />
                    <span className="text-xs font-medium text-blue-400 w-8 text-right">{numCards}</span>
                  </div>
                )}
                <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                  <input type="checkbox" checked={extractTasks} onChange={e => setExtractTasks(e.target.checked)} className="h-4 w-4 accent-emerald-500" />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">Extrair Tarefas</p>
                    <p className="text-xs text-zinc-500">Identifica ações, exercícios e entregas no documento</p>
                  </div>
                </label>
                {genFlashcards && (
                  <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                    <input type="checkbox" checked={scheduleReviews} onChange={e => setScheduleReviews(e.target.checked)} className="h-4 w-4 accent-purple-500" />
                    <div>
                      <p className="text-sm font-medium text-zinc-200">Agendar Revisões SRS</p>
                      <p className="text-xs text-zinc-500">Cria lembretes de revisão espaçada no calendário (+1d, +3d, +7d)</p>
                    </div>
                  </label>
                )}
              </div>
              <Button
                onClick={() => digestMutation.mutate()}
                disabled={!selectedDoc}
                className="w-full bg-amber-600 hover:bg-amber-700 text-white"
              >
                <Zap className="mr-2 h-4 w-4" />
                Executar Smart Digest
              </Button>
            </>
          )}
          {digestMutation.isPending && (
            <div className="flex flex-col items-center justify-center gap-3 py-10">
              <Brain className="h-8 w-8 animate-pulse text-amber-400" />
              <span className="text-sm text-zinc-400">Analisando documento...</span>
              <span className="text-xs text-zinc-600">Gerando resumo, flashcards e extraindo tarefas</span>
            </div>
          )}
          {digestResult && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {digestResult.deck_id && (
                  <div className="rounded-lg border border-blue-800 bg-blue-950/30 p-3">
                    <p className="text-xs text-blue-400 font-medium mb-1">Flashcards criados</p>
                    <p className="text-lg font-bold text-blue-300">{numCards} cards</p>
                    <a href="/flashcards" className="text-xs text-blue-500 hover:underline">Ver em Flashcards →</a>
                  </div>
                )}
                {digestResult.tasks_created > 0 && (
                  <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3">
                    <p className="text-xs text-emerald-400 font-medium mb-1">Tarefas extraídas</p>
                    <p className="text-lg font-bold text-emerald-300">{digestResult.tasks_created} tarefas</p>
                    <a href="/tasks" className="text-xs text-emerald-500 hover:underline">Ver em Tarefas →</a>
                  </div>
                )}
                {digestResult.reviews_scheduled > 0 && (
                  <div className="rounded-lg border border-purple-800 bg-purple-950/30 p-3">
                    <p className="text-xs text-purple-400 font-medium mb-1">Revisões SRS agendadas</p>
                    <p className="text-lg font-bold text-purple-300">{digestResult.reviews_scheduled} lembretes</p>
                    <a href="/schedule" className="text-xs text-purple-500 hover:underline">Ver Calendário →</a>
                  </div>
                )}
              </div>
              {digestResult.task_titles.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                    <CheckSquare className="h-3 w-3" /> Tarefas criadas:
                  </p>
                  <ul className="space-y-1">
                    {digestResult.task_titles.map((t, i) => (
                      <li key={i} className="text-xs text-zinc-300 flex items-start gap-2">
                        <span className="text-emerald-500 mt-0.5">✓</span>{t}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                  <BookOpen className="h-3 w-3" /> Resumo:
                </p>
                <div className="prose prose-invert prose-xs max-w-none max-h-60 overflow-y-auto rounded-lg bg-zinc-800 p-3">
                  <ReactMarkdown>{digestResult.summary}</ReactMarkdown>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => { setDigestResult(null); digestMutation.reset() }} className="w-full">
                Fazer novamente
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Create Artifact Dialog ────────────────────────────────────────────────────

function CreateArtifactDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [type, setType] = useState<string>('checklist')
  const [topic, setTopic] = useState('')
  const [result, setResult] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const startJob = useMutation({
    mutationFn: () =>
      apiClient.createArtifactAsync(
        type,
        topic,
        undefined,
        selectedDocs.map(doc => doc.doc_id)
      ),
    onSuccess: data => { setJobId(data.job_id) },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao iniciar artefato'),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: query =>
      query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed'
        ? false : 1200,
  })

  useEffect(() => {
    if (!jobId || !jobQuery.data) return
    if (jobQuery.data.status === 'succeeded') {
      const payload = jobQuery.data.result ?? {}
      setResult(String(payload.answer ?? ''))
      if (payload.filename) toast.success(`Artefato salvo: ${payload.filename}`)
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      setJobId(null)
    } else if (jobQuery.data.status === 'failed') {
      toast.error(jobQuery.data.error ?? 'Erro ao gerar artefato')
      setJobId(null)
    }
  }, [jobId, jobQuery.data, qc])

  const isProcessing = startJob.isPending || !!jobId

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Gerar Artefato</h2>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="p-6 space-y-4">
          {!result ? (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Tipo de Artefato</label>
                <select
                  value={type}
                  onChange={e => setType(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  {ARTIFACT_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Tópico</label>
                <Input placeholder="Ex: Python para iniciantes" value={topic} onChange={e => setTopic(e.target.value)} />
              </div>
              <div className="space-y-2">
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Documentos para usar (opcional)</label>
                <div className="flex gap-2">
                  <select
                    value={selectedDoc}
                    onChange={e => setSelectedDoc(e.target.value)}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                  >
                    <option value="">Selecione um documento</option>
                    {(docs ?? []).filter(doc => !selectedDocs.some(item => item.doc_id === doc.doc_id)).map(doc => (
                      <option key={doc.doc_id} value={doc.doc_id}>{doc.file_name}</option>
                    ))}
                  </select>
                  <Button
                    type="button" variant="outline"
                    onClick={() => {
                      const docToAdd = (docs ?? []).find(doc => doc.doc_id === selectedDoc)
                      if (!docToAdd || selectedDocs.some(item => item.doc_id === docToAdd.doc_id)) return
                      setSelectedDocs(prev => [...prev, docToAdd])
                      setSelectedDoc('')
                    }}
                    disabled={!selectedDoc}
                  >Adicionar</Button>
                </div>
                {selectedDocs.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedDocs.map(doc => (
                      <span key={doc.doc_id} className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-200">
                        {doc.file_name}
                        <button type="button" onClick={() => setSelectedDocs(prev => prev.filter(item => item.doc_id !== doc.doc_id))} className="text-zinc-400 hover:text-red-400">
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <Button onClick={() => startJob.mutate()} disabled={!topic.trim() || isProcessing} className="w-full">
                {isProcessing ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{jobQuery.data?.stage ?? 'Gerando...'}</>
                ) : 'Gerar'}
              </Button>
              {isProcessing && (
                <div className="rounded-md border border-zinc-700 bg-zinc-800 p-2">
                  <div className="mb-1 flex justify-between text-[11px] text-zinc-400">
                    <span>{jobQuery.data?.stage ?? 'iniciando'}</span>
                    <span>{jobQuery.data?.progress ?? 5}%</span>
                  </div>
                  <div className="h-2 rounded bg-zinc-700">
                    <div className="h-2 rounded bg-blue-500 transition-all" style={{ width: `${jobQuery.data?.progress ?? 5}%` }} />
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="prose prose-invert prose-sm max-w-none max-h-80 overflow-y-auto">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
              <Button variant="outline" onClick={onClose} className="w-full">Fechar</Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Preview Dialog ────────────────────────────────────────────────────────────

function PreviewDialog({ filename, onClose }: { filename: string; onClose: () => void }) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (!isMarkdownArtifact(filename)) {
      if (!cancelled) { setContent('Preview disponivel apenas para arquivos de texto (.md, .markdown, .txt).'); setLoading(false) }
      return
    }
    setLoading(true)
    apiClient.getArtifactText(filename)
      .then(text => { if (cancelled) return; setContent(text) })
      .catch((err: any) => { if (cancelled) return; setContent(err?.response?.data?.detail ?? 'Erro ao carregar arquivo.') })
      .finally(() => { if (cancelled) return; setLoading(false) })
    return () => { cancelled = true }
  }, [filename])

  async function handleDownload() {
    setDownloading(true)
    try { const blob = await apiClient.getArtifactBlob(filename); downloadBlobFile(blob, filename) }
    catch { toast.error('Erro ao baixar arquivo') } finally { setDownloading(false) }
  }

  async function handleDownloadPdf() {
    setDownloading(true)
    try { const blob = await apiClient.getArtifactPdfBlob(filename); downloadBlobFile(blob, toPdfName(filename)) }
    catch { toast.error('Erro ao baixar PDF') } finally { setDownloading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100 truncate">{filename}</h2>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={downloading}><Download className="h-4 w-4 mr-1" />Download</Button>
            {isMarkdownArtifact(filename) && (
              <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading}><FileText className="h-4 w-4 mr-1" />PDF</Button>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
          </div>
        </div>
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          {loading ? (
            <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-4 w-full" />)}</div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none"><ReactMarkdown>{content ?? ''}</ReactMarkdown></div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Artifacts Page ───────────────────────────────────────────────────────

export function Artifacts() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [showSummarize, setShowSummarize] = useState(false)
  const [showDigest, setShowDigest] = useState(false)
  const [previewFile, setPreviewFile] = useState<string | null>(null)
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)

  const { data: artifacts, isLoading, error } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts'],
    queryFn: apiClient.listArtifacts,
    retry: 1,
  })

  const deleteMut = useMutation({
    mutationFn: (filename: string) => apiClient.deleteArtifact(filename),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['artifacts'] }); toast.success('Artefato removido.') },
    onError: () => toast.error('Erro ao remover artefato.'),
  })

  async function handleDownload(filename: string) {
    const key = `${filename}:file`; setDownloadingKey(key)
    try { const blob = await apiClient.getArtifactBlob(filename); downloadBlobFile(blob, filename) }
    catch { toast.error('Erro ao baixar arquivo') } finally { setDownloadingKey(null) }
  }

  async function handleDownloadPdf(filename: string) {
    const key = `${filename}:pdf`; setDownloadingKey(key)
    try { const blob = await apiClient.getArtifactPdfBlob(filename); downloadBlobFile(blob, toPdfName(filename)) }
    catch { toast.error('Erro ao baixar PDF') } finally { setDownloadingKey(null) }
  }

  return (
    <PageShell>
      <PageHeader
        title="Artefatos"
        subtitle="Resumos, checklists e outros artefatos gerados pelo agente"
        actions={(
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => setShowSummarize(true)}
            className="border-blue-700 text-blue-400 hover:bg-blue-900/20"
            title="Gera resumo breve ou aprofundado de um documento"
          >
            <BookOpen className="mr-2 h-4 w-4" />
            Resumir Documento
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowDigest(true)}
            className="border-amber-700 text-amber-400 hover:bg-amber-900/20"
            title="Gera resumo + flashcards + extrai tarefas em uma operação"
          >
            <Zap className="mr-2 h-4 w-4" />
            Smart Digest
          </Button>
          <Button
            variant="outline"
            onClick={() => window.location.href = '/studyplan'}
            className="border-emerald-700 text-emerald-400 hover:bg-emerald-900/20"
            title="Cria plano de estudos completo: sessões, tarefas, flashcards"
          >
            <GraduationCap className="mr-2 h-4 w-4" />
            Plano de Estudos
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Novo Artefato
          </Button>
        </div>
        )}
      />

      {/* Descrições das ações principais */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-blue-900/40 bg-blue-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-blue-400 mb-0.5">Resumir Documento</p>
          <p className="text-xs text-zinc-500">Resumo breve (≤300 palavras) ou aprofundado (seção por seção) com download em .md e PDF.</p>
        </div>
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-amber-400 mb-0.5">Smart Digest</p>
          <p className="text-xs text-zinc-500">Resumo analítico + flashcards para revisão espaçada + extração automática de tarefas, tudo de uma vez.</p>
        </div>
        <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-emerald-400 mb-0.5">Plano de Estudos</p>
          <p className="text-xs text-zinc-500">Plano completo com sessões diárias no calendário, tarefas por tópico, flashcards SRS e resumo inicial.</p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">Erro ao carregar artefatos.</div>
      )}

      {isLoading && (
        <div className="space-y-3">{[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>
      )}

      {!isLoading && (!artifacts || artifacts.length === 0) && !error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <Archive className="h-12 w-12 text-zinc-600" />
            <p className="font-medium text-zinc-300">Nenhum artefato gerado</p>
            <p className="text-sm text-zinc-500">Gere resumos, checklists e mais</p>
            <Button onClick={() => setShowCreate(true)}><Plus className="mr-2 h-4 w-4" />Criar Artefato</Button>
          </CardContent>
        </Card>
      )}

      {artifacts && artifacts.length > 0 && (
        <div className="space-y-2">
          {artifacts.map(artifact => {
            const isMarkdown = isMarkdownArtifact(artifact.filename)
            const typeLabel = artifact.artifact_type
              ? (() => {
                  if (artifact.artifact_type === 'summary') return 'Resumo'
                  if (artifact.artifact_type === 'checklist') return 'Checklist'
                  if (artifact.artifact_type === 'study_plan') return 'Plano de Estudos'
                  return artifact.artifact_type
                })()
              : null

            return (
              <Card key={`${artifact.filename}-${artifact.created_at}`} className="hover:border-zinc-700 transition-colors">
                <CardContent className="flex items-center justify-between py-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <Archive className="h-5 w-5 shrink-0 text-blue-400" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-zinc-100 truncate">
                        {artifact.title?.trim() ? artifact.title : artifact.filename}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {typeLabel ? `${typeLabel} · ` : ''}{formatBytes(artifact.size)} · {formatDate(artifact.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    {isMarkdown && (
                      <Button variant="ghost" size="sm" onClick={() => setPreviewFile(artifact.filename)}>
                        <Eye className="h-4 w-4 mr-1" />Preview
                      </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => handleDownload(artifact.filename)} disabled={downloadingKey !== null}>
                      <Download className="h-4 w-4 mr-1" />
                      {downloadingKey === `${artifact.filename}:file` ? 'Baixando...' : 'Download'}
                    </Button>
                    {isMarkdown && (
                      <Button variant="outline" size="sm" onClick={() => handleDownloadPdf(artifact.filename)} disabled={downloadingKey !== null}>
                        <FileText className="h-4 w-4 mr-1" />
                        {downloadingKey === `${artifact.filename}:pdf` ? 'Baixando...' : 'PDF'}
                      </Button>
                    )}
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => { if (confirm(`Remover "${artifact.filename}"?`)) deleteMut.mutate(artifact.filename) }}
                      disabled={deleteMut.isPending}
                      className="text-zinc-600 hover:text-red-400"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {showSummarize && <SummarizeDocDialog onClose={() => setShowSummarize(false)} />}
      {showDigest && <SmartDigestDialog onClose={() => setShowDigest(false)} />}
      {showCreate && <CreateArtifactDialog onClose={() => setShowCreate(false)} />}
      {previewFile && <PreviewDialog filename={previewFile} onClose={() => setPreviewFile(null)} />}
    </PageShell>
  )
}
