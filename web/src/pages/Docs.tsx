import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, BookOpen, GitCompare, Loader2, Search, Download, Trash2, Zap, CheckSquare, Brain, CalendarDays, GraduationCap } from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type DocItem } from '@/api/client'

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

function SummarizeDialog({
  doc,
  onClose,
}: {
  doc: string
  onClose: () => void
}) {
  const [result, setResult] = useState('')
  const [mode, setMode] = useState<'brief' | 'deep'>('brief')
  const [saveSummary, setSaveSummary] = useState(true)
  const [artifactFilename, setArtifactFilename] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<'md' | 'pdf' | null>(null)

  const startJob = useMutation({
    mutationFn: () => apiClient.summarizeAsync(doc, saveSummary, mode),
    onSuccess: data => {
      setJobId(data.job_id)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao iniciar resumo'),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: query =>
      query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed'
        ? false
        : 1200,
  })

  useEffect(() => {
    if (!jobId || !jobQuery.data) return
    if (jobQuery.data.status === 'succeeded') {
      const payload = jobQuery.data.result ?? {}
      setResult(String(payload.answer ?? ''))
      setArtifactFilename(payload.artifact_filename ?? null)
      if (saveSummary && payload.artifact_filename) {
        toast.success(`Resumo salvo: ${payload.artifact_filename}`)
      }
      setJobId(null)
    } else if (jobQuery.data.status === 'failed') {
      toast.error(jobQuery.data.error ?? 'Erro ao gerar resumo')
      setJobId(null)
    }
  }, [jobId, jobQuery.data, saveSummary])

  const modeLabel = mode === 'brief' ? 'Resumo Breve' : 'Resumo Aprofundado'
  const isProcessing = startJob.isPending || !!jobId

  async function handleDownloadMd() {
    if (!artifactFilename) return
    setDownloading('md')
    try {
      const blob = await apiClient.getArtifactBlob(artifactFilename)
      downloadBlobFile(blob, artifactFilename)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar .md')
    } finally {
      setDownloading(null)
    }
  }

  async function handleDownloadPdf() {
    if (!artifactFilename) return
    setDownloading('pdf')
    try {
      const blob = await apiClient.getArtifactPdfBlob(artifactFilename)
      const pdfName = artifactFilename.replace(/\.(md|markdown|txt)$/i, '.pdf')
      downloadBlobFile(blob, pdfName)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar PDF')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Resumo: {doc}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>
        <div className="p-6 space-y-4">
          {!result && !isProcessing && (
            <>
              {/* Mode selector */}
              <div>
                <p className="mb-2 text-sm font-medium text-zinc-300">Tipo de resumo:</p>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setMode('brief')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                      mode === 'brief'
                        ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                        : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <p className="text-sm font-semibold">Resumo Breve</p>
                    <p className="mt-0.5 text-xs opacity-70">
                      Síntese concisa — até 300 palavras com os pontos essenciais
                    </p>
                  </button>
                  <button
                    onClick={() => setMode('deep')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                      mode === 'deep'
                        ? 'border-violet-500 bg-violet-500/10 text-violet-300'
                        : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <p className="text-sm font-semibold">Resumo Aprofundado</p>
                    <p className="mt-0.5 text-xs opacity-70">
                      Análise completa seção por seção com detalhes técnicos
                    </p>
                  </button>
                </div>
              </div>
              <label className="flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200">
                <input
                  type="checkbox"
                  checked={saveSummary}
                  onChange={e => setSaveSummary(e.target.checked)}
                />
                Salvar resumo em artefatos (habilita exportação .md e PDF)
              </label>
              <Button onClick={() => startJob.mutate()} className="w-full">
                <BookOpen className="mr-2 h-4 w-4" />
                Gerar {modeLabel}
              </Button>
            </>
          )}
          {isProcessing && (
            <div className="flex flex-col items-center justify-center gap-3 py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
              <span className="text-sm text-zinc-400">
                {mode === 'deep'
                  ? 'Analisando documento em profundidade...'
                  : 'Gerando resumo breve...'}
              </span>
              <div className="w-full max-w-md rounded-md border border-zinc-700 bg-zinc-800 p-2">
                <div className="mb-1 flex items-center justify-between text-[11px] text-zinc-400">
                  <span>{jobQuery.data?.stage ?? 'iniciando'}</span>
                  <span>{jobQuery.data?.progress ?? 5}%</span>
                </div>
                <div className="h-2 rounded bg-zinc-700">
                  <div
                    className="h-2 rounded bg-blue-500 transition-all"
                    style={{ width: `${jobQuery.data?.progress ?? 5}%` }}
                  />
                </div>
              </div>
            </div>
          )}
          {result && (
            <>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  mode === 'brief'
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'bg-violet-500/15 text-violet-300'
                }`}>
                  {modeLabel}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-300"
                  onClick={() => {
                    setResult('')
                    setArtifactFilename(null)
                    startJob.reset()
                  }}
                >
                  Gerar outro
                </Button>
              </div>
              {artifactFilename && (
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={handleDownloadMd} disabled={downloading !== null}>
                    <Download className="mr-2 h-4 w-4" />
                    {downloading === 'md' ? 'Baixando...' : 'Exportar .md'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading !== null}>
                    <FileText className="mr-2 h-4 w-4" />
                    {downloading === 'pdf' ? 'Baixando...' : 'Exportar PDF'}
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

function CompareDialog({
  doc1,
  allDocs,
  onClose,
}: {
  doc1: string
  allDocs: DocItem[]
  onClose: () => void
}) {
  const [doc2, setDoc2] = useState('')
  const [result, setResult] = useState('')

  const mutation = useMutation({
    mutationFn: () => apiClient.compare(doc1, doc2, false),
    onSuccess: data => setResult(data.answer),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao comparar'),
  })

  const others = allDocs.filter(d => d.file_name !== doc1)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Comparar: {doc1}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>
        <div className="p-6 space-y-4">
          {!result && (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                  Comparar com:
                </label>
                <select
                  value={doc2}
                  onChange={e => setDoc2(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  <option value="">Selecione um documento</option>
                  {others.map(d => (
                    <option key={d.file_name} value={d.file_name}>
                      {d.file_name}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                onClick={() => mutation.mutate()}
                disabled={!doc2 || mutation.isPending}
                className="w-full"
              >
                {mutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Comparando...
                  </>
                ) : (
                  <>
                    <GitCompare className="mr-2 h-4 w-4" />
                    Comparar
                  </>
                )}
              </Button>
            </>
          )}
          {result && (
            <div className="prose prose-invert prose-sm max-w-none max-h-96 overflow-y-auto">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SmartDigestDialog({ doc, onClose }: { doc: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'digest' | 'plan'>('digest')

  // Digest state
  const [genFlashcards, setGenFlashcards] = useState(true)
  const [extractTasks, setExtractTasks] = useState(true)
  const [scheduleReviews, setScheduleReviews] = useState(false)
  const [numCards, setNumCards] = useState(10)
  const [digestResult, setDigestResult] = useState<{
    summary: string; deck_id: number | null; tasks_created: number
    task_titles: string[]; reviews_scheduled: number
  } | null>(null)

  // Study plan state
  const [hoursPerDay, setHoursPerDay] = useState(2)
  const [deadlineDate, setDeadlineDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 14)
    return d.toISOString().split('T')[0]
  })
  const [planGenFlashcards, setPlanGenFlashcards] = useState(true)
  const [planNumCards, setPlanNumCards] = useState(15)
  const [planResult, setPlanResult] = useState<{
    plan_text: string; tasks_created: number; reminders_created: number
    sessions_count: number; deck_id: number | null; titulo: string
  } | null>(null)

  const digestMutation = useMutation({
    mutationFn: () =>
      apiClient.digestDocument(doc, { generateFlashcards: genFlashcards, extractTasks, numCards, maxTasks: 8, scheduleReviews }),
    onSuccess: data => {
      setDigestResult(data)
      if (data.deck_id) qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      if (data.tasks_created > 0) qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Smart Digest concluído!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro no Smart Digest'),
  })

  const planMutation = useMutation({
    mutationFn: () =>
      apiClient.createStudyPlanFromDoc(doc, hoursPerDay, deadlineDate, planGenFlashcards, planNumCards),
    onSuccess: data => {
      setPlanResult(data)
      if (data.deck_id) qc.invalidateQueries({ queryKey: ['flashcard-decks'] })
      if (data.tasks_created > 0) qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['reminders'] })
      toast.success('Plano de estudos criado!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao criar plano'),
  })

  const isProcessing = digestMutation.isPending || planMutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-amber-400" />
            <h2 className="font-semibold text-zinc-100 truncate max-w-xs">{doc}</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>

        {/* Tab bar */}
        {!isProcessing && !digestResult && !planResult && (
          <div className="flex border-b border-zinc-800 shrink-0">
            <button
              onClick={() => setTab('digest')}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
                tab === 'digest'
                  ? 'border-b-2 border-amber-500 text-amber-400 bg-amber-500/5'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <Zap className="h-4 w-4" /> Smart Digest
            </button>
            <button
              onClick={() => setTab('plan')}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
                tab === 'plan'
                  ? 'border-b-2 border-emerald-500 text-emerald-400 bg-emerald-500/5'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <GraduationCap className="h-4 w-4" /> Plano de Estudos
            </button>
          </div>
        )}

        <div className="p-6 space-y-4 overflow-y-auto flex-1">

          {/* ── SMART DIGEST TAB ── */}
          {tab === 'digest' && !digestResult && !digestMutation.isPending && (
            <>
              <p className="text-sm text-zinc-400">
                Gera resumo analítico, cria flashcards e extrai tarefas do documento em uma operação.
              </p>
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
              <Button onClick={() => digestMutation.mutate()} className="w-full bg-amber-600 hover:bg-amber-700 text-white">
                <Zap className="mr-2 h-4 w-4" />
                Executar Smart Digest
              </Button>
            </>
          )}

          {/* ── PLANO DE ESTUDOS TAB ── */}
          {tab === 'plan' && !planResult && !planMutation.isPending && (
            <>
              <p className="text-sm text-zinc-400">
                Gera um plano de estudos personalizado com sessões diárias no calendário, tarefas por tópico e flashcards.
              </p>
              <div className="space-y-4">
                {/* Horas por dia */}
                <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-zinc-200">Horas de estudo por dia</p>
                    <span className="text-sm font-bold text-emerald-400">{hoursPerDay}h</span>
                  </div>
                  <input
                    type="range" min={0.5} max={8} step={0.5}
                    value={hoursPerDay}
                    onChange={e => setHoursPerDay(Number(e.target.value))}
                    className="w-full accent-emerald-500"
                  />
                  <div className="flex justify-between text-xs text-zinc-600 mt-1">
                    <span>30min</span><span>4h</span><span>8h</span>
                  </div>
                </div>

                {/* Prazo */}
                <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3">
                  <div className="flex items-center gap-2 mb-2">
                    <CalendarDays className="h-4 w-4 text-zinc-400" />
                    <p className="text-sm font-medium text-zinc-200">Data limite para concluir</p>
                  </div>
                  <input
                    type="date"
                    value={deadlineDate}
                    min={new Date(Date.now() + 86400000).toISOString().split('T')[0]}
                    onChange={e => setDeadlineDate(e.target.value)}
                    className="w-full rounded-md border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                  {deadlineDate && (() => {
                    const days = Math.ceil((new Date(deadlineDate).getTime() - Date.now()) / 86400000)
                    const total = Math.round(days * hoursPerDay)
                    return (
                      <p className="text-xs text-zinc-500 mt-1.5">
                        {days} dias · ~{total}h no total · {Math.round(total / Math.max(1, days * hoursPerDay * 0.1))} sessões estimadas
                      </p>
                    )
                  })()}
                </div>

                {/* Flashcards */}
                <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                  <input type="checkbox" checked={planGenFlashcards} onChange={e => setPlanGenFlashcards(e.target.checked)} className="h-4 w-4 accent-blue-500" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-zinc-200">Gerar Flashcards</p>
                    <p className="text-xs text-zinc-500">Cria deck + revisões SRS após o prazo do plano</p>
                  </div>
                </label>
                {planGenFlashcards && (
                  <div className="ml-7 flex items-center gap-3">
                    <span className="text-xs text-zinc-400 shrink-0">Cards:</span>
                    <input type="range" min={5} max={30} step={5} value={planNumCards} onChange={e => setPlanNumCards(Number(e.target.value))} className="flex-1" />
                    <span className="text-xs font-medium text-blue-400 w-8 text-right">{planNumCards}</span>
                  </div>
                )}
              </div>
              <Button
                onClick={() => planMutation.mutate()}
                disabled={!deadlineDate}
                className="w-full bg-emerald-700 hover:bg-emerald-600 text-white"
              >
                <GraduationCap className="mr-2 h-4 w-4" />
                Criar Plano de Estudos
              </Button>
            </>
          )}

          {/* ── LOADING ── */}
          {digestMutation.isPending && (
            <div className="flex flex-col items-center justify-center gap-3 py-10">
              <Brain className="h-8 w-8 animate-pulse text-amber-400" />
              <span className="text-sm text-zinc-400">Analisando documento...</span>
              <span className="text-xs text-zinc-600">Gerando resumo, flashcards e extraindo tarefas</span>
            </div>
          )}
          {planMutation.isPending && (
            <div className="flex flex-col items-center justify-center gap-3 py-10">
              <GraduationCap className="h-8 w-8 animate-pulse text-emerald-400" />
              <span className="text-sm text-zinc-400">Criando plano de estudos...</span>
              <span className="text-xs text-zinc-600">Gerando tópicos, sessões e tarefas com IA</span>
            </div>
          )}

          {/* ── DIGEST RESULT ── */}
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

          {/* ── STUDY PLAN RESULT ── */}
          {planResult && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3">
                  <p className="text-xs text-emerald-400 font-medium mb-1">Tarefas criadas</p>
                  <p className="text-lg font-bold text-emerald-300">{planResult.tasks_created}</p>
                  <a href="/tasks" className="text-xs text-emerald-500 hover:underline">Ver Tarefas →</a>
                </div>
                <div className="rounded-lg border border-blue-800 bg-blue-950/30 p-3">
                  <p className="text-xs text-blue-400 font-medium mb-1">Sessões no calendário</p>
                  <p className="text-lg font-bold text-blue-300">{planResult.sessions_count}</p>
                  <a href="/schedule" className="text-xs text-blue-500 hover:underline">Ver Calendário →</a>
                </div>
                {planResult.deck_id && (
                  <div className="rounded-lg border border-purple-800 bg-purple-950/30 p-3">
                    <p className="text-xs text-purple-400 font-medium mb-1">Flashcards + SRS</p>
                    <p className="text-lg font-bold text-purple-300">{planNumCards} cards</p>
                    <a href="/flashcards" className="text-xs text-purple-500 hover:underline">Ver Flashcards →</a>
                  </div>
                )}
              </div>
              <div>
                <p className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
                  <GraduationCap className="h-3 w-3" /> Plano:
                </p>
                <div className="prose prose-invert prose-xs max-w-none max-h-72 overflow-y-auto rounded-lg bg-zinc-800 p-3">
                  <ReactMarkdown>{planResult.plan_text}</ReactMarkdown>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => { setPlanResult(null); planMutation.reset() }} className="w-full">
                Criar outro plano
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function Docs() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [summarizeDoc, setSummarizeDoc] = useState<string | null>(null)
  const [compareDoc, setCompareDoc] = useState<string | null>(null)
  const [digestDoc, setDigestDoc] = useState<string | null>(null)

  const { data: docs, isLoading, error } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const deleteMut = useMutation({
    mutationFn: (docId: string) => apiClient.deleteDoc(docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docs'] })
      toast.success('Documento removido.')
    },
    onError: () => toast.error('Erro ao remover documento.'),
  })

  const filtered = docs?.filter(d =>
    d.file_name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Documentos Indexados</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Gerencie e opere sobre seus documentos
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <Input
          placeholder="Buscar documento..."
          className="pl-10"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Erro ao carregar documentos. Certifique-se que o servidor está rodando.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {!isLoading && (!filtered || filtered.length === 0) && !error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <FileText className="h-12 w-12 text-zinc-600" />
            <p className="font-medium text-zinc-300">
              {search ? 'Nenhum documento encontrado' : 'Nenhum documento indexado'}
            </p>
            <p className="text-sm text-zinc-500">
              {search
                ? 'Tente outro termo de busca'
                : 'Use a página de Inserção para adicionar documentos'}
            </p>
          </CardContent>
        </Card>
      )}

      {filtered && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map(doc => (
            <Card key={doc.file_name} className="hover:border-zinc-700 transition-colors">
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText className="h-5 w-5 shrink-0 text-blue-400" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-100 truncate">
                      {doc.file_name}
                    </p>
                    <p className="text-xs text-zinc-500 truncate">{doc.source}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  <Badge variant="secondary">{doc.chunk_count} chunks</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDigestDoc(doc.file_name)}
                    className="text-amber-400 hover:text-amber-300"
                    title="Smart Digest: resumo + flashcards + tarefas"
                  >
                    <Zap className="h-4 w-4" />
                    Digest
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSummarizeDoc(doc.file_name)}
                  >
                    <BookOpen className="h-4 w-4" />
                    Resumir
                  </Button>
                  {docs && docs.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCompareDoc(doc.file_name)}
                    >
                      <GitCompare className="h-4 w-4" />
                      Comparar
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Remover "${doc.file_name}"? Esta ação não pode ser desfeita.`)) {
                        deleteMut.mutate(doc.doc_id)
                      }
                    }}
                    disabled={deleteMut.isPending}
                    className="text-zinc-600 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialogs */}
      {summarizeDoc && (
        <SummarizeDialog doc={summarizeDoc} onClose={() => setSummarizeDoc(null)} />
      )}
      {compareDoc && docs && (
        <CompareDialog
          doc1={compareDoc}
          allDocs={docs}
          onClose={() => setCompareDoc(null)}
        />
      )}
      {digestDoc && (
        <SmartDigestDialog doc={digestDoc} onClose={() => setDigestDoc(null)} />
      )}
    </div>
  )
}
