import { useState, useCallback, useRef } from 'react'
import { apiClient } from '@/api/client'

// ── Card structure for the "IA em ação" demo section ──

export type AICategory = 'tasks' | 'flashcards' | 'schedule' | 'summary' | 'suggestions' | 'general'

export interface AICard {
  title: string
  items: string[]
  category: AICategory
}

export interface AIResult {
  cards: AICard[]
  raw: string
  isMock: boolean
}

// ── Mock fallback (generated dynamically from the prompt topic) ──

function extractTopic(prompt: string): string {
  // Strip common command words to isolate the subject
  return prompt
    .replace(/^(quero|preciso|me ajude a?|crie|gere|monte|organize|faça|elabore|liste|resuma)\s+/i, '')
    .replace(/^(um|uma|o|a|os|as)\s+/i, '')
    .replace(/\s+(para|sobre|de|do|da|dos|das)\s+/i, ' ')
    .trim()
    .slice(0, 60)
}

function buildMockCards(prompt: string): AICard[] {
  const topic = extractTopic(prompt) || 'o tema solicitado'
  const topicCap = topic.charAt(0).toUpperCase() + topic.slice(1)
  return [
    {
      category: 'tasks',
      title: 'Tarefas criadas',
      items: [
        `Estudar fundamentos de ${topic}`,
        `Criar resumo dos pontos principais de ${topic}`,
        `Praticar exercícios relacionados a ${topic}`,
      ],
    },
    {
      category: 'flashcards',
      title: 'Flashcards gerados',
      items: [
        `O que é ${topic}?`,
        `Quais são os conceitos-chave de ${topic}?`,
        `Como aplicar ${topic} na prática?`,
      ],
    },
    {
      category: 'schedule',
      title: 'Agenda organizada',
      items: [
        `Seg — Introdução a ${topicCap}`,
        `Qua — Aprofundamento em ${topicCap}`,
        `Sex — Revisão e prática de ${topicCap}`,
      ],
    },
  ]
}

// ── Response parser ──

// Pre-compiled regexes (avoid re-compilation per line)
const RE_HEADER = /^#{1,3}\s+(.+)/
const RE_BOLD = /^\*\*(.+?)\*\*:?\s*$/
const RE_BULLET = /^[-*•]\s+(.+)/
const RE_NUMBERED = /^\d+[.)]\s+(.+)/
const RE_STARS = /\*+/g
const RE_CLEAN = /^[-*•]\s+|^\d+[.)]\s+|^#{1,3}\s+|\*+/g

const CATEGORY_KEYWORDS: Record<AICategory, string[]> = {
  tasks: ['tarefa', 'task', 'ação', 'ações', 'to-do', 'afazer', 'passo', 'etapa'],
  flashcards: ['flashcard', 'card', 'revisão', 'pergunta', 'quiz'],
  schedule: ['agenda', 'cronograma', 'horário', 'calendário', 'semana', 'dia', 'planejamento'],
  summary: ['resumo', 'summary', 'visão geral', 'overview', 'síntese'],
  suggestions: ['sugestão', 'dica', 'recomendação', 'conselho', 'recurso'],
  general: [],
}

const FALLBACK_SECTIONS: Array<{ title: string; category: AICategory }> = [
  { title: 'Sugestões', category: 'suggestions' },
  { title: 'Ações', category: 'tasks' },
  { title: 'Organização', category: 'schedule' },
]

function detectCategory(title: string): AICategory {
  const lower = title.toLowerCase()
  for (const [cat, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    if (cat === 'general') continue
    if (keywords.some(kw => lower.includes(kw))) return cat as AICategory
  }
  return 'general'
}

function pushSection(cards: AICard[], title: string, items: string[]) {
  if (title && items.length > 0) {
    cards.push({ title, items, category: detectCategory(title) })
  }
}

function parseResponse(answer: string): AICard[] {
  const cards: AICard[] = []
  const lines = answer.split('\n').map(l => l.trim()).filter(Boolean)

  let currentTitle = ''
  let currentItems: string[] = []

  for (const line of lines) {
    // Markdown header → new section
    const headerMatch = line.match(RE_HEADER)
    if (headerMatch) {
      pushSection(cards, currentTitle, currentItems)
      currentTitle = headerMatch[1].replace(RE_STARS, '').trim()
      currentItems = []
      continue
    }

    // Bold line as section title
    const boldMatch = line.match(RE_BOLD)
    if (boldMatch) {
      pushSection(cards, currentTitle, currentItems)
      currentTitle = boldMatch[1].trim()
      currentItems = []
      continue
    }

    // Bullet point or numbered list → item
    const bulletMatch = line.match(RE_BULLET) || line.match(RE_NUMBERED)
    if (bulletMatch) {
      currentItems.push(bulletMatch[1].replace(RE_STARS, '').trim())
      continue
    }

    // Plain text line long enough to be an item
    if (currentTitle && line.length > 10) {
      currentItems.push(line.replace(RE_STARS, '').trim())
    }
  }

  // Save last section
  pushSection(cards, currentTitle, currentItems)

  // If parsing failed, split all extractable items into 3 synthetic cards
  if (cards.length === 0) {
    const allItems = lines
      .map(l => l.replace(RE_CLEAN, ''))
      .filter(l => l.length > 5)
      .slice(0, 9)

    if (allItems.length > 0) {
      const perCard = Math.ceil(allItems.length / 3)
      for (let i = 0; i < 3 && i * perCard < allItems.length; i++) {
        cards.push({
          title: FALLBACK_SECTIONS[i].title,
          items: allItems.slice(i * perCard, (i + 1) * perCard),
          category: FALLBACK_SECTIONS[i].category,
        })
      }
    }
  }

  // Cap at 3 cards, 4 items each
  return cards.slice(0, 3).map(c => ({ ...c, items: c.items.slice(0, 4) }))
}

// ── Hook ──

const MIN_LOADING_MS = 800

export function useAI() {
  const [result, setResult] = useState<AIResult | null>(null)
  const [loading, setLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(async (prompt: string) => {
    if (!prompt.trim()) return

    // Cancel any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setResult(null)

    const minDelay = new Promise(r => setTimeout(r, MIN_LOADING_MS))

    try {
      const [response] = await Promise.all([
        apiClient.chat(prompt),
        minDelay,
      ])

      // Ignore if this request was superseded
      if (controller.signal.aborted) return

      const cards = parseResponse(response.answer)
      if (cards.length === 0) {
        setResult({ cards: buildMockCards(prompt), raw: response.answer, isMock: true })
      } else {
        setResult({ cards, raw: response.answer, isMock: false })
      }
    } catch {
      if (controller.signal.aborted) return
      await minDelay
      setResult({ cards: buildMockCards(prompt), raw: '', isMock: true })
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  const reset = useCallback(() => setResult(null), [])

  return { run, result, loading, reset }
}
