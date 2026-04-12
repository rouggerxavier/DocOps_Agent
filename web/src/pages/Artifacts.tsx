import { useEffect, useMemo, useState } from 'react'
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
import { apiClient, type ArtifactFilterOptions, type ArtifactItem, type ArtifactTemplate, type DocItem } from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { formatBytes, formatDate } from '@/lib/utils'

const ARTIFACT_TYPES = [
  { value: 'checklist', label: 'Checklist' },
  { value: 'artifact', label: 'Artefato Livre' },
] as const
const MARKDOWN_FILE_RE = /\.(md|markdown|txt)$/i
const ARTIFACT_SORT_OPTIONS = [
  { value: 'created_at', label: 'Mais recentes' },
  { value: 'title', label: 'Titulo (A-Z)' },
  { value: 'artifact_type', label: 'Tipo' },
  { value: 'confidence_score', label: 'Confianca' },
] as const

function confidenceBadgeClass(level: string | null | undefined): string {
  const normalized = String(level ?? '').toLowerCase()
  if (normalized === 'high') return 'border-emerald-700 bg-emerald-950/40 text-emerald-300'
  if (normalized === 'medium') return 'border-amber-700 bg-amber-950/40 text-amber-300'
  if (normalized === 'low') return 'border-rose-700 bg-rose-950/40 text-rose-300'
  return 'border-zinc-700 bg-zinc-900 text-zinc-400'
}

function pickDefaultTemplate(
  templates: ArtifactTemplate[],
  options: { summaryMode?: 'brief' | 'deep'; artifactType?: string }
): string {
  if (!templates.length) return ''

  if (options.summaryMode) {
    const byMode = templates.find(item => item.default_for_summary_modes.includes(options.summaryMode!))
    if (byMode) return byMode.template_id
  }

  if (options.artifactType) {
    const byType = templates.find(item => item.default_for_artifact_types.includes(options.artifactType!))
    if (byType) return byType.template_id
  }

  return templates[0]?.template_id ?? ''
}

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

// â”€â”€ Resumir Documento Dialog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function SummarizeDocDialog({
  onClose,
  templatesEnabled,
}: {
  onClose: () => void
  templatesEnabled: boolean
}) {
  const qc = useQueryClient()
  const [selectedDoc, setSelectedDoc] = useState('')
  const [mode, setMode] = useState<'brief' | 'deep'>('brief')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [result, setResult] = useState('')
  const [artifactFilename, setArtifactFilename] = useState<string | null>(null)
  const [resultTemplateLabel, setResultTemplateLabel] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<'md' | 'pdf' | null>(null)

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const { data: templates } = useQuery<ArtifactTemplate[]>({
    queryKey: ['artifact-templates', 'summary', mode],
    queryFn: () => apiClient.listArtifactTemplates(mode, 'summary'),
    enabled: templatesEnabled,
    staleTime: 60_000,
    retry: 1,
  })
  const templateOptions = useMemo(() => templates ?? [], [templates])
  const selectedTemplate = useMemo(
    () => templateOptions.find(item => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templateOptions]
  )

  useEffect(() => {
    if (!templatesEnabled) return
    if (!templateOptions.length) {
      setSelectedTemplateId('')
      return
    }
    const hasActive = templateOptions.some(item => item.template_id === selectedTemplateId)
    if (hasActive) return
    setSelectedTemplateId(pickDefaultTemplate(templateOptions, { summaryMode: mode, artifactType: 'summary' }))
  }, [mode, selectedTemplateId, templateOptions, templatesEnabled])

  const startJob = useMutation({
    mutationFn: () => apiClient.summarizeAsync(
      selectedDoc,
      true,
      mode,
      templatesEnabled ? (selectedTemplateId || undefined) : undefined,
    ),
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
      setResultTemplateLabel(payload.template_label ? String(payload.template_label) : null)
      if (payload.artifact_filename) {
        toast.success(`Resumo salvo: ${payload.artifact_filename}`)
        qc.invalidateQueries({ queryKey: ['artifacts'] })
        qc.invalidateQueries({ queryKey: ['artifact-filter-options'] })
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
                Gera um resumo analÃ­tico do documento com IA e salva nos artefatos para download.
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
                    <p className="mt-0.5 text-xs opacity-70">SÃ­ntese concisa â€” atÃ© 300 palavras com os pontos essenciais</p>
                  </button>
                  <button
                    onClick={() => setMode('deep')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${mode === 'deep' ? 'border-violet-500 bg-violet-500/10 text-violet-300' : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'}`}
                  >
                    <p className="text-sm font-semibold">Resumo Aprofundado</p>
                    <p className="mt-0.5 text-xs opacity-70">AnÃ¡lise completa seÃ§Ã£o por seÃ§Ã£o com detalhes tÃ©cnicos</p>
                  </button>
                </div>
              </div>
              {templatesEnabled && templateOptions.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium text-zinc-300">Template de saida:</p>
                  <div className="grid gap-2 md:grid-cols-3">
                    {templateOptions.map(template => (
                      <button
                        key={template.template_id}
                        onClick={() => setSelectedTemplateId(template.template_id)}
                        className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                          selectedTemplateId === template.template_id
                            ? 'border-amber-500 bg-amber-500/10 text-amber-200'
                            : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                        }`}
                      >
                        <p className="text-sm font-semibold">{template.label}</p>
                        <p className="mt-0.5 text-xs opacity-80">{template.short_description}</p>
                      </button>
                    ))}
                  </div>
                  {selectedTemplate && (
                    <div className="mt-2 rounded-lg border border-zinc-700 bg-zinc-800/70 p-3">
                      <p className="text-xs font-medium text-zinc-200">{selectedTemplate.preview_title}</p>
                      <p className="mt-1 text-xs text-zinc-400">{selectedTemplate.long_description}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {selectedTemplate.preview_sections.map(section => (
                          <span key={section} className="rounded-full border border-zinc-600 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-300">
                            {section}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
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
                  {modeLabel} â€” {selectedDoc}{resultTemplateLabel ? ` â€” ${resultTemplateLabel}` : ''}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500"
                  onClick={() => {
                    setResult('')
                    setArtifactFilename(null)
                    setResultTemplateLabel(null)
                    startJob.reset()
                  }}
                >
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

// â”€â”€ Smart Digest Dialog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
      toast.success('Smart Digest concluÃ­do!')
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
                Analisa o documento com IA e gera em uma operaÃ§Ã£o: <strong>resumo analÃ­tico</strong>, <strong>flashcards</strong> para revisÃ£o espaÃ§ada e <strong>tarefas</strong> extraÃ­das automaticamente.
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
                    <p className="text-xs text-zinc-500">Cria um deck de flashcards para revisÃ£o espaÃ§ada</p>
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
                    <p className="text-xs text-zinc-500">Identifica aÃ§Ãµes, exercÃ­cios e entregas no documento</p>
                  </div>
                </label>
                {genFlashcards && (
                  <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                    <input type="checkbox" checked={scheduleReviews} onChange={e => setScheduleReviews(e.target.checked)} className="h-4 w-4 accent-purple-500" />
                    <div>
                      <p className="text-sm font-medium text-zinc-200">Agendar RevisÃµes SRS</p>
                      <p className="text-xs text-zinc-500">Cria lembretes de revisÃ£o espaÃ§ada no calendÃ¡rio (+1d, +3d, +7d)</p>
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
                    <a href="/flashcards" className="text-xs text-blue-500 hover:underline">Ver em Flashcards â†’</a>
                  </div>
                )}
                {digestResult.tasks_created > 0 && (
                  <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3">
                    <p className="text-xs text-emerald-400 font-medium mb-1">Tarefas extraÃ­das</p>
                    <p className="text-lg font-bold text-emerald-300">{digestResult.tasks_created} tarefas</p>
                    <a href="/tasks" className="text-xs text-emerald-500 hover:underline">Ver em Tarefas â†’</a>
                  </div>
                )}
                {digestResult.reviews_scheduled > 0 && (
                  <div className="rounded-lg border border-purple-800 bg-purple-950/30 p-3">
                    <p className="text-xs text-purple-400 font-medium mb-1">RevisÃµes SRS agendadas</p>
                    <p className="text-lg font-bold text-purple-300">{digestResult.reviews_scheduled} lembretes</p>
                    <a href="/schedule" className="text-xs text-purple-500 hover:underline">Ver CalendÃ¡rio â†’</a>
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
                        <span className="text-emerald-500 mt-0.5">âœ“</span>{t}
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

// â”€â”€ Create Artifact Dialog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function CreateArtifactDialog({
  onClose,
  templatesEnabled,
}: {
  onClose: () => void
  templatesEnabled: boolean
}) {
  const qc = useQueryClient()
  const [type, setType] = useState<string>('checklist')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [topic, setTopic] = useState('')
  const [result, setResult] = useState('')
  const [resultTemplateLabel, setResultTemplateLabel] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })
  const { data: templates } = useQuery<ArtifactTemplate[]>({
    queryKey: ['artifact-templates', type],
    queryFn: () => apiClient.listArtifactTemplates(undefined, type),
    enabled: templatesEnabled,
    staleTime: 60_000,
    retry: 1,
  })
  const templateOptions = useMemo(() => templates ?? [], [templates])
  const selectedTemplate = useMemo(
    () => templateOptions.find(item => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templateOptions]
  )

  useEffect(() => {
    if (!templatesEnabled) return
    if (!templateOptions.length) {
      setSelectedTemplateId('')
      return
    }
    const hasActive = templateOptions.some(item => item.template_id === selectedTemplateId)
    if (hasActive) return
    setSelectedTemplateId(pickDefaultTemplate(templateOptions, { artifactType: type }))
  }, [selectedTemplateId, templateOptions, templatesEnabled, type])

  const startJob = useMutation({
    mutationFn: () =>
      apiClient.createArtifactAsync(
        type,
        topic,
        undefined,
        selectedDocs.map(doc => doc.doc_id),
        templatesEnabled ? (selectedTemplateId || undefined) : undefined,
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
      setResultTemplateLabel(payload.template_label ? String(payload.template_label) : null)
      if (payload.filename) toast.success(`Artefato salvo: ${payload.filename}`)
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      qc.invalidateQueries({ queryKey: ['artifact-filter-options'] })
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
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">TÃ³pico</label>
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
              {templatesEnabled && templateOptions.length > 0 && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-zinc-300">Template</label>
                  <div className="grid gap-2 md:grid-cols-3">
                    {templateOptions.map(template => (
                      <button
                        key={template.template_id}
                        onClick={() => setSelectedTemplateId(template.template_id)}
                        className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                          selectedTemplateId === template.template_id
                            ? 'border-amber-500 bg-amber-500/10 text-amber-200'
                            : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                        }`}
                      >
                        <p className="text-sm font-semibold">{template.label}</p>
                        <p className="mt-0.5 text-xs opacity-80">{template.short_description}</p>
                      </button>
                    ))}
                  </div>
                  {selectedTemplate && (
                    <div className="mt-2 rounded-lg border border-zinc-700 bg-zinc-800/70 p-3">
                      <p className="text-xs font-medium text-zinc-200">{selectedTemplate.preview_title}</p>
                      <p className="mt-1 text-xs text-zinc-400">{selectedTemplate.long_description}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {selectedTemplate.preview_sections.map(section => (
                          <span key={section} className="rounded-full border border-zinc-600 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-300">
                            {section}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
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
              {resultTemplateLabel && (
                <div className="rounded-md border border-amber-700/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                  Template aplicado: {resultTemplateLabel}
                </div>
              )}
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

// â”€â”€ Preview Dialog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function PreviewDialog({ artifact, onClose }: { artifact: { id: number; filename: string }; onClose: () => void }) {
  const { id: artifactId, filename } = artifact
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
    apiClient.getArtifactTextById(artifactId)
      .then(text => { if (cancelled) return; setContent(text) })
      .catch((err: any) => { if (cancelled) return; setContent(err?.response?.data?.detail ?? 'Erro ao carregar arquivo.') })
      .finally(() => { if (cancelled) return; setLoading(false) })
    return () => { cancelled = true }
  }, [artifactId, filename])

  async function handleDownload() {
    setDownloading(true)
    try { const blob = await apiClient.getArtifactBlobById(artifactId); downloadBlobFile(blob, filename) }
    catch { toast.error('Erro ao baixar arquivo') } finally { setDownloading(false) }
  }

  async function handleDownloadPdf() {
    setDownloading(true)
    try { const blob = await apiClient.getArtifactPdfBlobById(artifactId); downloadBlobFile(blob, toPdfName(filename)) }
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

// â”€â”€ Main Artifacts Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function Artifacts() {
  const qc = useQueryClient()
  const capabilities = useCapabilities()
  const templatesEnabled = capabilities.isEnabled('premium_artifact_templates_enabled')
  const [showCreate, setShowCreate] = useState(false)
  const [showSummarize, setShowSummarize] = useState(false)
  const [showDigest, setShowDigest] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ id: number; filename: string } | null>(null)
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)
  const [artifactTypeFilter, setArtifactTypeFilter] = useState('all')
  const [templateFilter, setTemplateFilter] = useState('all')
  const [sourceDocFilter, setSourceDocFilter] = useState('all')
  const [generationProfileFilter, setGenerationProfileFilter] = useState('all')
  const [sortBy, setSortBy] = useState<(typeof ARTIFACT_SORT_OPTIONS)[number]['value']>('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [search, setSearch] = useState('')

  const queryParams = useMemo(() => ({
    artifact_type: artifactTypeFilter !== 'all' ? artifactTypeFilter : undefined,
    template_id: templateFilter !== 'all' ? templateFilter : undefined,
    source_doc_id: sourceDocFilter !== 'all' ? sourceDocFilter : undefined,
    generation_profile: generationProfileFilter !== 'all' ? generationProfileFilter : undefined,
    search: search.trim() ? search.trim() : undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  }), [artifactTypeFilter, generationProfileFilter, search, sortBy, sortOrder, sourceDocFilter, templateFilter])

  const { data: filterOptions } = useQuery<ArtifactFilterOptions>({
    queryKey: ['artifact-filter-options'],
    queryFn: apiClient.listArtifactFilterOptions,
    retry: 1,
  })

  const { data: artifacts, isLoading, error } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts', queryParams],
    queryFn: () => apiClient.listArtifacts(queryParams),
    retry: 1,
  })

  const deleteMut = useMutation({
    mutationFn: (artifactId: number) => apiClient.deleteArtifactById(artifactId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      qc.invalidateQueries({ queryKey: ['artifact-filter-options'] })
      toast.success('Artefato removido.')
    },
    onError: () => toast.error('Erro ao remover artefato.'),
  })

  async function handleDownload(artifactId: number, filename: string) {
    const key = `${artifactId}:file`; setDownloadingKey(key)
    try { const blob = await apiClient.getArtifactBlobById(artifactId); downloadBlobFile(blob, filename) }
    catch { toast.error('Erro ao baixar arquivo') } finally { setDownloadingKey(null) }
  }

  async function handleDownloadPdf(artifactId: number, filename: string) {
    const key = `${artifactId}:pdf`; setDownloadingKey(key)
    try { const blob = await apiClient.getArtifactPdfBlobById(artifactId); downloadBlobFile(blob, toPdfName(filename)) }
    catch { toast.error('Erro ao baixar PDF') } finally { setDownloadingKey(null) }
  }

  return (
    <PageShell>
      <PageHeader
        title="Artefatos"
        subtitle={
          templatesEnabled
            ? 'Resumos, checklists e outros artefatos gerados com templates premium'
            : 'Resumos, checklists e outros artefatos gerados pelo agente'
        }
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
            title="Gera resumo + flashcards + extrai tarefas em uma operaÃ§Ã£o"
          >
            <Zap className="mr-2 h-4 w-4" />
            Smart Digest
          </Button>
          <Button
            variant="outline"
            onClick={() => window.location.href = '/studyplan'}
            className="border-emerald-700 text-emerald-400 hover:bg-emerald-900/20"
            title="Cria plano de estudos completo: sessÃµes, tarefas, flashcards"
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

      {/* DescriÃ§Ãµes das aÃ§Ãµes principais */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-blue-900/40 bg-blue-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-blue-400 mb-0.5">Resumir Documento</p>
          <p className="text-xs text-zinc-500">Resumo breve (â‰¤300 palavras) ou aprofundado (seÃ§Ã£o por seÃ§Ã£o) com download em .md e PDF.</p>
        </div>
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-amber-400 mb-0.5">Smart Digest</p>
          <p className="text-xs text-zinc-500">Resumo analÃ­tico + flashcards para revisÃ£o espaÃ§ada + extraÃ§Ã£o automÃ¡tica de tarefas, tudo de uma vez.</p>
        </div>
        <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/10 px-4 py-3">
          <p className="text-xs font-semibold text-emerald-400 mb-0.5">Plano de Estudos</p>
          <p className="text-xs text-zinc-500">Plano completo com sessÃµes diÃ¡rias no calendÃ¡rio, tarefas por tÃ³pico, flashcards SRS e resumo inicial.</p>
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3 py-4">
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
            <Input
              placeholder="Buscar por titulo ou arquivo..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <select
              value={artifactTypeFilter}
              onChange={e => setArtifactTypeFilter(e.target.value)}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              <option value="all">Todos os tipos</option>
              {(filterOptions?.artifact_types ?? []).map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
            <select
              value={templateFilter}
              onChange={e => setTemplateFilter(e.target.value)}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              <option value="all">Todos os templates</option>
              {(filterOptions?.template_ids ?? []).map(templateId => (
                <option key={templateId} value={templateId}>{templateId}</option>
              ))}
            </select>
            <select
              value={sourceDocFilter}
              onChange={e => setSourceDocFilter(e.target.value)}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              <option value="all">Todos os documentos</option>
              {(filterOptions?.source_doc_ids ?? []).map(sourceDocId => (
                <option key={sourceDocId} value={sourceDocId}>{sourceDocId}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
            <select
              value={generationProfileFilter}
              onChange={e => setGenerationProfileFilter(e.target.value)}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              <option value="all">Todos os perfis</option>
              {(filterOptions?.generation_profiles ?? []).map(profile => (
                <option key={profile} value={profile}>{profile}</option>
              ))}
            </select>
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as (typeof ARTIFACT_SORT_OPTIONS)[number]['value'])}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              {ARTIFACT_SORT_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select
              value={sortOrder}
              onChange={e => setSortOrder(e.target.value as 'asc' | 'desc')}
              className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100"
            >
              <option value="desc">Descendente</option>
              <option value="asc">Ascendente</option>
            </select>
            <Button
              variant="outline"
              onClick={() => {
                setSearch('')
                setArtifactTypeFilter('all')
                setTemplateFilter('all')
                setSourceDocFilter('all')
                setGenerationProfileFilter('all')
                setSortBy('created_at')
                setSortOrder('desc')
              }}
            >
              Limpar filtros
            </Button>
          </div>
        </CardContent>
      </Card>

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
                        {typeLabel ? `${typeLabel} Â· ` : ''}{formatBytes(artifact.size)} Â· {formatDate(artifact.created_at)}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {artifact.template_id && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-300">
                            Template: {artifact.template_id}
                          </span>
                        )}
                        {artifact.generation_profile && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-300">
                            Perfil: {artifact.generation_profile}
                          </span>
                        )}
                        {(artifact.source_doc_count ?? 0) > 0 && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-300">
                            Fontes: {artifact.source_doc_count}
                          </span>
                        )}
                        {(artifact.confidence_level || typeof artifact.confidence_score === 'number') && (
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${confidenceBadgeClass(artifact.confidence_level)}`}>
                            Confianca: {artifact.confidence_level ?? 'n/a'}
                            {typeof artifact.confidence_score === 'number' ? ` (${Math.round(artifact.confidence_score * 100)}%)` : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    {isMarkdown && (
                      <Button variant="ghost" size="sm" onClick={() => setPreviewFile({ id: artifact.id, filename: artifact.filename })}>
                        <Eye className="h-4 w-4 mr-1" />Preview
                      </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => handleDownload(artifact.id, artifact.filename)} disabled={downloadingKey !== null}>
                      <Download className="h-4 w-4 mr-1" />
                      {downloadingKey === `${artifact.id}:file` ? 'Baixando...' : 'Download'}
                    </Button>
                    {isMarkdown && (
                      <Button variant="outline" size="sm" onClick={() => handleDownloadPdf(artifact.id, artifact.filename)} disabled={downloadingKey !== null}>
                        <FileText className="h-4 w-4 mr-1" />
                        {downloadingKey === `${artifact.id}:pdf` ? 'Baixando...' : 'PDF'}
                      </Button>
                    )}
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => { if (confirm(`Remover "${artifact.filename}"?`)) deleteMut.mutate(artifact.id) }}
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

      {showSummarize && (
        <SummarizeDocDialog
          onClose={() => setShowSummarize(false)}
          templatesEnabled={templatesEnabled}
        />
      )}
      {showDigest && <SmartDigestDialog onClose={() => setShowDigest(false)} />}
      {showCreate && (
        <CreateArtifactDialog
          onClose={() => setShowCreate(false)}
          templatesEnabled={templatesEnabled}
        />
      )}
      {previewFile && <PreviewDialog artifact={previewFile} onClose={() => setPreviewFile(null)} />}
    </PageShell>
  )
}


