import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const PARTICLE_COUNT = 120

function Particles() {
  const mesh = useRef<THREE.Points>(null!)

  const [positions, colors, basePositions] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3)
    const col = new Float32Array(PARTICLE_COUNT * 3)
    const base = new Float32Array(PARTICLE_COUNT * 3)

    const blue = new THREE.Color('#3b82f6')
    const violet = new THREE.Color('#8b5cf6')
    const tmp = new THREE.Color()

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      const x = (Math.random() - 0.5) * 14
      const y = (Math.random() - 0.5) * 10
      const z = (Math.random() - 0.5) * 4

      pos[i3] = x
      pos[i3 + 1] = y
      pos[i3 + 2] = z
      base[i3] = x
      base[i3 + 1] = y
      base[i3 + 2] = z

      tmp.lerpColors(blue, violet, Math.random())
      col[i3] = tmp.r
      col[i3 + 1] = tmp.g
      col[i3 + 2] = tmp.b
    }
    return [pos, col, base]
  }, [])

  useFrame(({ clock, pointer, viewport }) => {
    if (!mesh.current) return
    const t = clock.getElapsedTime() * 0.15
    const posAttr = mesh.current.geometry.attributes.position as THREE.BufferAttribute
    const arr = posAttr.array as Float32Array
    const mx = pointer.x * (viewport.width / 2)
    const my = pointer.y * (viewport.height / 2)

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      arr[i3] = basePositions[i3] + Math.sin(t + i * 0.3) * 0.3
      arr[i3 + 1] = basePositions[i3 + 1] + Math.cos(t + i * 0.2) * 0.25
      arr[i3 + 2] = basePositions[i3 + 2] + Math.sin(t * 0.5 + i * 0.1) * 0.15

      const dx = arr[i3] - mx
      const dy = arr[i3 + 1] - my
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 2.5) {
        const force = (2.5 - dist) * 0.04
        arr[i3] += (dx / dist) * force
        arr[i3 + 1] += (dy / dist) * force
      }
    }
    posAttr.needsUpdate = true
  })

  return (
    <points ref={mesh}>
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
