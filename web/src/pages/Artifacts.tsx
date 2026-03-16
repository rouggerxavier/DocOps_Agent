import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, Download, Eye, FileText, Loader2, Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type ArtifactItem, type DocItem } from '@/api/client'
import { formatBytes, formatDate } from '@/lib/utils'

const ARTIFACT_TYPES = ['study_plan', 'summary', 'checklist', 'artifact'] as const
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

function CreateArtifactDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [type, setType] = useState<string>('study_plan')
  const [topic, setTopic] = useState('')
  const [result, setResult] = useState('')
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<DocItem[]>([])

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const mutation = useMutation({
    mutationFn: () =>
      apiClient.createArtifact(
        type,
        topic,
        undefined,
        selectedDocs.map(doc => doc.doc_id)
      ),
    onSuccess: data => {
      setResult(data.answer)
      qc.invalidateQueries({ queryKey: ['artifacts'] })
      toast.success(`Artefato salvo: ${data.filename}`)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao gerar artefato'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Gerar Artefato</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="p-6 space-y-4">
          {!result ? (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                  Tipo de Artefato
                </label>
                <select
                  value={type}
                  onChange={e => setType(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  {ARTIFACT_TYPES.map(t => (
                    <option key={t} value={t}>
                      {t.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                  TÃ³pico
                </label>
                <Input
                  placeholder="Ex: Python para iniciantes"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                  Documentos para usar (opcional)
                </label>
                <div className="flex gap-2">
                  <select
                    value={selectedDoc}
                    onChange={e => setSelectedDoc(e.target.value)}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                  >
                    <option value="">Selecione um documento</option>
                    {(docs ?? [])
                      .filter(doc => !selectedDocs.some(item => item.doc_id === doc.doc_id))
                      .map(doc => (
                        <option key={doc.doc_id} value={doc.doc_id}>
                          {doc.file_name}
                        </option>
                      ))}
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const docToAdd = (docs ?? []).find(doc => doc.doc_id === selectedDoc)
                      if (!docToAdd || selectedDocs.some(item => item.doc_id === docToAdd.doc_id)) return
                      setSelectedDocs(prev => [...prev, docToAdd])
                      setSelectedDoc('')
                    }}
                    disabled={!selectedDoc}
                  >
                    Adicionar
                  </Button>
                </div>
                {selectedDocs.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedDocs.map(doc => (
                      <span
                        key={doc.doc_id}
                        className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-200"
                      >
                        {doc.file_name}
                        <button
                          type="button"
                          onClick={() =>
                            setSelectedDocs(prev => prev.filter(item => item.doc_id !== doc.doc_id))
                          }
                          className="text-zinc-400 hover:text-red-400"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <Button
                onClick={() => mutation.mutate()}
                disabled={!topic.trim() || mutation.isPending}
                className="w-full"
              >
                {mutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Gerando...
                  </>
                ) : (
                  'Gerar'
                )}
              </Button>
            </>
          ) : (
            <>
              <div className="prose prose-invert prose-sm max-w-none max-h-80 overflow-y-auto">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
              <Button variant="outline" onClick={onClose} className="w-full">
                Fechar
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function PreviewDialog({ filename, onClose }: { filename: string; onClose: () => void }) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let cancelled = false

    if (!isMarkdownArtifact(filename)) {
      if (!cancelled) {
        setContent('Preview disponivel apenas para arquivos de texto (.md, .markdown, .txt).')
        setLoading(false)
      }
      return
    }

    setLoading(true)
    apiClient
      .getArtifactText(filename)
      .then(text => {
        if (cancelled) return
        setContent(text)
      })
      .catch((err: any) => {
        if (cancelled) return
        const msg = err?.response?.data?.detail ?? 'Erro ao carregar arquivo.'
        setContent(typeof msg === 'string' ? msg : 'Erro ao carregar arquivo.')
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [filename])

  async function handleDownload() {
    setDownloading(true)
    try {
      const blob = await apiClient.getArtifactBlob(filename)
      downloadBlobFile(blob, filename)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar arquivo')
    } finally {
      setDownloading(false)
    }
  }

  async function handleDownloadPdf() {
    setDownloading(true)
    try {
      const blob = await apiClient.getArtifactPdfBlob(filename)
      downloadBlobFile(blob, toPdfName(filename))
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar PDF')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100 truncate">{filename}</h2>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={downloading}>
              <Download className="h-4 w-4 mr-1" />
              Download
            </Button>
            {isMarkdownArtifact(filename) && (
              <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading}>
                <FileText className="h-4 w-4 mr-1" />
                PDF
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-4 w-full" />)}
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown>{content ?? ''}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function Artifacts() {
  const [showCreate, setShowCreate] = useState(false)
  const [previewFile, setPreviewFile] = useState<string | null>(null)
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)

  const { data: artifacts, isLoading, error } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts'],
    queryFn: apiClient.listArtifacts,
    retry: 1,
  })

  async function handleDownload(filename: string) {
    const key = `${filename}:file`
    setDownloadingKey(key)
    try {
      const blob = await apiClient.getArtifactBlob(filename)
      downloadBlobFile(blob, filename)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar arquivo')
    } finally {
      setDownloadingKey(null)
    }
  }

  async function handleDownloadPdf(filename: string) {
    const key = `${filename}:pdf`
    setDownloadingKey(key)
    try {
      const blob = await apiClient.getArtifactPdfBlob(filename)
      downloadBlobFile(blob, toPdfName(filename))
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Erro ao baixar PDF')
    } finally {
      setDownloadingKey(null)
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Artefatos</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Resumos, planos de estudo e checklists gerados pelo agente
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Novo Artefato
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Erro ao carregar artefatos.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      )}

      {!isLoading && (!artifacts || artifacts.length === 0) && !error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <Archive className="h-12 w-12 text-zinc-600" />
            <p className="font-medium text-zinc-300">Nenhum artefato gerado</p>
            <p className="text-sm text-zinc-500">
              Gere resumos, planos de estudo e checklists
            </p>
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Criar Artefato
            </Button>
          </CardContent>
        </Card>
      )}

      {artifacts && artifacts.length > 0 && (
        <div className="space-y-2">
          {artifacts.map(artifact => {
            const isMarkdown = isMarkdownArtifact(artifact.filename)

            return (
              <Card
                key={`${artifact.filename}-${artifact.created_at}`}
                className="hover:border-zinc-700 transition-colors"
              >
                <CardContent className="flex items-center justify-between py-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <Archive className="h-5 w-5 shrink-0 text-blue-400" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-zinc-100 truncate">
                        {artifact.title?.trim() ? artifact.title : artifact.filename}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {artifact.artifact_type ? `${artifact.artifact_type} · ` : ''}{formatBytes(artifact.size)} · {formatDate(artifact.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    {isMarkdown && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPreviewFile(artifact.filename)}
                      >
                        <Eye className="h-4 w-4 mr-1" />
                        Preview
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDownload(artifact.filename)}
                      disabled={downloadingKey !== null}
                    >
                      <Download className="h-4 w-4 mr-1" />
                      {downloadingKey === `${artifact.filename}:file` ? 'Baixando...' : 'Download'}
                    </Button>
                    {isMarkdown && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownloadPdf(artifact.filename)}
                        disabled={downloadingKey !== null}
                      >
                        <FileText className="h-4 w-4 mr-1" />
                        {downloadingKey === `${artifact.filename}:pdf` ? 'Baixando...' : 'PDF'}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {showCreate && <CreateArtifactDialog onClose={() => setShowCreate(false)} />}
      {previewFile && (
        <PreviewDialog filename={previewFile} onClose={() => setPreviewFile(null)} />
      )}
    </div>
  )
}

