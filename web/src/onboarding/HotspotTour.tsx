import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useOnboarding } from './OnboardingContext'

// ── Tour step catalog ─────────────────────────────────────────────────────────

interface TourStep {
  target: string   // valor do data-tour-id
  title: string
  content: string
}

const TOUR_CATALOG: Record<string, TourStep[]> = {
  ingest: [
    {
      target: 'ingest-tabs',
      title: '4 formas de inserir conteúdo',
      content: 'Escolha entre Upload de arquivo, Caminho no servidor, Clip de texto ou Foto com OCR — cada um tem seu fluxo dedicado.',
    },
    {
      target: 'ingest-dropzone',
      title: 'Arraste ou clique para enviar',
      content: 'Solte PDFs, Markdown ou TXT aqui. Também aceitamos planilhas Excel e CSV. O conteúdo é extraído, dividido em chunks e indexado automaticamente.',
    },
    {
      target: 'ingest-progress',
      title: 'Progresso em tempo real',
      content: 'Acompanhe extração, chunking e indexação. Quando concluído, o documento já fica disponível para consulta no Chat.',
    },
  ],
  chat: [
    {
      target: 'chat-composer',
      title: 'Faça sua pergunta aqui',
      content: 'O agente responde com base nos documentos indexados, com citações numeradas em cada trecho usado. Pressione Enter para enviar.',
    },
    {
      target: 'chat-attachment',
      title: 'Documentos e tratamento',
      content: 'Filtre a resposta por documentos específicos e ajuste profundidade, tom e rigor da resposta para cada conversa.',
    },
    {
      target: 'chat-grounding',
      title: 'Modo estrito de grounding',
      content: 'Ativado: responde só quando há evidência forte nos docs. Desativado (equilibrado): responde mesmo com cobertura parcial.',
    },
  ],
  artifacts: [
    {
      target: 'artifacts-actions',
      title: 'Crie artefatos a partir dos seus docs',
      content: 'Resuma documentos, gere Smart Digests ou crie artefatos customizados. Cada operação salva o resultado para consulta futura.',
    },
    {
      target: 'artifacts-summarize',
      title: 'Resumir Documento',
      content: 'Escolha um documento, selecione o modo (breve ou profundo) e gere um resumo estruturado em segundos.',
    },
    {
      target: 'artifacts-list',
      title: 'Histórico de artefatos',
      content: 'Filtre por tipo, data ou documento de origem. Baixe em Markdown ou PDF, visualize no preview ou use como base para o chat.',
    },
  ],
}

// ── Spotlight + Tooltip ───────────────────────────────────────────────────────

const TOOLTIP_W = 280
const TOOLTIP_OFFSET = 14
const VIEWPORT_PAD = 12

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

interface TooltipPos {
  top: number
  left: number
  arrowSide: 'top' | 'bottom'
}

function calcTooltipPos(rect: DOMRect, tooltipH: number): TooltipPos {
  const vw = window.innerWidth
  const vh = window.innerHeight

  const spaceBelow = vh - rect.bottom
  const spaceAbove = rect.top
  const placeBelow = spaceBelow >= tooltipH + TOOLTIP_OFFSET || spaceBelow >= spaceAbove

  const top = placeBelow
    ? rect.bottom + TOOLTIP_OFFSET
    : rect.top - tooltipH - TOOLTIP_OFFSET

  const idealLeft = rect.left + rect.width / 2 - TOOLTIP_W / 2
  const left = clamp(idealLeft, VIEWPORT_PAD, vw - TOOLTIP_W - VIEWPORT_PAD)

  return { top, left, arrowSide: placeBelow ? 'top' : 'bottom' }
}

// ── Main component ────────────────────────────────────────────────────────────

export function HotspotTour() {
  const { activeTour, closeTour } = useOnboarding()
  const [stepIdx, setStepIdx] = useState(0)
  const [spotRect, setSpotRect] = useState<DOMRect | null>(null)
  const [tooltipH, setTooltipH] = useState(160)
  const [direction, setDirection] = useState(1)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  const steps = activeTour ? (TOUR_CATALOG[activeTour] ?? []) : []
  const step = steps[stepIdx]

  // Measure tooltip height after render
  useLayoutEffect(() => {
    if (tooltipRef.current) {
      setTooltipH(tooltipRef.current.offsetHeight)
    }
  })

  // Find target element, scroll into view, record rect
  useEffect(() => {
    if (!step) return
    const el = document.querySelector<HTMLElement>(`[data-tour-id="${step.target}"]`)
    if (!el) { setSpotRect(null); return }

    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })

    // Give the scroll time to settle before measuring
    const t = window.setTimeout(() => {
      setSpotRect(el.getBoundingClientRect())
    }, 220)
    return () => window.clearTimeout(t)
  }, [step])

  // Auto-focus close button when tour opens
  useEffect(() => {
    if (activeTour) {
      setStepIdx(0)
      window.setTimeout(() => closeButtonRef.current?.focus(), 100)
    }
  }, [activeTour])

  // ESC closes
  useEffect(() => {
    if (!activeTour) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') closeTour()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [activeTour, closeTour])

  if (!activeTour || steps.length === 0) return null

  function navigate(delta: number) {
    setDirection(delta)
    setStepIdx((i) => clamp(i + delta, 0, steps.length - 1))
    setSpotRect(null)
  }

  const isFirst = stepIdx === 0
  const isLast = stepIdx === steps.length - 1
  const tooltipPos = spotRect ? calcTooltipPos(spotRect, tooltipH) : null

  return (
    <>
      {/* Dimmed overlay — pointer-events only on the overlay itself, not the spotlight */}
      <div
        className="fixed inset-0 z-[110]"
        style={{ background: 'rgba(0,0,0,0)' }}
        onClick={closeTour}
        aria-hidden="true"
      />

      {/* Spotlight highlight */}
      {spotRect && (
        <motion.div
          key={step.target}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.18 }}
          className="pointer-events-none fixed z-[111] rounded-xl"
          style={{
            top: spotRect.top - 4,
            left: spotRect.left - 4,
            width: spotRect.width + 8,
            height: spotRect.height + 8,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.62)',
            outline: '2px solid var(--ui-accent)',
          }}
        />
      )}

      {/* Tooltip */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`${activeTour}-${stepIdx}`}
          ref={tooltipRef}
          role="dialog"
          aria-modal="false"
          aria-label={step?.title}
          custom={direction}
          initial={{ opacity: 0, y: direction > 0 ? 8 : -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: direction > 0 ? -8 : 8 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="fixed z-[112] rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface)] p-4 shadow-2xl"
          style={{
            width: TOOLTIP_W,
            top: tooltipPos?.top ?? '50%',
            left: tooltipPos?.left ?? '50%',
            transform: tooltipPos ? 'none' : 'translate(-50%, -50%)',
          }}
        >
          {/* Close */}
          <button
            ref={closeButtonRef}
            type="button"
            onClick={closeTour}
            className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-md text-[color:var(--ui-text-dim)] hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]"
            aria-label="Fechar tour"
          >
            <X className="h-3.5 w-3.5" />
          </button>

          {/* Step counter */}
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--ui-accent)]">
            {stepIdx + 1} / {steps.length}
          </p>

          <p className="pr-5 text-sm font-semibold text-[color:var(--ui-text)]">{step.title}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-[color:var(--ui-text-dim)]">{step.content}</p>

          {/* Navigation */}
          <div className="mt-3 flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={closeTour}
              className="h-7 px-2 text-[11px] text-[color:var(--ui-text-meta)]"
            >
              Pular tour
            </Button>
            <div className="flex items-center gap-1">
              {!isFirst && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(-1)}
                  className="h-7 w-7 p-0"
                  aria-label="Passo anterior"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
              )}
              {!isLast ? (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => navigate(1)}
                  className={cn('h-7 bg-[color:var(--ui-accent)] px-3 text-[11px] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]')}
                >
                  Próximo
                  <ChevronRight className="h-3 w-3" />
                </Button>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  onClick={closeTour}
                  className="h-7 bg-[color:var(--ui-accent)] px-3 text-[11px] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
                >
                  Concluir
                </Button>
              )}
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </>
  )
}
