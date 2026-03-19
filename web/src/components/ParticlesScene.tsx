import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const PARTICLE_COUNT = 120
const REPULSION_RADIUS = 2.5
const CONNECTION_DIST = 2.5
const Z_SPREAD = 6              // depth range — wider = more parallax separation
const Z_SPREAD_HALF = Z_SPREAD * 0.5
const PARALLAX_STRENGTH = 1.5   // max world-space offset for nearest particles
const MOUSE_LERP = 0.08         // smooth mouse interpolation factor
const ATTRACT_STRENGTH = 0.008  // gentle pull toward cursor
const ATTRACT_MAX_FORCE = 0.06  // force cap — prevents chaos
const OFFSET_DAMPING = 0.92     // per-frame velocity decay (lower = heavier feel)
const CONNECTION_DIST_SQ = CONNECTION_DIST * CONNECTION_DIST
const REPULSION_RADIUS_SQ = REPULSION_RADIUS * REPULSION_RADIUS
const MAX_LINES = (PARTICLE_COUNT * (PARTICLE_COUNT - 1)) / 2

// Line base color (blue-violet midpoint)
const LINE_R = 0.35
const LINE_G = 0.42
const LINE_B = 0.95

function Particles() {
  const pointsRef = useRef<THREE.Points>(null!)
  const linesRef = useRef<THREE.LineSegments>(null!)
  // Canvas has pointerEvents:none so R3F `pointer` is always 0,0.
  // Track mouse at window level instead.
  const mouse = useRef({ x: 0, y: 0 })
  const smoothMouse = useRef({ x: 0, y: 0 })

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  const [positions, colors, basePositions, depthFactors, offsets] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3)
    const col = new Float32Array(PARTICLE_COUNT * 3)
    const base = new Float32Array(PARTICLE_COUNT * 3)
    const depth = new Float32Array(PARTICLE_COUNT) // precomputed per-particle parallax weight
    const offs = new Float32Array(PARTICLE_COUNT * 2) // persistent XY attraction offsets

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
      depth[i] = (z + Z_SPREAD_HALF) / Z_SPREAD // 0 (far) → 1 (near), static

      tmp.lerpColors(blue, violet, Math.random())
      col[i3] = tmp.r
      col[i3 + 1] = tmp.g
      col[i3 + 2] = tmp.b
    }
    return [pos, col, base, depth, offs]
  }, [])

  // Pre-allocated line buffers (reused every frame, never recreated)
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

    // Smooth mouse in world coords (for attraction)
    const smxW = smx * vhw
    const smyW = smy * vhh

    // ── Update particle positions (drift + parallax + attraction + repulsion) ──
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      const i2 = i * 2

      const pf = depthFactors[i] * PARALLAX_STRENGTH
      arr[i3] = basePositions[i3] + Math.sin(t + i * 0.3) * 0.3 + smx * pf
      arr[i3 + 1] = basePositions[i3 + 1] + Math.cos(t + i * 0.2) * 0.25 + smy * pf
      arr[i3 + 2] = basePositions[i3 + 2] + Math.sin(t * 0.5 + i * 0.1) * 0.15

      // Attraction: gentle pull toward smooth mouse
      const adx = smxW - arr[i3]
      const ady = smyW - arr[i3 + 1]
      const aDist = Math.sqrt(adx * adx + ady * ady)
      if (aDist > 0.01) {
        const force = Math.min(ATTRACT_STRENGTH * aDist, ATTRACT_MAX_FORCE)
        offsets[i2] += (adx / aDist) * force
        offsets[i2 + 1] += (ady / aDist) * force
      }

      // Damping — creates weight/lag
      offsets[i2] *= OFFSET_DAMPING
      offsets[i2 + 1] *= OFFSET_DAMPING

      // Apply accumulated offset
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

    // ── Build dynamic connections between nearby particles ──
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
          const alpha = 1 - distSq / CONNECTION_DIST_SQ // quadratic fade, no sqrt
          const off = lineCount * 6
          // Vertex A
          linePositions[off] = arr[ix]
          linePositions[off + 1] = arr[ix + 1]
          linePositions[off + 2] = arr[ix + 2]
          // Vertex B
          linePositions[off + 3] = arr[jx]
          linePositions[off + 4] = arr[jx + 1]
          linePositions[off + 5] = arr[jx + 2]
          // Color faded by distance (additive blending: darker = invisible)
          const r = LINE_R * alpha
          const g = LINE_G * alpha
          const b = LINE_B * alpha
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
  })

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.06}
          vertexColors
          transparent
          opacity={0.6}
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
          opacity={0.4}
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
