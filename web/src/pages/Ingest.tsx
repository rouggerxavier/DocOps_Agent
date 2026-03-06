import { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Upload, FolderOpen, CheckCircle, X, FileText } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiClient, type IngestResponse } from '@/api/client'
import { cn } from '@/lib/utils'

export function Ingest() {
  // Upload tab state
  const [dragOver, setDragOver] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Path tab state
  const [serverPath, setServerPath] = useState('')

  // Advanced
  const [chunkSize, setChunkSize] = useState('')
  const [chunkOverlap, setChunkOverlap] = useState('')

  // Active tab
  const [tab, setTab] = useState<'upload' | 'path'>('upload')

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
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao ingerir arquivos')
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
      toast.success(`${data.chunks_indexed} chunks indexados com sucesso!`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Erro ao ingerir caminho')
    },
  })

  const isLoading = uploadMutation.isPending || pathMutation.isPending

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files).filter(f =>
      /\.(pdf|txt|md|markdown)$/i.test(f.name)
    )
    setSelectedFiles(prev => [...prev, ...files])
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Ingestão de Documentos</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Indexe PDFs, Markdown e arquivos de texto no Chroma
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex rounded-lg border border-zinc-800 bg-zinc-900 p-1 w-fit">
        {(['upload', 'path'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
              tab === t
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200'
            )}
          >
            {t === 'upload' ? 'Upload de Arquivo' : 'Caminho do Servidor'}
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
              Arraste arquivos ou clique para selecionar. Suporta PDF, TXT, MD.
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
              <p className="mt-1 text-xs text-zinc-500">PDF, TXT, MD, MARKDOWN</p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.md,.markdown"
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

            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={selectedFiles.length === 0 || isLoading}
              className="w-full"
            >
              {isLoading ? 'Indexando...' : 'Indexar Arquivos'}
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
            <Button
              onClick={() => pathMutation.mutate()}
              disabled={!serverPath.trim() || isLoading}
              className="w-full"
            >
              {isLoading ? 'Indexando...' : 'Indexar Caminho'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Advanced settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-zinc-400">Configurações Avançadas</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
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
        </CardContent>
      </Card>

      {/* Result */}
      {result && (
        <Card className="border-green-800 bg-green-950/30">
          <CardContent className="py-4">
            <div className="flex items-start gap-3">
              <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-400" />
              <div>
                <p className="font-medium text-green-300">Ingestão concluída!</p>
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
