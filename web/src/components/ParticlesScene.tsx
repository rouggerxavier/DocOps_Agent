import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useScrollProgress } from '@/hooks/useScrollProgress'

const PARTICLE_COUNT = 90
const REPULSION_RADIUS = 2.5
const CONNECTION_DIST = 2.2
const Z_SPREAD = 6
const Z_SPREAD_HALF = Z_SPREAD * 0.5
const PARALLAX_STRENGTH = 1.5
const MOUSE_LERP = 0.08
const ATTRACT_STRENGTH = 0.008
const ATTRACT_MAX_FORCE = 0.06
const OFFSET_DAMPING = 0.92
const SCROLL_LERP = 0.05
const CONNECTION_DIST_SQ = CONNECTION_DIST * CONNECTION_DIST
const REPULSION_RADIUS_SQ = REPULSION_RADIUS * REPULSION_RADIUS
const MAX_LINES = (PARTICLE_COUNT * (PARTICLE_COUNT - 1)) / 2

// Cursor proximity amplification for connection lines
const LINE_CURSOR_RADIUS = 3.0
const LINE_CURSOR_RADIUS_SQ = LINE_CURSOR_RADIUS * LINE_CURSOR_RADIUS
const LINE_CURSOR_BOOST = 2.5

// Line base color (blue-violet midpoint)
const LINE_R = 0.35
const LINE_G = 0.42
const LINE_B = 0.95

/** Programmatic glow texture — soft radial falloff for particle halos */
function createGlowTexture(): THREE.Texture {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const half = size / 2
  const gradient = ctx.createRadialGradient(half, half, 0, half, half, half)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.15, 'rgba(255,255,255,0.7)')
  gradient.addColorStop(0.4, 'rgba(255,255,255,0.25)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true
  return texture
}

function Particles() {
  const pointsRef = useRef<THREE.Points>(null!)
  const linesRef = useRef<THREE.LineSegments>(null!)
  const mouse = useRef({ x: 0, y: 0 })
  const smoothMouse = useRef({ x: 0, y: 0 })
  const scrollRef = useScrollProgress()
  const smoothScroll = useRef(0)

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  const glowTexture = useMemo(() => createGlowTexture(), [])

  const [positions, colors, basePositions, depthFactors, offsets] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3)
    const col = new Float32Array(PARTICLE_COUNT * 3)
    const base = new Float32Array(PARTICLE_COUNT * 3)
    const depth = new Float32Array(PARTICLE_COUNT)
    const offs = new Float32Array(PARTICLE_COUNT * 2)

    const blue = new THREE.Color('#3b82f6')
    const violet = new THREE.Color('#8b5cf6')
    const tmp = new THREE.Color()

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      const x = (Math.random() - 0.5) * 14
      const y = (Math.random() - 0.5) * 10
      const z = (Math.random() - 0.5) * Z_SPREAD

      pos[i3] = x
      pos[i3 + 1] = y
      pos[i3 + 2] = z
      base[i3] = x
      base[i3 + 1] = y
      base[i3 + 2] = z
      depth[i] = (z + Z_SPREAD_HALF) / Z_SPREAD

      tmp.lerpColors(blue, violet, Math.random())
      col[i3] = tmp.r
      col[i3 + 1] = tmp.g
      col[i3 + 2] = tmp.b
    }
    return [pos, col, base, depth, offs]
  }, [])

  const [linePositions, lineColors] = useMemo(
    () => [new Float32Array(MAX_LINES * 6), new Float32Array(MAX_LINES * 6)],
    [],
  )

  useFrame(({ clock, viewport }) => {
    if (!pointsRef.current || !linesRef.current) return
    const t = clock.getElapsedTime() * 0.15
    const posAttr = pointsRef.current.geometry.attributes.position as THREE.BufferAttribute
    const arr = posAttr.array as Float32Array
    const vhw = viewport.width / 2
    const vhh = viewport.height / 2
    const mx = mouse.current.x * vhw
    const my = mouse.current.y * vhh

    // ── Smooth mouse tracking for parallax (lerp) ──
    smoothMouse.current.x += (mouse.current.x - smoothMouse.current.x) * MOUSE_LERP
    smoothMouse.current.y += (mouse.current.y - smoothMouse.current.y) * MOUSE_LERP
    const smx = smoothMouse.current.x
    const smy = smoothMouse.current.y
    const smxW = smx * vhw
    const smyW = smy * vhh

    // ── Smooth scroll tracking ──
    smoothScroll.current += (scrollRef.current - smoothScroll.current) * SCROLL_LERP
    const scroll = smoothScroll.current
    const driftScale = 1 + scroll * 0.8
    const lineBaseR = LINE_R + scroll * 0.2
    const lineBaseG = LINE_G + scroll * 0.04
    const lineBaseB = LINE_B - scroll * 0.12

    // ── Update particle positions (organic drift + parallax + attraction + repulsion) ──
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      const i2 = i * 2

      const pf = depthFactors[i] * PARALLAX_STRENGTH

      // Multi-frequency organic drift — golden-ratio offset per particle
      const seed = i * 1.618
      const xDrift = (
        Math.sin(t * 0.7 + seed * 1.3) * 0.22 +
        Math.sin(t * 0.3 + seed * 2.1) * 0.15 +
        Math.cos(t * 0.5 + seed * 0.7) * 0.08
      ) * driftScale
      const yDrift = (
        Math.cos(t * 0.6 + seed * 1.1) * 0.20 +
        Math.sin(t * 0.25 + seed * 1.7) * 0.12 +
        Math.cos(t * 0.4 + seed * 0.9) * 0.08
      ) * driftScale
      const zDrift = Math.sin(t * 0.35 + seed * 0.5) * 0.12

      arr[i3] = basePositions[i3] + xDrift + smx * pf
      arr[i3 + 1] = basePositions[i3 + 1] + yDrift + smy * pf
      arr[i3 + 2] = basePositions[i3 + 2] + zDrift

      // Attraction: gentle pull toward smooth mouse
      const adx = smxW - arr[i3]
      const ady = smyW - arr[i3 + 1]
      const aDist = Math.sqrt(adx * adx + ady * ady)
      if (aDist > 0.01) {
        const force = Math.min(ATTRACT_STRENGTH * aDist, ATTRACT_MAX_FORCE)
        offsets[i2] += (adx / aDist) * force
        offsets[i2 + 1] += (ady / aDist) * force
      }

      offsets[i2] *= OFFSET_DAMPING
      offsets[i2 + 1] *= OFFSET_DAMPING

      arr[i3] += offsets[i2]
      arr[i3 + 1] += offsets[i2 + 1]

      // Close-range repulsion (raw mouse — immediate response)
      const dx = arr[i3] - mx
      const dy = arr[i3 + 1] - my
      const distSqR = dx * dx + dy * dy
      if (distSqR < REPULSION_RADIUS_SQ) {
        const dist = Math.sqrt(distSqR)
        const force = (REPULSION_RADIUS - dist) * 0.04
        arr[i3] += (dx / dist) * force
        arr[i3 + 1] += (dy / dist) * force
      }
    }
    posAttr.needsUpdate = true

    // ── Build dynamic connections with cursor proximity amplification ──
    let lineCount = 0
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const ix = i * 3
      for (let j = i + 1; j < PARTICLE_COUNT; j++) {
        const jx = j * 3
        const dx = arr[ix] - arr[jx]
        const dy = arr[ix + 1] - arr[jx + 1]
        const dz = arr[ix + 2] - arr[jx + 2]
        const distSq = dx * dx + dy * dy + dz * dz
        if (distSq < CONNECTION_DIST_SQ) {
          const alpha = 1 - distSq / CONNECTION_DIST_SQ

          // Cursor proximity boost — lines near mouse glow brighter
          const midX = (arr[ix] + arr[jx]) * 0.5
          const midY = (arr[ix + 1] + arr[jx + 1]) * 0.5
          const cmDx = midX - smxW
          const cmDy = midY - smyW
          const cursorDistSq = cmDx * cmDx + cmDy * cmDy
          const cursorFactor = cursorDistSq < LINE_CURSOR_RADIUS_SQ
            ? 1 + (LINE_CURSOR_BOOST - 1) * (1 - cursorDistSq / LINE_CURSOR_RADIUS_SQ)
            : 1

          const off = lineCount * 6
          linePositions[off] = arr[ix]
          linePositions[off + 1] = arr[ix + 1]
          linePositions[off + 2] = arr[ix + 2]
          linePositions[off + 3] = arr[jx]
          linePositions[off + 4] = arr[jx + 1]
          linePositions[off + 5] = arr[jx + 2]

          const r = lineBaseR * alpha * cursorFactor
          const g = lineBaseG * alpha * cursorFactor
          const b = lineBaseB * alpha * cursorFactor
          lineColors[off] = r;     lineColors[off + 1] = g;     lineColors[off + 2] = b
          lineColors[off + 3] = r; lineColors[off + 4] = g; lineColors[off + 5] = b
          lineCount++
        }
      }
    }

    const linePosAttr = linesRef.current.geometry.attributes.position as THREE.BufferAttribute
    const lineColAttr = linesRef.current.geometry.attributes.color as THREE.BufferAttribute
    linePosAttr.needsUpdate = true
    lineColAttr.needsUpdate = true
    linesRef.current.geometry.setDrawRange(0, lineCount * 2)

    // ── Scroll-reactive material (gentler fade — particles stay longer) ──
    const ptMat = pointsRef.current.material as THREE.PointsMaterial
    ptMat.size = 0.15 - scroll * 0.01
    ptMat.opacity = 0.55 - scroll * 0.08
    ptMat.color.setRGB(1 + scroll * 0.15, 1 - scroll * 0.05, 1 - scroll * 0.15)

    const lnMat = linesRef.current.material as THREE.LineBasicMaterial
    lnMat.opacity = 0.30 - scroll * 0.08
  })

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          map={glowTexture}
          size={0.15}
          vertexColors
          transparent
          opacity={0.55}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <lineSegments ref={linesRef}>
        <bufferGeometry drawRange={{ start: 0, count: 0 }}>
          <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
          <bufferAttribute attach="attributes-color" args={[lineColors, 3]} />
        </bufferGeometry>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.30}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </lineSegments>
    </group>
  )
}

export default function ParticlesScene() {
  return (
    <Canvas
      className="!absolute inset-0"
      camera={{ position: [0, 0, 5], fov: 60 }}
      dpr={[1, 1.5]}
      gl={{ antialias: false, alpha: true, powerPreference: 'low-power' }}
      style={{ pointerEvents: 'none' }}
      frameloop="always"
    >
      <Particles />
    </Canvas>
  )
}
