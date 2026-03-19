import { useRef, useState, useLayoutEffect, type RefObject } from 'react'

/**
 * getDynamicDelay — organic, position-aware animation delay.
 *
 * Uses exponential saturation so early items in a sequence are well-separated
 * and later items converge — naturally mirroring how the eye scans a grid.
 * A small sine term adds organic irregularity (breaks mechanical rhythm).
 * The yNorm bonus ensures elements deeper in the page enter slightly later,
 * matching scroll momentum.
 *
 * @param index   Sequential position of the element (0-based)
 * @param yNorm   Element's normalized Y on the page (0 = top, 1 = bottom).
 *                Computed automatically by useDynamicDelay; pass 0 for
 *                above-fold / statically positioned elements.
 * @returns       Delay in seconds, capped at MAX_DELAY
 */
export function getDynamicDelay(index: number, yNorm = 0): number {
  // Exponential saturation: Δdelay per item shrinks as index grows.
  // This prevents the last grid item from waiting half a second.
  const base  = 0.12 * (1 - Math.exp(-index * 0.65))
  const yBonus = yNorm  * 0.06   // deeper elements wait slightly longer
  const noise  = Math.sin(index * 2.3) * 0.009  // organic irregularity
  return Math.min(base + yBonus + noise, 0.50)
}

/**
 * useDynamicDelay — hook that pairs a ref with a position-aware delay.
 *
 * Measures the element's offsetTop at layout time (before paint) and feeds
 * the normalized Y into getDynamicDelay. The ref must be attached to the
 * animated element so the measurement is accurate.
 */
export function useDynamicDelay(index: number): [RefObject<HTMLDivElement | null>, number] {
  const ref   = useRef<HTMLDivElement>(null)
  const [delay, setDelay] = useState(() => getDynamicDelay(index))

  // useLayoutEffect fires synchronously before the browser paints,
  // so the measured value is ready before the first animation frame.
  useLayoutEffect(() => {
    if (!ref.current) return
    const pageH = document.documentElement.scrollHeight || 1
    const yNorm = Math.min(1, ref.current.offsetTop / pageH)
    setDelay(getDynamicDelay(index, yNorm))
  }, [index])

  return [ref, delay]
}
