import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FolderOpen, CheckCircle, X, FileText, Loader2, Layers, ChevronDown, ClipboardPaste, Camera } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiClient, type IngestResponse } from '@/api/client'
import { cn } from '@/lib/utils'
import * as XLSX from 'xlsx'

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
    const headers = rows[0] ?? []
    return { fileName: file.name, headers, rows: rows.slice(1, 11) }
  }

  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const firstSheetName = workbook.SheetNames[0]
  const sheet = workbook.Sheets[firstSheetName]
  const matrix: any[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, blankrows: false })
  const normalized = matrix
    .map(row => row.map(cell => (cell == null ? '' : String(cell))))
    .filter(row => row.some(cell => String(cell).trim() !== ''))
  const headers = normalized[0] ?? []
  return {
    fileName: `${file.name} (${firstSheetName})`,
    headers,
    rows: normalized.slice(1, 11),
  }
}

// Fake progress stages for visual feedback during ingestion
const INGEST_STAGES = [
  { label: 'Carregando arquivos...', pct: 15 },
  { label: 'Dividindo em chunks...', pct: 40 },
  { label: 'Vetorizando chunks...', pct: 65 },
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
      if (idx >= INGEST_STAGES.length - 1) {
        if (timerRef.current) clearInterval(timerRef.current)
      }
    }, 900)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isLoading])

  return { stageLabel: INGEST_STAGES[stageIdx]?.label ?? '', pct }
}

export function Ingest() {
  const qc = useQueryClient()

  // Upload tab state
  const [dragOver, setDragOver] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [preview, setPreview] = useState<TabularPreview | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Path tab state
  const [serverPath, setServerPath] = useState('')

  // Advanced
  const [chunkSize, setChunkSize] = useState('')
  const [chunkOverlap, setChunkOverlap] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Clip tab state
  const [clipText, setClipText] = useState('')
  const [clipTitle, setClipTitle] = useState('')

  // Photo tab state
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoTitle, setPhotoTitle] = useState('')
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)

  // Active tab
  const [tab, setTab] = useState<'upload' | 'path' | 'clip' | 'photo'>('upload')

  const [result, setResult] = useState<IngestResponse | null>(null)

  const uploadMutation = useMutation({
    mutationFn: () =>
      apiClient.ingestUpload(
        selectedFiles,
        chunkSize ? parseInt(chunkSize) : 0,
        chunkOverlap ? parseInt(chunkOverlap) : 0
      ),
    onSuccess: data => {
      setResult(data)
      setSelectedFiles([])
      qc.invalidateQueries({ queryKey: ['docs'] })
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao inserir arquivos')
    },
  })

  const pathMutation = useMutation({
    mutationFn: () =>
      apiClient.ingestPath(
        serverPath,
        chunkSize ? parseInt(chunkSize) : 0,
        chunkOverlap ? parseInt(chunkOverlap) : 0
      ),
    onSuccess: data => {
      setResult(data)
      setServerPath('')
      qc.invalidateQueries({ queryKey: ['docs'] })
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao inserir caminho')
    },
  })

  const clipMutation = useMutation({
    mutationFn: () => apiClient.ingestClip(clipText, clipTitle || 'clip'),
    onSuccess: data => {
      setResult(data)
      setClipText('')
      setClipTitle('')
      qc.invalidateQueries({ queryKey: ['docs'] })
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao inserir texto')
    },
  })

  const photoMutation = useMutation({
    mutationFn: () => apiClient.ingestPhoto(photoFile!, photoTitle || 'foto'),
    onSuccess: data => {
      setResult(data)
      setPhotoFile(null)
      setPhotoTitle('')
      setPhotoPreview(null)
      qc.invalidateQueries({ queryKey: ['docs'] })
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao processar foto')
    },
  })

  const isLoading = uploadMutation.isPending || pathMutation.isPending || clipMutation.isPending || photoMutation.isPending
  const { stageLabel, pct } = useIngestProgress(isLoading)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files).filter(f =>
      /\.(pdf|txt|md|markdown|csv|xlsx|xls|ods)$/i.test(f.name)
    )
    setSelectedFiles(prev => [...prev, ...files])
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  useEffect(() => {
    if (selectedFiles.length === 0) {
      setPreviewIndex(null)
      setPreview(null)
      return
    }
    if (previewIndex === null || previewIndex >= selectedFiles.length) {
      const firstTabularIdx = selectedFiles.findIndex(f => /\.(csv|xlsx|xls|ods)$/i.test(f.name))
      setPreviewIndex(firstTabularIdx >= 0 ? firstTabularIdx : null)
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
      .then(data => {
        if (cancelled) return
        setPreview(data)
      })
      .catch(() => {
        if (cancelled) return
        setPreview(null)
      })
    return () => {
      cancelled = true
    }
  }, [previewIndex, selectedFiles])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Inserção de Documentos</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Indexe PDFs, Markdown, texto e planilhas (CSV/XLSX/XLS/ODS) no Chroma
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex rounded-lg border border-zinc-800 bg-zinc-900 p-1 w-fit">
        {([
          { key: 'upload', label: 'Upload' },
          { key: 'path', label: 'Caminho' },
          { key: 'clip', label: 'Clip de Texto' },
          { key: 'photo', label: 'Foto / OCR' },
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
              tab === t.key
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Upload tab */}
      {tab === 'upload' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-blue-400" />
              Upload de Arquivos
            </CardTitle>
            <CardDescription>
              Arraste arquivos ou clique para selecionar. Suporta PDF, TXT, MD, CSV, XLSX, XLS e ODS
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors',
                dragOver
                  ? 'border-blue-500 bg-blue-500/10'
                  : 'border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50'
              )}
            >
              <Upload className="mx-auto mb-3 h-10 w-10 text-zinc-500" />
              <p className="text-sm font-medium text-zinc-300">
                Arraste arquivos aqui ou clique para selecionar
              </p>
              <p className="mt-1 text-xs text-zinc-500">PDF, TXT, MD, MARKDOWN, CSV, XLSX</p>
              <p className="mt-1 text-xs text-zinc-500">XLS, ODS</p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.md,.markdown,.csv,.xlsx,.xls,.ods"
                className="hidden"
                onChange={handleFileInput}
              />
            </div>

            {/* Selected files */}
            {selectedFiles.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-zinc-300">
                  {selectedFiles.length} arquivo(s) selecionado(s):
                </p>
                {selectedFiles.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg bg-zinc-800 px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-blue-400" />
                      <span className="text-sm text-zinc-200">{f.name}</span>
                      <span className="text-xs text-zinc-500">
                        ({(f.size / 1024).toFixed(1)} KB)
                      </span>
                      {/\.(csv|xlsx|xls|ods)$/i.test(f.name) && (
                        <button
                          onClick={e => {
                            e.stopPropagation()
                            setPreviewIndex(i)
                          }}
                          className={cn(
                            'rounded border px-2 py-0.5 text-[10px] transition-colors',
                            previewIndex === i
                              ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                              : 'border-zinc-600 text-zinc-400 hover:border-zinc-500'
                          )}
                        >
                          Preview
                        </button>
                      )}
                    </div>
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        setSelectedFiles(prev => prev.filter((_, j) => j !== i))
                      }}
                      className="text-zinc-500 hover:text-red-400"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {preview && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-950 p-3">
                <p className="mb-2 text-sm font-medium text-zinc-200">
                  Pré-visualização tabular: {preview.fileName}
                </p>
                <div className="overflow-auto">
                  <table className="min-w-full border-collapse text-xs">
                    <thead>
                      <tr>
                        {preview.headers.map((header, idx) => (
                          <th key={`${header}-${idx}`} className="border border-zinc-700 bg-zinc-900 px-2 py-1 text-left text-zinc-300">
                            {header || `col_${idx + 1}`}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, rowIdx) => (
                        <tr key={rowIdx}>
                          {preview.headers.map((_, colIdx) => (
                            <td key={`${rowIdx}-${colIdx}`} className="border border-zinc-800 px-2 py-1 text-zinc-400">
                              {row[colIdx] ?? ''}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {isLoading && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/60 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                  <span className="text-sm text-zinc-300">{stageLabel}</span>
                  <span className="ml-auto text-xs font-mono text-zinc-500">{pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-blue-600 transition-all duration-700"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="text-xs text-zinc-600">
                  Isso pode levar alguns segundos dependendo do tamanho dos arquivos.
                </p>
              </div>
            )}
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={selectedFiles.length === 0 || isLoading}
              className={cn('w-full', (selectedFiles.length === 0 || isLoading) && 'opacity-50 cursor-not-allowed')}
            >
              {isLoading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Indexando...</>
              ) : (
                <><Layers className="mr-2 h-4 w-4" />Indexar Arquivos</>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Path tab */}
      {tab === 'path' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="h-5 w-5 text-blue-400" />
              Caminho do Servidor
            </CardTitle>
            <CardDescription>
              Informe o caminho absoluto ou relativo de uma pasta ou arquivo no servidor.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                Caminho
              </label>
              <Input
                placeholder="Ex: /home/user/docs ou ./docs"
                value={serverPath}
                onChange={e => setServerPath(e.target.value)}
              />
            </div>
            {isLoading && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/60 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                  <span className="text-sm text-zinc-300">{stageLabel}</span>
                  <span className="ml-auto text-xs font-mono text-zinc-500">{pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-blue-600 transition-all duration-700"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            )}
            <Button
              onClick={() => pathMutation.mutate()}
              disabled={!serverPath.trim() || isLoading}
              className="w-full"
            >
              {isLoading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Indexando...</>
              ) : (
                <><Layers className="mr-2 h-4 w-4" />Indexar Caminho</>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Clip tab */}
      {tab === 'clip' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ClipboardPaste className="h-5 w-5 text-blue-400" />
              Clip de Texto
            </CardTitle>
            <CardDescription>
              Cole texto da área de transferência, URLs ou anotações rápidas para indexar.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                Título (opcional)
              </label>
              <Input
                placeholder="Ex: Anotações da aula, Trecho do artigo..."
                value={clipTitle}
                onChange={e => setClipTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                Texto
              </label>
              <textarea
                value={clipText}
                onChange={e => setClipText(e.target.value)}
                placeholder="Cole ou digite o texto aqui (mínimo 10 caracteres)..."
                rows={8}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-zinc-500 resize-y"
              />
              <p className="mt-1 text-xs text-zinc-600">{clipText.length} caracteres</p>
            </div>
            <Button
              onClick={() => clipMutation.mutate()}
              disabled={clipText.trim().length < 10 || isLoading}
              className="w-full"
            >
              {clipMutation.isPending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Indexando...</>
              ) : (
                <><ClipboardPaste className="mr-2 h-4 w-4" />Indexar Texto</>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Photo tab */}
      {tab === 'photo' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Camera className="h-5 w-5 text-blue-400" />
              Foto / OCR
            </CardTitle>
            <CardDescription>
              Envie uma foto e o texto será extraído automaticamente via IA (Gemini Vision).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                Título (opcional)
              </label>
              <Input
                placeholder="Ex: Página do livro, Quadro branco..."
                value={photoTitle}
                onChange={e => setPhotoTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                Imagem
              </label>
              <div
                onClick={() => document.getElementById('photo-input')?.click()}
                className={cn(
                  'cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors',
                  photoFile
                    ? 'border-blue-500/50 bg-blue-500/5'
                    : 'border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50'
                )}
              >
                {photoPreview ? (
                  <div className="space-y-3">
                    <img
                      src={photoPreview}
                      alt="Preview"
                      className="mx-auto max-h-48 rounded-lg object-contain"
                    />
                    <p className="text-xs text-zinc-400">{photoFile?.name}</p>
                    <p className="text-[10px] text-zinc-600">Clique para trocar</p>
                  </div>
                ) : (
                  <>
                    <Camera className="mx-auto mb-3 h-10 w-10 text-zinc-500" />
                    <p className="text-sm font-medium text-zinc-300">
                      Clique para selecionar uma imagem
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">JPG, PNG, WebP, HEIC</p>
                  </>
                )}
                <input
                  id="photo-input"
                  type="file"
                  accept=".jpg,.jpeg,.png,.webp,.heic"
                  className="hidden"
                  onChange={e => {
                    const file = e.target.files?.[0] ?? null
                    setPhotoFile(file)
                    if (file) {
                      const reader = new FileReader()
                      reader.onload = ev => setPhotoPreview(ev.target?.result as string)
                      reader.readAsDataURL(file)
                    } else {
                      setPhotoPreview(null)
                    }
                  }}
                />
              </div>
            </div>
            <Button
              onClick={() => photoMutation.mutate()}
              disabled={!photoFile || isLoading}
              className="w-full"
            >
              {photoMutation.isPending ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Extraindo texto...</>
              ) : (
                <><Camera className="mr-2 h-4 w-4" />Extrair e Indexar</>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Advanced settings — colapsável */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <button
          onClick={() => setAdvancedOpen(v => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-zinc-800/40 transition-colors"
        >
          <span className="text-sm font-medium text-zinc-400">Configurações Avançadas</span>
          <ChevronDown className={cn('h-4 w-4 text-zinc-500 transition-transform', advancedOpen && 'rotate-180')} />
        </button>
        {advancedOpen && (
          <div className="border-t border-zinc-800/60 px-4 pb-4 pt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                Chunk Size (padrão: 900)
              </label>
              <Input
                type="number"
                placeholder="900"
                value={chunkSize}
                onChange={e => setChunkSize(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                Chunk Overlap (padrão: 150)
              </label>
              <Input
                type="number"
                placeholder="150"
                value={chunkOverlap}
                onChange={e => setChunkOverlap(e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Result */}
      {result && (
        <Card className="border-green-800 bg-green-950/30">
          <CardContent className="py-4">
            <div className="flex items-start gap-3">
              <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-400" />
              <div>
                <p className="font-medium text-green-300">Inserção concluída!</p>
                <p className="mt-1 text-sm text-green-500">
                  {result.files_loaded} documento(s) carregado(s),{' '}
                  {result.chunks_indexed} chunks indexados.
                </p>
                {result.file_names.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {result.file_names.map(f => (
                      <li key={f} className="flex items-center gap-2 text-xs text-green-600">
                        <FileText className="h-3 w-3" />
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

