import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCircle, ClipboardPaste, FileText, FolderOpen, Layers, Loader2, Upload, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader, PageShell } from '@/components/ui/page-shell'
import { apiClient, type IngestResponse } from '@/api/client'
import { cn } from '@/lib/utils'
import * as XLSX from 'xlsx'
import { SectionIntro } from '@/onboarding/SectionIntro'

type TabularPreview = {
  fileName: string
  headers: string[]
  rows: string[][]
}

async function buildPreview(file: File): Promise<TabularPreview | null> {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!['csv', 'xlsx', 'xls', 'ods'].includes(ext)) return null

  if (ext === 'csv') {
    const text = await file.text()
    const lines = text.split(/\r?\n/).filter(Boolean).slice(0, 21)
    const rows = lines.map(line => line.split(',').map(cell => cell.trim()))
    return { fileName: file.name, headers: rows[0] ?? [], rows: rows.slice(1, 11) }
  }

  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const firstSheetName = workbook.SheetNames[0]
  const sheet = workbook.Sheets[firstSheetName]
  const matrix: unknown[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, blankrows: false })
  const normalized = matrix
    .map(row => row.map(cell => (cell == null ? '' : String(cell))))
    .filter(row => row.some(cell => String(cell).trim() !== ''))
  return {
    fileName: `${file.name} (${firstSheetName})`,
    headers: normalized[0] ?? [],
    rows: normalized.slice(1, 11),
  }
}

const INGEST_STAGES = [
  { label: 'Carregando arquivos...', pct: 15 },
  { label: 'Processando conteudo...', pct: 40 },
  { label: 'Gerando vetores...', pct: 65 },
  { label: 'Indexando no Chroma...', pct: 85 },
  { label: 'Salvando metadados...', pct: 95 },
]

function useIngestProgress(isLoading: boolean) {
  const [stageIdx, setStageIdx] = useState(0)
  const [pct, setPct] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!isLoading) {
      if (timerRef.current) clearInterval(timerRef.current)
      setStageIdx(0)
      setPct(0)
      return
    }

    setStageIdx(0)
    setPct(5)
    let idx = 0
    timerRef.current = setInterval(() => {
      idx = Math.min(idx + 1, INGEST_STAGES.length - 1)
      setStageIdx(idx)
      setPct(INGEST_STAGES[idx].pct)
      if (idx >= INGEST_STAGES.length - 1 && timerRef.current) {
        clearInterval(timerRef.current)
      }
    }, 900)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isLoading])

  return { stageLabel: INGEST_STAGES[stageIdx]?.label ?? '', pct }
}

export function Ingest() {
  const queryClient = useQueryClient()

  const [tab, setTab] = useState<'upload' | 'path' | 'clip' | 'photo'>('upload')
  const [dragOver, setDragOver] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [preview, setPreview] = useState<TabularPreview | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [serverPath, setServerPath] = useState('')
  const [clipText, setClipText] = useState('')
  const [clipTitle, setClipTitle] = useState('')
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoTitle, setPhotoTitle] = useState('')
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)

  const [result, setResult] = useState<IngestResponse | null>(null)

  const uploadMutation = useMutation({
    mutationFn: () => apiClient.ingestUpload(selectedFiles),
    onSuccess: data => {
      setResult(data)
      setSelectedFiles([])
      queryClient.invalidateQueries({ queryKey: ['docs'] })
      toast.success('Documentos indexados com sucesso!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao inserir arquivos'),
  })

  const pathMutation = useMutation({
    mutationFn: () => apiClient.ingestPath(serverPath),
    onSuccess: data => {
      setResult(data)
      setServerPath('')
      queryClient.invalidateQueries({ queryKey: ['docs'] })
      toast.success('Documentos indexados com sucesso!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao inserir caminho'),
  })

  const clipMutation = useMutation({
    mutationFn: () => apiClient.ingestClip(clipText, clipTitle || 'clip'),
    onSuccess: data => {
      setResult(data)
      setClipText('')
      setClipTitle('')
      queryClient.invalidateQueries({ queryKey: ['docs'] })
      toast.success('Documento indexado com sucesso!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao inserir texto'),
  })

  const photoMutation = useMutation({
    mutationFn: () => apiClient.ingestPhoto(photoFile!, photoTitle || 'foto'),
    onSuccess: data => {
      setResult(data)
      setPhotoFile(null)
      setPhotoTitle('')
      setPhotoPreview(null)
      queryClient.invalidateQueries({ queryKey: ['docs'] })
      toast.success('Documento indexado com sucesso!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao processar foto'),
  })

  const isLoading = uploadMutation.isPending || pathMutation.isPending || clipMutation.isPending || photoMutation.isPending
  const { stageLabel, pct } = useIngestProgress(isLoading)
  const totalSizeKb = selectedFiles.reduce((acc, file) => acc + file.size, 0) / 1024

  function handleDrop(event: React.DragEvent) {
    event.preventDefault()
    setDragOver(false)
    const files = Array.from(event.dataTransfer.files).filter(file =>
      /\.(pdf|txt|md|markdown|csv|xlsx|xls|ods)$/i.test(file.name),
    )
    setSelectedFiles(prev => [...prev, ...files])
  }

  function handleFileInput(event: React.ChangeEvent<HTMLInputElement>) {
    const { files } = event.currentTarget
    if (!files) return
    setSelectedFiles(prev => [...prev, ...Array.from(files)])
  }

  useEffect(() => {
    if (selectedFiles.length === 0) {
      setPreviewIndex(null)
      setPreview(null)
      return
    }
    if (previewIndex === null || previewIndex >= selectedFiles.length) {
      const firstTabular = selectedFiles.findIndex(file => /\.(csv|xlsx|xls|ods)$/i.test(file.name))
      setPreviewIndex(firstTabular >= 0 ? firstTabular : null)
    }
  }, [selectedFiles, previewIndex])

  useEffect(() => {
    const selected = previewIndex !== null ? selectedFiles[previewIndex] : null
    if (!selected) {
      setPreview(null)
      return
    }
    let cancelled = false
    buildPreview(selected)
      .then(data => { if (!cancelled) setPreview(data) })
      .catch(() => { if (!cancelled) setPreview(null) })
    return () => { cancelled = true }
  }, [previewIndex, selectedFiles])

  return (
    <PageShell className="space-y-8">
      <SectionIntro sectionId="ingest" />
      <PageHeader
        title="Inserção de Documentos"
        subtitle="Alimente o cérebro do DocOps Agent com novos conhecimentos. Os documentos são processados e indexados para consulta imediata."
      />

      <div className="flex w-fit gap-1 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] p-1">
        {([
          { key: 'upload', label: 'Upload' },
          { key: 'path', label: 'Caminho' },
          { key: 'clip', label: 'Clip de Texto' },
          { key: 'photo', label: 'Foto / OCR' },
        ] as const).map(item => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              tab === item.key
                ? 'bg-[color:var(--ui-surface-3)] text-[color:var(--ui-accent)]'
                : 'text-[color:var(--ui-text-meta)] hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'upload' && (
        <section className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-8">
            <div className="app-surface p-1">
              <div
                onDragOver={event => { event.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  'cursor-pointer rounded-lg border-2 border-dashed px-6 py-16 text-center transition-colors',
                  dragOver
                    ? 'border-[color:var(--ui-accent)]/80 bg-[color:var(--ui-accent-soft)]'
                    : 'border-[color:var(--ui-border-strong)]/60 bg-[color:var(--ui-bg-alt)] hover:border-[color:var(--ui-accent)]/50',
                )}
              >
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[color:var(--ui-surface-3)]"><Upload className="h-8 w-8 text-[color:var(--ui-accent)]" /></div>
                <p className="text-lg font-semibold text-[color:var(--ui-text)]">Arraste arquivos aqui ou clique para selecionar</p>
                <p className="mt-2 text-xs text-[color:var(--ui-text-meta)]">PDF, TXT, MD, CSV, XLSX, XLS, ODS</p>
                <input ref={fileInputRef} type="file" multiple accept=".pdf,.txt,.md,.markdown,.csv,.xlsx,.xls,.ods" className="hidden" onChange={handleFileInput} />
              </div>
            </div>

            {selectedFiles.length > 0 && (
              <div className="mt-4 space-y-2">
                {selectedFiles.map((file, index) => (
                  <div key={`${file.name}-${index}`} className="flex items-center justify-between rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-3 py-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <FileText className="h-4 w-4 shrink-0 text-[color:var(--ui-accent)]" />
                      <span className="truncate text-sm text-[color:var(--ui-text)]">{file.name}</span>
                      <span className="text-xs text-[color:var(--ui-text-meta)]">({(file.size / 1024).toFixed(1)} KB)</span>
                      {/\.(csv|xlsx|xls|ods)$/i.test(file.name) && (
                        <button onClick={event => { event.stopPropagation(); setPreviewIndex(index) }} className={cn('rounded border px-2 py-0.5 text-[10px]', previewIndex === index ? 'border-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]' : 'border-[color:var(--ui-border)] text-[color:var(--ui-text-meta)]')}>
                          Preview
                        </button>
                      )}
                    </div>
                    <button onClick={event => { event.stopPropagation(); setSelectedFiles(prev => prev.filter((_, idx) => idx !== index)) }} className="text-[color:var(--ui-text-meta)] hover:text-rose-300">
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {preview && (
              <div className="mt-4 overflow-hidden rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-bg-alt)]">
                <p className="border-b border-[color:var(--ui-border-soft)] px-3 py-2 text-sm font-medium text-[color:var(--ui-text)]">Pre-visualizacao tabular: {preview.fileName}</p>
                <div className="overflow-auto">
                  <table className="min-w-full border-collapse text-xs">
                    <thead>
                      <tr>
                        {preview.headers.map((header, idx) => <th key={`${header}-${idx}`} className="border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-2 py-1 text-left text-[color:var(--ui-text-dim)]">{header || `col_${idx + 1}`}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, rowIdx) => (
                        <tr key={rowIdx}>
                          {preview.headers.map((_, colIdx) => <td key={`${rowIdx}-${colIdx}`} className="border border-[color:var(--ui-border-soft)] px-2 py-1 text-[color:var(--ui-text-dim)]">{row[colIdx] ?? ''}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          <div className="col-span-12 space-y-5 lg:col-span-4">
            <div className="app-surface p-5">
              <h3 className="mb-4 text-xs font-bold uppercase tracking-[0.14em] text-[color:var(--ui-accent)]/80">Informacao de indexacao</h3>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between"><span className="text-[color:var(--ui-text-meta)]">Arquivos selecionados</span><span className="font-mono text-[color:var(--ui-text)]">{selectedFiles.length}</span></div>
                <div className="flex items-center justify-between"><span className="text-[color:var(--ui-text-meta)]">Tamanho total</span><span className="font-mono text-[color:var(--ui-text)]">{totalSizeKb.toFixed(1)} KB</span></div>
              </div>
            </div>

            {isLoading && (
              <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface-1)] p-4 space-y-3">
                <div className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin text-[color:var(--ui-accent)]" /><span className="text-sm text-[color:var(--ui-text-dim)]">{stageLabel}</span><span className="ml-auto text-xs font-mono text-[color:var(--ui-text-meta)]">{pct}%</span></div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--ui-bg-alt)]"><div className="h-full rounded-full bg-[color:var(--ui-accent)] transition-all duration-700" style={{ width: `${pct}%` }} /></div>
              </div>
            )}

            <Button onClick={() => uploadMutation.mutate()} disabled={selectedFiles.length === 0 || isLoading} className="h-12 w-full rounded-xl border-0 bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] disabled:opacity-40">
              {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Layers className="mr-2 h-4 w-4" />}
              {isLoading ? 'Indexando...' : 'Indexar Arquivos'}
            </Button>
          </div>
        </section>
      )}

      {tab === 'path' && (
        <section className="app-surface p-6 space-y-4">
          <Input placeholder="Ex: /home/user/docs ou ./docs" value={serverPath} onChange={event => setServerPath(event.target.value)} className="h-11 border-[color:var(--ui-border)] bg-[color:var(--ui-bg-alt)] text-[color:var(--ui-text)]" />
          <Button onClick={() => pathMutation.mutate()} disabled={!serverPath.trim() || isLoading} className="h-11 w-full rounded-lg border-0 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
            {isLoading ? 'Indexando...' : 'Indexar Caminho'}
          </Button>
        </section>
      )}

      {tab === 'clip' && (
        <section className="app-surface p-6 space-y-4">
          <Input placeholder="Titulo (opcional)" value={clipTitle} onChange={event => setClipTitle(event.target.value)} className="h-11 border-[color:var(--ui-border)] bg-[color:var(--ui-bg-alt)] text-[color:var(--ui-text)]" />
          <textarea value={clipText} onChange={event => setClipText(event.target.value)} placeholder="Cole texto para indexar..." rows={8} className="w-full rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-bg-alt)] px-3 py-2 text-sm text-[color:var(--ui-text)] outline-none" />
          <p className="text-xs text-[color:var(--ui-text-meta)]">{clipText.length} caracteres</p>
          <Button onClick={() => clipMutation.mutate()} disabled={clipText.trim().length < 10 || isLoading} className="h-11 w-full rounded-lg border-0 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
            {clipMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ClipboardPaste className="mr-2 h-4 w-4" />}
            {clipMutation.isPending ? 'Indexando...' : 'Indexar Texto'}
          </Button>
        </section>
      )}

      {tab === 'photo' && (
        <section className="app-surface p-6 space-y-4">
          <Input placeholder="Titulo (opcional)" value={photoTitle} onChange={event => setPhotoTitle(event.target.value)} className="h-11 border-[color:var(--ui-border)] bg-[color:var(--ui-bg-alt)] text-[color:var(--ui-text)]" />
          <div onClick={() => document.getElementById('photo-input')?.click()} className={cn('cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors', photoFile ? 'border-[color:var(--ui-accent)]/60 bg-[color:var(--ui-accent-soft)]' : 'border-[color:var(--ui-border)] hover:border-[color:var(--ui-accent)]/45')}>
            {photoPreview ? <img src={photoPreview} alt="Preview" className="mx-auto max-h-52 rounded-lg object-contain" /> : <Camera className="mx-auto h-9 w-9 text-[color:var(--ui-text-meta)]" />}
            <input
              id="photo-input"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.heic"
              className="hidden"
              onChange={event => {
                const file = event.target.files?.[0] ?? null
                setPhotoFile(file)
                if (!file) { setPhotoPreview(null); return }
                const reader = new FileReader()
                reader.onload = ev => setPhotoPreview(ev.target?.result as string)
                reader.readAsDataURL(file)
              }}
            />
          </div>
          <Button onClick={() => photoMutation.mutate()} disabled={!photoFile || isLoading} className="h-11 w-full rounded-lg border-0 bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]">
            {photoMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Camera className="mr-2 h-4 w-4" />}
            {photoMutation.isPending ? 'Extraindo texto...' : 'Extrair e Indexar'}
          </Button>
        </section>
      )}

      {result && (
        <section className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />
            <div>
              <p className="font-medium text-emerald-200">Insercao concluida</p>
              <p className="mt-1 text-sm text-emerald-300">{result.files_loaded} documento(s) processado(s).</p>
              {result.file_names.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {result.file_names.map(name => (
                    <li key={name} className="flex items-center gap-2 text-xs text-emerald-300">
                      <FileText className="h-3 w-3" />
                      {name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>
      )}
    </PageShell>
  )
}
