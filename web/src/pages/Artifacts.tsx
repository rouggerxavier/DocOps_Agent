import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Archive, BookOpen, Brain, CheckSquare, ChevronDown, Download, Eye,
  FileText, GraduationCap, Loader2, Plus, Search, SlidersHorizontal,
  Trash2, X, Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type ArtifactFilterOptions, type ArtifactItem, type ArtifactTemplate, type DocItem } from '@/api/client'
import { useCapabilities } from '@/features/CapabilitiesProvider'
import { trackPremiumFeatureActivation, trackPremiumTouchpointViewed, trackUpgradeCompleted, trackUpgradeInitiated } from '@/features/premiumAnalytics'
import { formatBytes, formatDate } from '@/lib/utils'

const MARKDOWN_FILE_RE = /\.(md|markdown|txt)$/i
const ARTIFACT_SORT_OPTIONS = [
  { value: 'created_at', label: 'Mais recentes' },
  { value: 'title', label: 'Titulo (A-Z)' },
  { value: 'artifact_type', label: 'Tipo' },
  { value: 'confidence_score', label: 'Confiança' },
] as const


function pickDefaultTemplate(
  templates: ArtifactTemplate[],
  options: { summaryMode?: 'brief' | 'deep'; artifactType?: string }
): string {
  const availableTemplates = templates.filter(item => !item.locked)
  if (!availableTemplates.length) return ''
  if (options.summaryMode) {
    const byMode = availableTemplates.find(item => item.default_for_summary_modes.includes(options.summaryMode!))
    if (byMode) return byMode.template_id
  }
  if (options.artifactType) {
    const byType = availableTemplates.find(item => item.default_for_artifact_types.includes(options.artifactType!))
    if (byType) return byType.template_id
  }
  return availableTemplates[0]?.template_id ?? ''
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

// ── Generic Custom Select ─────────────────────────────────────────────────────

interface SelectOption { value: string; label: string }
function FilterSelect({
  options,
  value,
  onChange,
  placeholder = 'Selecione...',
}: {
  options: SelectOption[]
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [])

  const selectedLabel = options.find(o => o.value === value)?.label ?? placeholder

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-2 h-10 px-3 rounded-lg bg-[#111111] border border-[#282828] text-sm text-[#e1e3e4] hover:border-primary/40 transition-colors"
      >
        <span className="truncate text-left">{selectedLabel}</span>
        <ChevronDown className={`h-4 w-4 text-[#c6c5d4] shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-[#282828] bg-[#111111] shadow-xl overflow-hidden max-h-52 overflow-y-auto">
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-[#1e1e1e] ${
                value === opt.value ? 'text-primary font-medium' : 'text-[#e1e3e4]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── DocSelector (named custom dropdown for doc lists) ─────────────────────────

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

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [])

  const selectedLabel = docs.find(d => d.file_name === value)?.file_name ?? 'Selecione um documento'

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-2 h-10 px-3 rounded-lg bg-[#1e1e1e] border border-[#282828] text-sm text-[#e1e3e4] hover:border-primary/40 transition-colors"
      >
        <span className="truncate text-left">{selectedLabel}</span>
        <ChevronDown className={`h-4 w-4 text-[#c6c5d4] shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-[#282828] bg-[#111111] shadow-xl overflow-hidden max-h-52 overflow-y-auto">
          <button
            type="button"
            onClick={() => { onChange(''); setOpen(false) }}
            className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-[#1e1e1e] ${!value ? 'text-primary font-medium' : 'text-[#c6c5d4]'}`}
          >
            Selecione um documento
          </button>
          {docs.map(d => (
            <button
              key={d.file_name}
              type="button"
              onClick={() => { onChange(d.file_name); setOpen(false) }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-[#1e1e1e] ${value === d.file_name ? 'text-primary font-medium' : 'text-[#e1e3e4]'}`}
            >
              {d.file_name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Resumir Documento Dialog ──────────────────────────────────────────────────

function SummarizeDocDialog({
  onClose,
  templatesFeatureEnabled,
  templatesUnlocked,
  entitlementTier,
  onRefreshAccess,
}: {
  onClose: () => void
  templatesFeatureEnabled: boolean
  templatesUnlocked: boolean
  entitlementTier: string
  onRefreshAccess?: () => Promise<void> | void
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
    enabled: templatesFeatureEnabled,
    staleTime: 60_000,
    retry: 1,
  })
  const templateOptions = useMemo(() => templates ?? [], [templates])
  const templatesLocked = templatesFeatureEnabled && !templatesUnlocked
  const selectedTemplate = useMemo(
    () => templateOptions.find(item => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templateOptions]
  )
  const selectedTemplateIsLocked = Boolean(selectedTemplate?.locked)

  useEffect(() => {
    if (!templatesLocked) return
    trackPremiumTouchpointViewed({
      touchpoint: 'artifacts.summarize_templates',
      capability: 'premium_artifact_templates',
      metadata: { surface: 'artifacts', dialog: 'summarize' },
    })
  }, [templatesLocked])

  useEffect(() => {
    if (!templatesFeatureEnabled) return
    if (!templateOptions.length) { setSelectedTemplateId(''); return }
    const hasActive = templateOptions.some(item => item.template_id === selectedTemplateId && !item.locked)
    if (hasActive) return
    setSelectedTemplateId(pickDefaultTemplate(templateOptions, { summaryMode: mode, artifactType: 'summary' }))
  }, [mode, selectedTemplateId, templateOptions, templatesFeatureEnabled])

  const templateIdForRequest = (
    templatesFeatureEnabled
    && selectedTemplateId
    && !selectedTemplateIsLocked
  )
    ? selectedTemplateId
    : undefined

  const startJob = useMutation({
    mutationFn: () => apiClient.summarizeAsync(
      selectedDoc, true, mode,
      templateIdForRequest,
    ),
    onSuccess: data => setJobId(data.job_id),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao iniciar resumo'),
  })

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: query =>
      query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed' ? false : 1200,
  })

  useEffect(() => {
    if (!jobId || !jobQuery.data) return
    if (jobQuery.data.status === 'succeeded') {
      const payload = jobQuery.data.result ?? {}
      setResult(String(payload.answer ?? ''))
      setArtifactFilename(payload.artifact_filename ?? null)
      setResultTemplateLabel(payload.template_label ? String(payload.template_label) : null)
      if (templatesFeatureEnabled && templatesUnlocked) {
        trackPremiumFeatureActivation({
          touchpoint: 'artifacts.summarize_templates',
          capability: 'premium_artifact_templates',
          metadata: {
            surface: 'artifacts',
            template_id: payload.template_id ? String(payload.template_id) : null,
            summary_mode: mode,
          },
        })
      }
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
  }, [jobId, jobQuery.data, mode, qc, templatesFeatureEnabled, templatesUnlocked])

  const modeLabel = mode === 'brief' ? 'Resumo Breve' : 'Resumo Aprofundado'
  const isProcessing = startJob.isPending || !!jobId

  async function handleDownloadMd() {
    if (!artifactFilename) return
    setDownloading('md')
    try { const blob = await apiClient.getArtifactBlob(artifactFilename); downloadBlobFile(blob, artifactFilename) }
    catch { toast.error('Erro ao baixar .md') } finally { setDownloading(null) }
  }

  async function handleDownloadPdf() {
    if (!artifactFilename) return
    setDownloading('pdf')
    try { const blob = await apiClient.getArtifactPdfBlob(artifactFilename); downloadBlobFile(blob, toPdfName(artifactFilename)) }
    catch { toast.error('Erro ao baixar PDF') } finally { setDownloading(null) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 overflow-y-auto">
      <div className="w-full max-w-2xl rounded-2xl border border-[#1e1e1e] bg-[#0d0d0d] shadow-2xl shadow-black/60 my-auto">

        {/* ── Close button ── */}
        <div className="flex justify-end px-6 pt-5">
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-[#1e1e1e] text-[#c6c5d4] transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {result ? (
          /* ── Result view ── */
          <div className="px-8 pb-8 space-y-4">
            <div className="flex items-center justify-between">
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${mode === 'brief' ? 'bg-primary/15 text-primary' : 'bg-violet-500/15 text-violet-300'}`}>
                {modeLabel}{resultTemplateLabel ? ` — ${resultTemplateLabel}` : ''}
              </span>
              <button
                className="text-xs text-[#c6c5d4] hover:text-[#e1e3e4] transition-colors"
                onClick={() => { setResult(''); setArtifactFilename(null); setResultTemplateLabel(null); startJob.reset() }}
              >
                ← Gerar outro
              </button>
            </div>
            {artifactFilename && (
              <div className="flex flex-wrap gap-2">
                <button onClick={handleDownloadMd} disabled={downloading !== null} className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#282828] bg-[#1e1e1e] text-sm text-[#e1e3e4] hover:border-primary/40 transition-colors disabled:opacity-50">
                  <Download className="h-3.5 w-3.5" />{downloading === 'md' ? 'Baixando...' : 'Exportar .md'}
                </button>
                <button onClick={handleDownloadPdf} disabled={downloading !== null} className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#282828] bg-[#1e1e1e] text-sm text-[#e1e3e4] hover:border-primary/40 transition-colors disabled:opacity-50">
                  <FileText className="h-3.5 w-3.5" />{downloading === 'pdf' ? 'Baixando...' : 'Exportar PDF'}
                </button>
              </div>
            )}
            <div className="prose prose-invert prose-sm max-w-none max-h-[32rem] overflow-y-auto rounded-xl bg-[#1e1e1e] p-4">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          </div>
        ) : isProcessing ? (
          /* ── Processing view ── */
          <div className="px-8 pb-10 flex flex-col items-center gap-4">
            {/* Kicker */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#1e1e1e] border border-[#282828]/40 mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shadow-[0_0_8px_rgba(147,197,253,0.6)]" />
              <span className="text-[10px] uppercase tracking-widest font-bold text-[#c6c5d4]">Processando</span>
            </div>
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-base font-semibold text-[#e1e3e4] text-center">
              {mode === 'deep' ? 'Analisando documento em profundidade...' : 'Gerando resumo breve...'}
            </p>
            <div className="w-full rounded-xl border border-[#1e1e1e] bg-[#111111] p-3">
              <div className="mb-2 flex justify-between text-[11px] text-[#c6c5d4]">
                <span>{jobQuery.data?.stage ?? 'iniciando'}</span>
                <span>{jobQuery.data?.progress ?? 5}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-[#1e1e1e]">
                <div className="h-1.5 rounded-full bg-gradient-to-r from-primary to-primary/60 transition-all" style={{ width: `${jobQuery.data?.progress ?? 5}%` }} />
              </div>
            </div>
          </div>
        ) : (
          /* ── Config view ── */
          <div className="px-8 pb-8 space-y-6">
            {/* Kicker + headline */}
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#1e1e1e] border border-[#282828]/40">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.5)]" />
                <span className="text-[10px] uppercase tracking-widest font-bold text-[#c6c5d4]">Inteligência Artificial</span>
              </div>
              <h2 className="text-3xl font-headline font-extrabold text-[#e1e3e4] tracking-tight leading-tight">
                Configuração do Resumo
              </h2>
              <p className="text-[#c6c5d4] text-sm leading-relaxed">
                Transforme documentos extensos em inteligência estruturada através do motor de análise semântica.
              </p>
            </div>

            {/* Document selector */}
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-[#c6c5d4]">Documento de Origem</label>
              <DocSelector docs={docs ?? []} value={selectedDoc} onChange={setSelectedDoc} />
            </div>

            {/* Type cards */}
            <div>
              <p className="mb-3 text-xs font-bold uppercase tracking-widest text-[#c6c5d4]">Tipo de Análise</p>
              <div className="grid grid-cols-2 gap-4">
                {/* Resumo Breve */}
                <button
                  onClick={() => setMode('brief')}
                  className={`relative rounded-xl p-5 text-left transition-all duration-300 border-2 ${
                    mode === 'brief'
                      ? 'bg-[#1e1e1e] border-primary/60 shadow-[0_0_24px_rgba(147,197,253,0.08)]'
                      : 'bg-[#111111] border-transparent hover:bg-[#151515]'
                  }`}
                >
                  {mode === 'brief' && (
                    <div className="absolute top-3 right-3 text-primary">
                      <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z" style={{display:'none'}}/></svg>
                    </div>
                  )}
                  {mode === 'brief' && (
                    <span className="absolute top-3 right-3 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[#001e30]">
                      <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </span>
                  )}
                  <div className={`w-12 h-12 rounded-lg mb-4 flex items-center justify-center ${mode === 'brief' ? 'bg-primary/10' : 'bg-[#1e1e1e]'}`}>
                    <BookOpen className={`h-6 w-6 ${mode === 'brief' ? 'text-primary' : 'text-[#c6c5d4]'}`} />
                  </div>
                  <h3 className="text-base font-headline font-bold text-[#e1e3e4] mb-1">Resumo Breve</h3>
                  <p className="text-xs text-[#c6c5d4] leading-relaxed mb-4">
                    Síntese executiva focada nos pontos cruciais. Ideal para leituras rápidas e tomada de decisão.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${mode === 'brief' ? 'bg-primary/20 text-primary' : 'bg-[#0a0a0a] text-[#c6c5d4]'}`}>
                      Até 300 palavras
                    </span>
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${mode === 'brief' ? 'bg-primary/20 text-primary' : 'bg-[#0a0a0a] text-[#c6c5d4]'}`}>
                      Formato Lista
                    </span>
                  </div>
                </button>

                {/* Resumo Aprofundado */}
                <button
                  onClick={() => setMode('deep')}
                  className={`relative rounded-xl p-5 text-left transition-all duration-300 border-2 ${
                    mode === 'deep'
                      ? 'bg-[#1e1e1e] border-primary/60 shadow-[0_0_24px_rgba(147,197,253,0.08)]'
                      : 'bg-[#111111] border-transparent hover:bg-[#151515]'
                  }`}
                >
                  {mode === 'deep' && (
                    <span className="absolute top-3 right-3 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[#001e30]">
                      <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </span>
                  )}
                  <div className={`w-12 h-12 rounded-lg mb-4 flex items-center justify-center ${mode === 'deep' ? 'bg-primary/10' : 'bg-[#1e1e1e]'}`}>
                    <Brain className={`h-6 w-6 ${mode === 'deep' ? 'text-primary' : 'text-[#c6c5d4]'}`} />
                  </div>
                  <h3 className="text-base font-headline font-bold text-[#e1e3e4] mb-1">Resumo Aprofundado</h3>
                  <p className="text-xs text-[#c6c5d4] leading-relaxed mb-4">
                    Análise técnica completa, abrangendo metodologias, dados estatísticos e implicações de longo prazo.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${mode === 'deep' ? 'bg-primary/20 text-primary' : 'bg-[#0a0a0a] text-[#c6c5d4]'}`}>
                      Análise Ilimitada
                    </span>
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${mode === 'deep' ? 'bg-primary/20 text-primary' : 'bg-[#0a0a0a] text-[#c6c5d4]'}`}>
                      Seção por Seção
                    </span>
                  </div>
                </button>
              </div>
            </div>

            {/* Templates (premium) */}
            {templatesFeatureEnabled && templateOptions.length > 0 && (
              <div>
                <p className="mb-3 text-xs font-bold uppercase tracking-widest text-[#c6c5d4]">Template de Saída</p>
                <div className="grid gap-2 md:grid-cols-3">
                  {templateOptions.map(template => (
                    <button
                      key={template.template_id}
                      type="button"
                      onClick={() => {
                        if (template.locked) return
                        setSelectedTemplateId(template.template_id)
                      }}
                      disabled={Boolean(template.locked)}
                      className={`rounded-xl border px-3 py-2.5 text-left transition-all ${
                        template.locked
                          ? 'cursor-not-allowed border-amber-700/35 bg-amber-950/15 text-amber-200/80'
                          : selectedTemplateId === template.template_id
                          ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
                          : 'border-[#1e1e1e] bg-[#111111] text-[#c6c5d4] hover:border-[#282828]'
                      }`}
                    >
                      <p className="text-sm font-semibold">
                        {template.label}
                        {template.locked ? ' (Premium)' : ''}
                      </p>
                      <p className="mt-0.5 text-xs opacity-80">{template.short_description}</p>
                    </button>
                  ))}
                </div>
                {selectedTemplate && (
                  <div className="mt-2 rounded-xl border border-[#1e1e1e] bg-[#111111] p-3">
                    <p className="text-xs font-medium text-[#e1e3e4]">{selectedTemplate.preview_title}</p>
                    <p className="mt-1 text-xs text-[#c6c5d4]">{selectedTemplate.long_description}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {selectedTemplate.preview_sections.map(section => (
                        <span key={section} className="rounded-full border border-[#282828] bg-[#0a0a0a] px-2 py-0.5 text-[11px] text-[#c6c5d4]">
                          {section}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {templatesLocked && (
                  <div className="mt-3 rounded-xl border border-amber-600/35 bg-amber-950/15 px-3 py-2.5">
                    <p className="text-xs font-medium text-amber-200">
                      Templates premium bloqueados no plano atual ({entitlementTier}).
                    </p>
                    <p className="mt-1 text-[11px] text-amber-100/85">
                      Faca upgrade para desbloquear templates e manter o formato premium no resumo.
                    </p>
                    <button
                      type="button"
                      onClick={() => { void onRefreshAccess?.() }}
                      className="mt-2 rounded-lg border border-amber-500/45 px-2.5 py-1 text-[11px] text-amber-100 transition-colors hover:bg-amber-500/10"
                    >
                      Ja fiz upgrade, atualizar acesso
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Footer: AI status + CTA */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-[#1e1e1e]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#1e1e1e] flex items-center justify-center border border-[#282828]">
                  <Brain className="h-5 w-5 text-[#c6c5d4] opacity-60" />
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[#c6c5d4]">Status do Processamento</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_6px_rgba(147,197,253,0.6)]" />
                    <span className="text-sm font-medium text-[#e1e3e4]">IA Pronta para Analisar</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => startJob.mutate()}
                disabled={!selectedDoc || isProcessing || selectedTemplateIsLocked}
                className="flex items-center gap-3 px-7 py-3 rounded-xl font-bold font-headline text-[#001e30] bg-gradient-to-br from-primary to-primary/70 shadow-[0_8px_24px_rgba(147,197,253,0.2)] hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100"
              >
                <span>Gerar Resumo</span>
                <Zap className="h-4 w-4" />
              </button>
            </div>

            {/* Stats bento */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Tempo Estimado', value: mode === 'deep' ? '~45 seg' : '~14 seg' },
                { label: 'Complexidade', value: mode === 'deep' ? 'Alta' : 'Baixa', accent: true },
                { label: 'Créditos de IA', value: 'Premium' },
              ].map(stat => (
                <div key={stat.label} className="bg-[#0a0a0a] p-4 rounded-xl border border-[#1e1e1e]">
                  <span className="text-[10px] text-[#c6c5d4] uppercase font-bold tracking-widest block mb-1">{stat.label}</span>
                  <p className={`text-xl font-headline font-bold ${stat.accent ? 'text-primary' : 'text-[#e1e3e4]'}`}>{stat.value}</p>
                </div>
              ))}
            </div>
          </div>
        )}
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 overflow-y-auto">
      <div className="w-full max-w-2xl rounded-2xl border border-[#1e1e1e] bg-[#0d0d0d] shadow-2xl shadow-black/60 my-auto">

        {/* ── Close button ── */}
        <div className="flex justify-end px-6 pt-5">
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-[#1e1e1e] text-[#c6c5d4] transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {digestResult ? (
          /* ── Result view ── */
          <div className="px-8 pb-8 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-400">
                Smart Digest — concluído
              </span>
              <button
                className="text-xs text-[#c6c5d4] hover:text-[#e1e3e4] transition-colors"
                onClick={() => { setDigestResult(null); digestMutation.reset() }}
              >
                ← Fazer novamente
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {digestResult.deck_id && (
                <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                  <p className="text-xs text-primary font-bold uppercase tracking-widest mb-1">Flashcards criados</p>
                  <p className="text-2xl font-headline font-bold text-primary">{numCards} cards</p>
                  <a href="/flashcards" className="text-xs text-primary/70 hover:text-primary transition-colors mt-1 block">Ver em Flashcards →</a>
                </div>
              )}
              {digestResult.tasks_created > 0 && (
                <div className="rounded-xl border border-emerald-700/30 bg-emerald-950/20 p-4">
                  <p className="text-xs text-emerald-400 font-bold uppercase tracking-widest mb-1">Tarefas extraídas</p>
                  <p className="text-2xl font-headline font-bold text-emerald-300">{digestResult.tasks_created}</p>
                  <a href="/tasks" className="text-xs text-emerald-500/70 hover:text-emerald-400 transition-colors mt-1 block">Ver em Tarefas →</a>
                </div>
              )}
              {digestResult.reviews_scheduled > 0 && (
                <div className="rounded-xl border border-purple-700/30 bg-purple-950/20 p-4">
                  <p className="text-xs text-purple-400 font-bold uppercase tracking-widest mb-1">Revisões SRS</p>
                  <p className="text-2xl font-headline font-bold text-purple-300">{digestResult.reviews_scheduled}</p>
                  <a href="/schedule" className="text-xs text-purple-500/70 hover:text-purple-400 transition-colors mt-1 block">Ver Calendário →</a>
                </div>
              )}
            </div>
            {digestResult.task_titles.length > 0 && (
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-[#c6c5d4] mb-2 flex items-center gap-1">
                  <CheckSquare className="h-3 w-3" /> Tarefas criadas
                </p>
                <ul className="space-y-1">
                  {digestResult.task_titles.map((t, i) => (
                    <li key={i} className="text-xs text-[#e1e3e4] flex items-start gap-2">
                      <span className="text-emerald-500 mt-0.5">✓</span>{t}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-[#c6c5d4] mb-2 flex items-center gap-1">
                <BookOpen className="h-3 w-3" /> Resumo gerado
              </p>
              <div className="prose prose-invert prose-xs max-w-none max-h-60 overflow-y-auto rounded-xl bg-[#111111] p-4">
                <ReactMarkdown>{digestResult.summary}</ReactMarkdown>
              </div>
            </div>
          </div>

        ) : digestMutation.isPending ? (
          /* ── Processing view ── */
          <div className="px-8 pb-10 flex flex-col items-center gap-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#1e1e1e] border border-[#282828]/40 mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.5)]" />
              <span className="text-[10px] uppercase tracking-widest font-bold text-[#c6c5d4]">Processando</span>
            </div>
            <Brain className="h-8 w-8 animate-pulse text-amber-400" />
            <p className="text-base font-semibold text-[#e1e3e4] text-center">Analisando documento...</p>
            <p className="text-xs text-[#8e9099] text-center">Gerando resumo, flashcards e extraindo tarefas</p>
          </div>

        ) : (
          /* ── Config view ── */
          <div className="px-8 pb-8 space-y-6">
            {/* Kicker + headline */}
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#1e1e1e] border border-[#282828]/40">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.5)]" />
                <span className="text-[10px] uppercase tracking-widest font-bold text-[#c6c5d4]">Automação Inteligente</span>
              </div>
              <h2 className="text-3xl font-headline font-extrabold text-[#e1e3e4] tracking-tight leading-tight">
                Configurar Smart Digest
              </h2>
              <p className="text-[#c6c5d4] text-sm leading-relaxed">
                Uma operação, três entregas: <strong className="text-[#e1e3e4]">resumo analítico</strong>, <strong className="text-[#e1e3e4]">flashcards</strong> para revisão espaçada e <strong className="text-[#e1e3e4]">tarefas</strong> extraídas automaticamente.
              </p>
            </div>

            {/* Document selector */}
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-[#c6c5d4]">Documento de Origem</label>
              <DocSelector docs={docs ?? []} value={selectedDoc} onChange={setSelectedDoc} />
            </div>

            {/* Option cards */}
            <div>
              <p className="mb-3 text-xs font-bold uppercase tracking-widest text-[#c6c5d4]">O que será gerado</p>
              <div className="space-y-2">

                {/* Flashcards card */}
                <button
                  type="button"
                  onClick={() => setGenFlashcards(v => !v)}
                  className={`w-full text-left rounded-xl border-2 p-4 transition-all duration-200 ${
                    genFlashcards
                      ? 'border-primary/50 bg-[#111111] shadow-[0_0_20px_rgba(147,197,253,0.06)]'
                      : 'border-transparent bg-[#111111] hover:bg-[#151515]'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${genFlashcards ? 'bg-primary/10' : 'bg-[#1e1e1e]'}`}>
                      <BookOpen className={`h-5 w-5 ${genFlashcards ? 'text-primary' : 'text-[#c6c5d4]'}`} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-bold font-headline text-[#e1e3e4]">Gerar Flashcards</p>
                        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${genFlashcards ? 'border-primary bg-primary' : 'border-[#454652]'}`}>
                          {genFlashcards && <svg className="h-2.5 w-2.5 text-[#001e30]" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                        </div>
                      </div>
                      <p className="text-xs text-[#c6c5d4] mt-0.5">Cria um deck de flashcards para revisão espaçada</p>
                      {genFlashcards && (
                        <div className="mt-3 flex items-center gap-3" onClick={e => e.stopPropagation()}>
                          <span className="text-xs text-[#c6c5d4] shrink-0">Quantidade:</span>
                          <input
                            type="range" min={5} max={30} step={5} value={numCards}
                            onChange={e => setNumCards(Number(e.target.value))}
                            className="flex-1"
                            style={{ background: `linear-gradient(to right, #93C5FD ${((numCards - 5) / 25) * 100}%, #282828 ${((numCards - 5) / 25) * 100}%)` }}
                          />
                          <span className="text-xs font-bold text-primary w-8 text-right font-mono">{numCards}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </button>

                {/* Extract tasks card */}
                <button
                  type="button"
                  onClick={() => setExtractTasks(v => !v)}
                  className={`w-full text-left rounded-xl border-2 p-4 transition-all duration-200 ${
                    extractTasks
                      ? 'border-emerald-500/40 bg-[#111111] shadow-[0_0_20px_rgba(52,211,153,0.04)]'
                      : 'border-transparent bg-[#111111] hover:bg-[#151515]'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${extractTasks ? 'bg-emerald-500/10' : 'bg-[#1e1e1e]'}`}>
                      <CheckSquare className={`h-5 w-5 ${extractTasks ? 'text-emerald-400' : 'text-[#c6c5d4]'}`} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-bold font-headline text-[#e1e3e4]">Extrair Tarefas</p>
                        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${extractTasks ? 'border-emerald-500 bg-emerald-500' : 'border-[#454652]'}`}>
                          {extractTasks && <svg className="h-2.5 w-2.5 text-[#001e30]" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                        </div>
                      </div>
                      <p className="text-xs text-[#c6c5d4] mt-0.5">Identifica ações, exercícios e entregas no documento</p>
                    </div>
                  </div>
                </button>

                {/* Schedule reviews card (only if flashcards enabled) */}
                {genFlashcards && (
                  <button
                    type="button"
                    onClick={() => setScheduleReviews(v => !v)}
                    className={`w-full text-left rounded-xl border-2 p-4 transition-all duration-200 ${
                      scheduleReviews
                        ? 'border-purple-500/40 bg-[#111111] shadow-[0_0_20px_rgba(168,85,247,0.04)]'
                        : 'border-transparent bg-[#111111] hover:bg-[#151515]'
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${scheduleReviews ? 'bg-purple-500/10' : 'bg-[#1e1e1e]'}`}>
                        <GraduationCap className={`h-5 w-5 ${scheduleReviews ? 'text-purple-400' : 'text-[#c6c5d4]'}`} />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-bold font-headline text-[#e1e3e4]">Agendar Revisões SRS</p>
                          <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${scheduleReviews ? 'border-purple-500 bg-purple-500' : 'border-[#454652]'}`}>
                            {scheduleReviews && <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                          </div>
                        </div>
                        <p className="text-xs text-[#c6c5d4] mt-0.5">Cria lembretes de revisão espaçada no calendário (+1d, +3d, +7d)</p>
                      </div>
                    </div>
                  </button>
                )}
              </div>
            </div>

            {/* Footer: AI status + CTA */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-[#1e1e1e]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#1e1e1e] flex items-center justify-center border border-[#282828]">
                  <Brain className="h-5 w-5 text-amber-400 opacity-70" />
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[#c6c5d4]">Status do Processamento</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shadow-[0_0_6px_rgba(251,191,36,0.6)]" />
                    <span className="text-sm font-medium text-[#e1e3e4]">Agente Pronto</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => digestMutation.mutate()}
                disabled={!selectedDoc}
                className="flex items-center gap-3 px-7 py-3 rounded-xl font-bold font-headline text-[#000000] bg-gradient-to-br from-amber-400 to-amber-500/80 shadow-[0_8px_24px_rgba(251,191,36,0.2)] hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100"
              >
                <span>Executar Smart Digest</span>
                <Zap className="h-4 w-4" />
              </button>
            </div>

            {/* Stats bento */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Entregas', value: [genFlashcards, extractTasks, scheduleReviews].filter(Boolean).length + 1 + ' itens' },
                { label: 'Flashcards', value: genFlashcards ? `${numCards} cards` : 'Desativado', accent: genFlashcards },
                { label: 'Modo', value: 'Paralelo' },
              ].map(stat => (
                <div key={stat.label} className="bg-[#0a0a0a] p-4 rounded-xl border border-[#1e1e1e]">
                  <span className="text-[10px] text-[#c6c5d4] uppercase font-bold tracking-widest block mb-1">{stat.label}</span>
                  <p className={`text-xl font-headline font-bold ${stat.accent ? 'text-amber-400' : 'text-[#e1e3e4]'}`}>{stat.value}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Create Artifact Dialog ────────────────────────────────────────────────────

function CreateArtifactDialog({
  onClose,
  templatesFeatureEnabled,
  templatesUnlocked,
  entitlementTier,
  onRefreshAccess,
}: {
  onClose: () => void
  templatesFeatureEnabled: boolean
  templatesUnlocked: boolean
  entitlementTier: string
  onRefreshAccess?: () => Promise<void> | void
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
    enabled: templatesFeatureEnabled,
    staleTime: 60_000,
    retry: 1,
  })
  const templateOptions = useMemo(() => templates ?? [], [templates])
  const templatesLocked = templatesFeatureEnabled && !templatesUnlocked
  const selectedTemplate = useMemo(
    () => templateOptions.find(item => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templateOptions]
  )
  const selectedTemplateIsLocked = Boolean(selectedTemplate?.locked)

  useEffect(() => {
    if (!templatesLocked) return
    trackPremiumTouchpointViewed({
      touchpoint: 'artifacts.create_templates',
      capability: 'premium_artifact_templates',
      metadata: { surface: 'artifacts', dialog: 'create' },
    })
  }, [templatesLocked])

  useEffect(() => {
    if (!templatesFeatureEnabled) return
    if (!templateOptions.length) { setSelectedTemplateId(''); return }
    const hasActive = templateOptions.some(item => item.template_id === selectedTemplateId && !item.locked)
    if (hasActive) return
    setSelectedTemplateId(pickDefaultTemplate(templateOptions, { artifactType: type }))
  }, [selectedTemplateId, templateOptions, templatesFeatureEnabled, type])

  const templateIdForRequest = (
    templatesFeatureEnabled
    && selectedTemplateId
    && !selectedTemplateIsLocked
  )
    ? selectedTemplateId
    : undefined

  const startJob = useMutation({
    mutationFn: () =>
      apiClient.createArtifactAsync(
        type, topic, undefined,
        selectedDocs.map(doc => doc.doc_id),
        templateIdForRequest,
      ),
    onSuccess: data => { setJobId(data.job_id) },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao iniciar artefato'),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: query =>
      query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed' ? false : 1200,
  })

  useEffect(() => {
    if (!jobId || !jobQuery.data) return
    if (jobQuery.data.status === 'succeeded') {
      const payload = jobQuery.data.result ?? {}
      setResult(String(payload.answer ?? ''))
      setResultTemplateLabel(payload.template_label ? String(payload.template_label) : null)
      if (templatesFeatureEnabled && templatesUnlocked) {
        trackPremiumFeatureActivation({
          touchpoint: 'artifacts.create_templates',
          capability: 'premium_artifact_templates',
          metadata: {
            surface: 'artifacts',
            artifact_type: type,
            template_id: payload.template_id ? String(payload.template_id) : null,
          },
        })
      }
      if (payload.filename) toast.success(`Artefato salvo: ${payload.filename}`)
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      qc.invalidateQueries({ queryKey: ['artifact-filter-options'] })
      setJobId(null)
    } else if (jobQuery.data.status === 'failed') {
      toast.error(jobQuery.data.error ?? 'Erro ao gerar artefato')
      setJobId(null)
    }
  }, [jobId, jobQuery.data, qc, templatesFeatureEnabled, templatesUnlocked, type])

  const isProcessing = startJob.isPending || !!jobId

  const typeSelectOptions = [
    { value: 'checklist', label: 'Checklist' },
    { value: 'artifact', label: 'Artefato Livre' },
  ]

  // Docs available to add (exclude already selected)
  const availableDocs = (docs ?? []).filter(doc => !selectedDocs.some(item => item.doc_id === doc.doc_id))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-[#282828] bg-[#111111] shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-[#282828] px-6 py-4 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#1e1e1e] flex items-center justify-center">
              <Plus className="h-4 w-4 text-primary" />
            </div>
            <h2 className="font-bold font-headline text-[#e1e3e4]">Novo Artefato</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-[#1e1e1e] text-[#c6c5d4] transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {!result ? (
            <>
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[#c6c5d4]">Tipo de Artefato</label>
                <FilterSelect options={typeSelectOptions} value={type} onChange={setType} />
              </div>
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[#c6c5d4]">Tópico</label>
                <input
                  type="text"
                  placeholder="Ex: Python para iniciantes"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  className="w-full h-10 px-3 rounded-lg bg-[#1e1e1e] border border-[#282828] text-sm text-[#e1e3e4] placeholder-[#454652] focus:outline-none focus:border-primary/40 transition-colors"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-xs font-semibold uppercase tracking-widest text-[#c6c5d4]">Documentos para usar (opcional)</label>
                <div className="flex gap-2">
                  <div className="flex-1">
                    <DocSelector
                      docs={availableDocs}
                      value={selectedDoc}
                      onChange={setSelectedDoc}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const found = (docs ?? []).find(doc => doc.file_name === selectedDoc)
                      if (!found || selectedDocs.some(item => item.doc_id === found.doc_id)) return
                      setSelectedDocs(prev => [...prev, found])
                      setSelectedDoc('')
                    }}
                    disabled={!selectedDoc}
                    className="px-4 py-2 rounded-lg border border-[#282828] bg-[#1e1e1e] text-sm text-[#e1e3e4] hover:border-primary/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Adicionar
                  </button>
                </div>
                {selectedDocs.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedDocs.map(doc => (
                      <span key={doc.doc_id} className="inline-flex items-center gap-2 rounded-full border border-[#282828] bg-[#1e1e1e] px-3 py-1 text-xs text-[#e1e3e4]">
                        {doc.file_name}
                        <button type="button" onClick={() => setSelectedDocs(prev => prev.filter(item => item.doc_id !== doc.doc_id))} className="text-[#c6c5d4] hover:text-rose-400 transition-colors">
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {templatesFeatureEnabled && templateOptions.length > 0 && (
                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[#c6c5d4]">Template</label>
                  <div className="grid gap-2 md:grid-cols-3">
                    {templateOptions.map(template => (
                      <button
                        key={template.template_id}
                        type="button"
                        onClick={() => {
                          if (template.locked) return
                          setSelectedTemplateId(template.template_id)
                        }}
                        disabled={Boolean(template.locked)}
                        className={`rounded-xl border px-3 py-2 text-left transition-all ${
                          template.locked
                            ? 'cursor-not-allowed border-amber-700/35 bg-amber-950/15 text-amber-200/80'
                            : selectedTemplateId === template.template_id
                            ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
                            : 'border-[#282828] bg-[#1e1e1e] text-[#c6c5d4] hover:border-[#454652]'
                        }`}
                      >
                        <p className="text-sm font-semibold">
                          {template.label}
                          {template.locked ? ' (Premium)' : ''}
                        </p>
                        <p className="mt-0.5 text-xs opacity-80">{template.short_description}</p>
                      </button>
                    ))}
                  </div>
                  {selectedTemplate && (
                    <div className="mt-2 rounded-xl border border-[#282828] bg-[#1e1e1e] p-3">
                      <p className="text-xs font-medium text-[#e1e3e4]">{selectedTemplate.preview_title}</p>
                      <p className="mt-1 text-xs text-[#c6c5d4]">{selectedTemplate.long_description}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {selectedTemplate.preview_sections.map(section => (
                          <span key={section} className="rounded-full border border-[#282828] bg-[#111111] px-2 py-0.5 text-[11px] text-[#c6c5d4]">
                            {section}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {templatesLocked && (
                    <div className="mt-3 rounded-xl border border-amber-600/35 bg-amber-950/15 px-3 py-2.5">
                      <p className="text-xs font-medium text-amber-200">
                        Templates premium bloqueados no plano atual ({entitlementTier}).
                      </p>
                      <p className="mt-1 text-[11px] text-amber-100/85">
                        Faca upgrade para liberar templates premium na criacao de artefatos.
                      </p>
                      <button
                        type="button"
                        onClick={() => { void onRefreshAccess?.() }}
                        className="mt-2 rounded-lg border border-amber-500/45 px-2.5 py-1 text-[11px] text-amber-100 transition-colors hover:bg-amber-500/10"
                      >
                        Ja fiz upgrade, atualizar acesso
                      </button>
                    </div>
                  )}
                </div>
              )}
              {isProcessing && (
                <div className="rounded-xl border border-[#282828] bg-[#1e1e1e] p-3">
                  <div className="mb-1 flex justify-between text-[11px] text-[#c6c5d4]">
                    <span>{jobQuery.data?.stage ?? 'iniciando'}</span>
                    <span>{jobQuery.data?.progress ?? 5}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-[#282828]">
                    <div className="h-1.5 rounded-full bg-primary transition-all" style={{ width: `${jobQuery.data?.progress ?? 5}%` }} />
                  </div>
                </div>
              )}
              <button
                onClick={() => startJob.mutate()}
                disabled={!topic.trim() || isProcessing || selectedTemplateIsLocked}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-[#000000] font-bold font-headline transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isProcessing ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />{jobQuery.data?.stage ?? 'Gerando...'}</>
                ) : (
                  <><Plus className="h-4 w-4" />Gerar Artefato</>
                )}
              </button>
            </>
          ) : (
            <>
              {resultTemplateLabel && (
                <div className="rounded-xl border border-amber-700/30 bg-amber-950/10 px-3 py-2 text-xs text-amber-300">
                  Template aplicado: {resultTemplateLabel}
                </div>
              )}
              <div className="prose prose-invert prose-sm max-w-none max-h-80 overflow-y-auto rounded-xl bg-[#1e1e1e] p-4">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
              <button onClick={onClose} className="w-full py-2 rounded-xl border border-[#282828] bg-[#1e1e1e] text-sm text-[#e1e3e4] hover:border-primary/30 transition-colors">
                Fechar
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Preview Dialog ────────────────────────────────────────────────────────────

function PreviewDialog({ artifact, onClose }: { artifact: { id: number; filename: string }; onClose: () => void }) {
  const { id: artifactId, filename } = artifact
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (!isMarkdownArtifact(filename)) {
      if (!cancelled) { setContent('Preview disponível apenas para arquivos de texto (.md, .markdown, .txt).'); setLoading(false) }
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-[#282828] bg-[#111111] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#282828] px-6 py-4">
          <h2 className="font-bold font-headline text-[#e1e3e4] truncate">{filename}</h2>
          <div className="flex gap-2">
            <button onClick={handleDownload} disabled={downloading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#282828] bg-[#1e1e1e] text-xs text-[#e1e3e4] hover:border-primary/40 transition-colors disabled:opacity-50">
              <Download className="h-3.5 w-3.5" />Download
            </button>
            {isMarkdownArtifact(filename) && (
              <button onClick={handleDownloadPdf} disabled={downloading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#282828] bg-[#1e1e1e] text-xs text-[#e1e3e4] hover:border-primary/40 transition-colors disabled:opacity-50">
                <FileText className="h-3.5 w-3.5" />PDF
              </button>
            )}
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-[#1e1e1e] text-[#c6c5d4] transition-colors">
              <X className="h-4 w-4" />
            </button>
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

// ── Artifact Icon helper ──────────────────────────────────────────────────────

function ArtifactIcon({ type, filename }: { type?: string | null; filename: string }) {
  if (type === 'summary') return <BookOpen className="h-5 w-5 text-primary" />
  if (type === 'checklist') return <CheckSquare className="h-5 w-5 text-emerald-400" />
  if (type === 'study_plan') return <GraduationCap className="h-5 w-5 text-amber-400" />
  if (isMarkdownArtifact(filename)) return <FileText className="h-5 w-5 text-primary" />
  return <Archive className="h-5 w-5 text-[#c6c5d4]" />
}

function artifactTypeBadge(type?: string | null) {
  if (!type) return null
  if (type === 'summary') return { label: 'Resumo', cls: 'text-primary' }
  if (type === 'checklist') return { label: 'Checklist', cls: 'text-emerald-400' }
  if (type === 'study_plan') return { label: 'Plano de Estudos', cls: 'text-amber-400' }
  return { label: type, cls: 'text-[#c6c5d4]' }
}

// ── Main Artifacts Page ───────────────────────────────────────────────────────

export function Artifacts() {
  const qc = useQueryClient()
  const capabilities = useCapabilities()
  const templatesFeatureEnabled = capabilities.isEnabled('premium_artifact_templates_enabled')
  const templatesUnlocked = capabilities.hasCapability('premium_artifact_templates')
  const templatesEnabled = templatesFeatureEnabled && templatesUnlocked
  const templatesLocked = templatesFeatureEnabled && !templatesUnlocked
  const [lastUpgradeTouchpoint, setLastUpgradeTouchpoint] = useState('artifacts.templates')
  const [wasTemplatesLocked, setWasTemplatesLocked] = useState(templatesLocked)
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
  const [showFilters, setShowFilters] = useState(false)

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

  useEffect(() => {
    if (!templatesLocked) return
    trackPremiumTouchpointViewed({
      touchpoint: 'artifacts.templates',
      capability: 'premium_artifact_templates',
      metadata: { surface: 'artifacts' },
    })
  }, [templatesLocked])

  useEffect(() => {
    if (wasTemplatesLocked && !templatesLocked) {
      trackUpgradeCompleted({
        touchpoint: lastUpgradeTouchpoint,
        capability: 'premium_artifact_templates',
        metadata: { surface: 'artifacts' },
      })
      trackPremiumFeatureActivation({
        touchpoint: 'artifacts.templates',
        capability: 'premium_artifact_templates',
        metadata: { surface: 'artifacts', source: 'unlock_transition' },
      })
    }
    setWasTemplatesLocked(templatesLocked)
  }, [lastUpgradeTouchpoint, templatesLocked, wasTemplatesLocked])

  useEffect(() => {
    if (!templatesEnabled) return
    trackPremiumFeatureActivation({
      touchpoint: 'artifacts.templates',
      capability: 'premium_artifact_templates',
      metadata: { surface: 'artifacts', source: 'templates_enabled' },
    })
  }, [templatesEnabled])

  function handleTemplateUpgradeIntent(source: 'link' | 'refresh_access', touchpoint = 'artifacts.templates') {
    setLastUpgradeTouchpoint(touchpoint)
    trackUpgradeInitiated({
      touchpoint,
      capability: 'premium_artifact_templates',
      metadata: { surface: 'artifacts', source },
    })
  }

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

  async function handleRefreshTemplateAccess(touchpoint = 'artifacts.templates') {
    handleTemplateUpgradeIntent('refresh_access', touchpoint)
    await capabilities.refresh()
    await qc.invalidateQueries({ queryKey: ['artifact-templates'] })
    toast.info('Acesso premium atualizado. Se o upgrade ja foi aplicado, recarregamos os templates.')
  }

  // Build filter select options from filterOptions
  const typeFilterOptions: SelectOption[] = [
    { value: 'all', label: 'Todos os tipos' },
    ...(filterOptions?.artifact_types ?? []).map(t => ({ value: t, label: t })),
  ]
  const templateFilterOptions: SelectOption[] = [
    { value: 'all', label: 'Todos os templates' },
    ...(filterOptions?.template_ids ?? []).map(t => ({ value: t, label: t })),
  ]
  const sourceDocFilterOptions: SelectOption[] = [
    { value: 'all', label: 'Todos os documentos' },
    ...(filterOptions?.source_doc_ids ?? []).map(t => ({ value: t, label: t })),
  ]
  const profileFilterOptions: SelectOption[] = [
    { value: 'all', label: 'Todos os perfis' },
    ...(filterOptions?.generation_profiles ?? []).map(t => ({ value: t, label: t })),
  ]
  const sortByOptions: SelectOption[] = ARTIFACT_SORT_OPTIONS.map(o => ({ value: o.value, label: o.label }))
  const sortOrderOptions: SelectOption[] = [
    { value: 'desc', label: 'Descendente' },
    { value: 'asc', label: 'Ascendente' },
  ]

  const hasActiveFilters = artifactTypeFilter !== 'all' || templateFilter !== 'all' || sourceDocFilter !== 'all' || generationProfileFilter !== 'all'

  return (
    <div className="relative min-h-screen">
      {/* Background decoration blobs */}
      <div className="fixed top-0 right-0 -z-10 w-[600px] h-[600px] bg-primary/5 blur-[120px] rounded-full translate-x-1/2 -translate-y-1/2 pointer-events-none" />
      <div className="fixed bottom-0 left-0 -z-10 w-[400px] h-[400px] bg-amber-400/5 blur-[100px] rounded-full -translate-x-1/2 translate-y-1/2 pointer-events-none" />

      <div className="px-4 py-6 space-y-8 sm:px-6 sm:py-8 sm:space-y-12">

        {/* ── Hero ── */}
        <header>
          <span className="app-kicker">Biblioteca de ativos inteligentes</span>
          <h1 className="text-3xl font-extrabold font-headline tracking-tighter mt-2 text-[#e1e3e4] sm:text-5xl">
            Artefatos
          </h1>
          <p className="mt-3 text-sm text-[#c6c5d4] max-w-2xl leading-relaxed sm:mt-4 sm:text-lg">
            {templatesEnabled
              ? 'Resumos, checklists e outros artefatos gerados com templates premium'
              : templatesLocked
                ? `Seu plano atual (${capabilities.entitlementTier}) bloqueia templates premium.`
              : 'Resumos, checklists e outros artefatos gerados pelo agente'}
          </p>
        </header>

        {templatesLocked && (
          <div className="rounded-xl border border-amber-600/35 bg-amber-950/15 px-4 py-3">
            <p className="text-sm font-medium text-amber-200">
              Templates premium bloqueados no plano atual ({capabilities.entitlementTier}).
            </p>
            <p className="mt-1 text-xs text-amber-100/85">
              Faca upgrade para desbloquear previews e geracao com templates premium.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => { void handleRefreshTemplateAccess('artifacts.templates') }}
                className="rounded-lg border border-amber-500/45 px-2.5 py-1 text-xs text-amber-100 transition-colors hover:bg-amber-500/10"
              >
                Ja fiz upgrade, atualizar acesso
              </button>
              <button
                type="button"
                onClick={() => {
                  handleTemplateUpgradeIntent('link', 'artifacts.templates')
                  window.location.href = '/settings'
                }}
                className="rounded-lg border border-amber-500/30 px-2.5 py-1 text-xs text-amber-100/90 transition-colors hover:bg-amber-500/10"
              >
                Ver recursos premium
              </button>
            </div>
          </div>
        )}

        {/* ── Action Hub ── */}
        <section>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-2 lg:grid-cols-4 sm:gap-4">

            {/* Resumir Documento */}
            <button
              onClick={() => setShowSummarize(true)}
              className="group relative flex flex-col items-start p-4 rounded-xl bg-[#111111] hover:bg-[#1e1e1e] transition-all duration-300 text-left overflow-hidden border border-[#1e1e1e] hover:border-[#282828] sm:p-6"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="w-10 h-10 rounded-lg bg-[#1e1e1e] mb-3 flex items-center justify-center group-hover:scale-110 transition-transform sm:w-12 sm:h-12 sm:mb-5">
                <BookOpen className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
              </div>
              <h3 className="text-sm font-bold font-headline text-[#e1e3e4] mb-1 sm:text-lg sm:mb-2">Resumir Documento</h3>
              <p className="text-xs text-[#c6c5d4] leading-snug sm:text-sm">Extraia a essência de arquivos extensos instantaneamente.</p>
            </button>

            {/* Smart Digest */}
            <button
              onClick={() => setShowDigest(true)}
              className="group relative flex flex-col items-start p-4 rounded-xl bg-[#111111] hover:bg-[#1e1e1e] transition-all duration-300 text-left overflow-hidden border border-[#1e1e1e] hover:border-[#282828] sm:p-6"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-amber-400/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="w-10 h-10 rounded-lg bg-[#1e1e1e] mb-3 flex items-center justify-center group-hover:scale-110 transition-transform sm:w-12 sm:h-12 sm:mb-5">
                <Zap className="h-5 w-5 text-amber-400 sm:h-6 sm:w-6" />
              </div>
              <h3 className="text-sm font-bold font-headline text-[#e1e3e4] mb-1 sm:text-lg sm:mb-2">Smart Digest</h3>
              <p className="text-xs text-[#c6c5d4] leading-snug sm:text-sm">Resumo + flashcards + tarefas em uma única operação.</p>
            </button>

            {/* Plano de Estudos */}
            <button
              onClick={() => window.location.href = '/studyplan'}
              className="group relative flex flex-col items-start p-4 rounded-xl bg-[#111111] hover:bg-[#1e1e1e] transition-all duration-300 text-left overflow-hidden border border-[#1e1e1e] hover:border-[#282828] sm:p-6"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-emerald-400/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="w-10 h-10 rounded-lg bg-[#1e1e1e] mb-3 flex items-center justify-center group-hover:scale-110 transition-transform sm:w-12 sm:h-12 sm:mb-5">
                <GraduationCap className="h-5 w-5 text-emerald-400 sm:h-6 sm:w-6" />
              </div>
              <h3 className="text-sm font-bold font-headline text-[#e1e3e4] mb-1 sm:text-lg sm:mb-2">Plano de Estudos</h3>
              <p className="text-xs text-[#c6c5d4] leading-snug sm:text-sm">Roteiros de aprendizado gerados via IA generativa.</p>
            </button>

            {/* Novo Artefato */}
            <button
              onClick={() => setShowCreate(true)}
              className="group relative flex flex-col items-center justify-center p-4 rounded-xl border-2 border-dashed border-[#282828] hover:border-primary/50 transition-all duration-300 text-center bg-transparent sm:p-6"
            >
              <div className="w-10 h-10 rounded-full bg-primary/10 mb-3 flex items-center justify-center group-hover:bg-primary/20 transition-colors sm:w-12 sm:h-12 sm:mb-4">
                <Plus className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
              </div>
              <h3 className="text-sm font-bold font-headline text-primary sm:text-lg">Novo Artefato</h3>
              <p className="text-xs text-[#c6c5d4] mt-1 sm:mt-2">Clique para iniciar criação livre</p>
            </button>

          </div>
        </section>

        {/* ── Library Section ── */}
        <section>
          {/* Section header */}
          <div className="mb-4 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold font-headline text-[#e1e3e4] sm:text-2xl">Arquivos Recentes</h2>
              {!isLoading && artifacts && (
                <span className="px-2.5 py-0.5 rounded-full bg-[#1e1e1e] text-xs text-[#c6c5d4] font-semibold">
                  {artifacts.length} {artifacts.length === 1 ? 'item' : 'itens'}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* Search */}
              <div className="relative flex-1 sm:flex-none">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#c6c5d4]" />
                <input
                  type="text"
                  placeholder="Buscar artefatos..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-[#111111] border border-[#1e1e1e] rounded-lg text-sm text-[#e1e3e4] placeholder-[#454652] focus:outline-none focus:border-primary/40 transition-all sm:w-56"
                />
              </div>
              {/* Filter toggle */}
              <button
                onClick={() => setShowFilters(f => !f)}
                className={`shrink-0 p-2 rounded-lg transition-colors ${showFilters || hasActiveFilters ? 'bg-primary/15 text-primary border border-primary/30' : 'bg-[#111111] border border-[#1e1e1e] text-[#c6c5d4] hover:bg-[#1e1e1e]'}`}
                title="Filtros avançados"
              >
                <SlidersHorizontal className="h-4 w-4" />
              </button>
              {/* Clear filters */}
              {hasActiveFilters && (
                <button
                  onClick={() => {
                    setArtifactTypeFilter('all'); setTemplateFilter('all')
                    setSourceDocFilter('all'); setGenerationProfileFilter('all')
                    setSortBy('created_at'); setSortOrder('desc')
                  }}
                  className="shrink-0 text-xs text-[#c6c5d4] hover:text-[#e1e3e4] transition-colors"
                >
                  Limpar
                </button>
              )}
            </div>
          </div>

          {/* Expandable filter panel */}
          {showFilters && (
            <div className="mb-6 p-4 rounded-xl bg-[#111111] border border-[#1e1e1e] space-y-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterSelect options={typeFilterOptions} value={artifactTypeFilter} onChange={setArtifactTypeFilter} />
                <FilterSelect options={templateFilterOptions} value={templateFilter} onChange={setTemplateFilter} />
                <FilterSelect options={sourceDocFilterOptions} value={sourceDocFilter} onChange={setSourceDocFilter} />
                <FilterSelect options={profileFilterOptions} value={generationProfileFilter} onChange={setGenerationProfileFilter} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterSelect options={sortByOptions} value={sortBy} onChange={v => setSortBy(v as typeof sortBy)} />
                <FilterSelect options={sortOrderOptions} value={sortOrder} onChange={v => setSortOrder(v as 'asc' | 'desc')} />
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-xl border border-rose-800/40 bg-rose-950/20 px-4 py-3 text-sm text-rose-400">
              Erro ao carregar artefatos.
            </div>
          )}

          {/* Loading */}
          {isLoading && (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && (!artifacts || artifacts.length === 0) && !error && (
            <div className="flex flex-col items-center gap-4 py-16 rounded-xl border-2 border-dashed border-[#1e1e1e]">
              <div className="w-16 h-16 rounded-2xl bg-[#111111] flex items-center justify-center">
                <Archive className="h-8 w-8 text-[#454652]" />
              </div>
              <div className="text-center">
                <p className="font-bold font-headline text-[#e1e3e4]">Nenhum artefato gerado</p>
                <p className="text-sm text-[#c6c5d4] mt-1">Gere resumos, checklists e mais usando as ações acima</p>
              </div>
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-[#000000] font-bold text-sm font-headline hover:opacity-90 transition-opacity"
              >
                <Plus className="h-4 w-4" />
                Criar Artefato
              </button>
            </div>
          )}

          {/* Artifact list */}
          {artifacts && artifacts.length > 0 && (
            <div className="space-y-2">
              {artifacts.map((artifact, idx) => {
                const isMarkdown = isMarkdownArtifact(artifact.filename)
                const badge = artifactTypeBadge(artifact.artifact_type)

                return (
                  <div
                    key={`${artifact.filename}-${artifact.created_at}`}
                    className={`group flex items-center gap-3 p-3 rounded-xl transition-all duration-200 sm:gap-5 sm:p-4 ${
                      idx % 2 === 0
                        ? 'bg-[#111111] hover:bg-[#1e1e1e]'
                        : 'bg-[#0d0d0d] border border-[#1e1e1e]/50 hover:bg-[#111111]'
                    }`}
                  >
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-xl bg-[#1e1e1e] flex items-center justify-center shrink-0 sm:w-12 sm:h-12">
                      <ArtifactIcon type={artifact.artifact_type} filename={artifact.filename} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-bold font-headline text-[#e1e3e4] truncate group-hover:text-primary transition-colors sm:text-base">
                        {artifact.title?.trim() ? artifact.title : artifact.filename}
                      </h4>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap sm:gap-2 sm:mt-1">
                        {badge && <span className={`text-xs font-semibold ${badge.cls}`}>{badge.label}</span>}
                        {badge && <span className="w-1 h-1 rounded-full bg-[#282828]" />}
                        <span className="text-xs text-[#c6c5d4]">{formatDate(artifact.created_at)}</span>
                        <span className="hidden w-1 h-1 rounded-full bg-[#282828] sm:block" />
                        <span className="hidden text-xs text-[#c6c5d4] sm:block">{formatBytes(artifact.size)}</span>
                      </div>
                    </div>

                    {/* Actions — always visible on mobile, hover-only on sm+ */}
                    <div className="flex items-center gap-1 shrink-0 sm:opacity-0 sm:group-hover:opacity-100 sm:transition-opacity">
                      {isMarkdown && (
                        <button
                          onClick={() => setPreviewFile({ id: artifact.id, filename: artifact.filename })}
                          className="p-2 hover:bg-[#282828] rounded-lg text-[#c6c5d4] transition-colors"
                          title="Preview"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDownload(artifact.id, artifact.filename)}
                        disabled={downloadingKey !== null}
                        className="p-2 hover:bg-[#282828] rounded-lg text-[#c6c5d4] transition-colors disabled:opacity-50"
                        title="Download"
                      >
                        {downloadingKey === `${artifact.id}:file` ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Download className="h-4 w-4" />
                        )}
                      </button>
                      {isMarkdown && (
                        <button
                          onClick={() => handleDownloadPdf(artifact.id, artifact.filename)}
                          disabled={downloadingKey !== null}
                          className="hidden p-2 hover:bg-[#282828] rounded-lg text-[#c6c5d4] transition-colors disabled:opacity-50 sm:block"
                          title="Exportar PDF"
                        >
                          {downloadingKey === `${artifact.id}:pdf` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <FileText className="h-4 w-4" />
                          )}
                        </button>
                      )}
                      <button
                        onClick={() => { if (confirm(`Remover "${artifact.filename}"?`)) deleteMut.mutate(artifact.id) }}
                        disabled={deleteMut.isPending}
                        className="p-2 hover:bg-rose-950/30 text-[#454652] hover:text-rose-400 rounded-lg transition-colors"
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>

      {/* ── FAB ── */}
      <div className="fixed bottom-8 right-8 z-50">
        <button
          onClick={() => window.location.href = '/chat'}
          className="flex items-center gap-3 bg-primary text-[#000000] px-6 py-4 rounded-full font-bold font-headline shadow-[0_10px_30px_rgba(147,197,253,0.25)] hover:scale-105 active:scale-95 transition-all"
        >
          <Zap className="h-5 w-5" />
          <span>Perguntar ao Agente</span>
        </button>
      </div>

      {/* Dialogs */}
      {showSummarize && (
        <SummarizeDocDialog
          onClose={() => setShowSummarize(false)}
          templatesFeatureEnabled={templatesFeatureEnabled}
          templatesUnlocked={templatesUnlocked}
          entitlementTier={capabilities.entitlementTier}
          onRefreshAccess={() => handleRefreshTemplateAccess('artifacts.summarize_templates')}
        />
      )}
      {showDigest && <SmartDigestDialog onClose={() => setShowDigest(false)} />}
      {showCreate && (
        <CreateArtifactDialog
          onClose={() => setShowCreate(false)}
          templatesFeatureEnabled={templatesFeatureEnabled}
          templatesUnlocked={templatesUnlocked}
          entitlementTier={capabilities.entitlementTier}
          onRefreshAccess={() => handleRefreshTemplateAccess('artifacts.create_templates')}
        />
      )}
      {previewFile && <PreviewDialog artifact={previewFile} onClose={() => setPreviewFile(null)} />}
    </div>
  )
}
