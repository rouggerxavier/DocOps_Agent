import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, extend, useFrame } from '@react-three/fiber'
import { useAspect, useTexture } from '@react-three/drei'
import { Mesh } from 'three'
import * as THREE from 'three/webgpu'
import {
  abs,
  blendScreen,
  float,
  mod,
  mx_cell_noise_float,
  oneMinus,
  smoothstep,
  texture,
  uniform,
  uv,
  vec2,
  vec3,
} from 'three/tsl'
import { cn } from '@/lib/utils'

const TEXTUREMAP = { src: 'https://i.postimg.cc/XYwvXN8D/img-4.png' }
const DEPTHMAP = { src: 'https://i.postimg.cc/2SHKQh2q/raw-4.webp' }
const WIDTH = 300
const HEIGHT = 300

extend(THREE as any)

type HeroFuturisticMobileLegacyProps = {
  className?: string
  interactive?: boolean
  fallbackMode?: 'still' | 'gradient'
}

class MobileWebGPUErrorBoundary extends React.Component<
  { fallback: React.ReactNode; children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { fallback: React.ReactNode; children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children
  }
}

function Scene({ animated, interactive }: { animated: boolean; interactive: boolean }) {
  const [rawMap, depthMap] = useTexture([TEXTUREMAP.src, DEPTHMAP.src])
  const meshRef = useRef<Mesh>(null)
  const [visible, setVisible] = useState(false)
  const elapsedRef = useRef(0)

  useEffect(() => {
    if (rawMap && depthMap) {
      setVisible(true)
    }
  }, [rawMap, depthMap])

  const { material, uniforms } = useMemo(() => {
    const pointer = uniform(new THREE.Vector2(0, 0))
    const progress = uniform(0)
    const strength = 0.01

    const depthTexture = texture(depthMap)
    const colorTexture = texture(rawMap, uv().add(depthTexture.r.mul(pointer as any).mul(strength)) as any)

    const aspect = float(WIDTH).div(HEIGHT)
    const mappedUv = vec2(uv().x.mul(aspect) as any, uv().y as any)
    const tiledUv = mod(mappedUv.mul(vec2(120.0)), 2.0).sub(1.0)
    const brightness = mx_cell_noise_float(mappedUv.mul(vec2(120.0)).div(2))
    const dist = float(tiledUv.length())
    const dot = float(smoothstep(0.5, 0.49, dist)).mul(brightness)
    const flow = oneMinus(smoothstep(0, 0.02, abs(depthTexture.sub(progress) as any)) as any)
    const baseColor = colorTexture.mul(0.8)
    const lowerBandCut = smoothstep(0.24, 0.44, uv().y as any)
    const mask = dot.mul(flow as any).mul(lowerBandCut as any).mul(vec3(1.45, 0.4, 0.08))
    const final = blendScreen(baseColor, mask)

    return {
      material: new THREE.MeshBasicNodeMaterial({
        colorNode: final,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        opacity: 0,
      }),
      uniforms: {
        pointer,
        progress,
      },
    }
  }, [depthMap, rawMap])

  const [w, h] = useAspect(WIDTH, HEIGHT)

  useFrame((state, delta) => {
    elapsedRef.current += delta
    uniforms.progress.value = animated ? Math.sin(elapsedRef.current * 0.45) * 0.5 + 0.5 : 0.46

    if (interactive && animated) {
      uniforms.pointer.value.set(state.pointer.x, state.pointer.y)
    } else {
      uniforms.pointer.value.set(0, 0)
    }

    if (meshRef.current?.material && 'opacity' in meshRef.current.material) {
      const sceneMaterial = meshRef.current.material as THREE.MeshBasicMaterial & { opacity: number }
      sceneMaterial.opacity = THREE.MathUtils.lerp(sceneMaterial.opacity, visible ? 1 : 0, animated ? 0.08 : 0.12)
    }
  })

  return (
    <mesh ref={meshRef} scale={[w * 0.48, h * 0.48, 1]} material={material}>
      <planeGeometry />
    </mesh>
  )
}

function HeroFallback({ mode }: { mode: 'still' | 'gradient' }) {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(90%_72%_at_72%_18%,rgba(109,137,181,0.1),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.04),transparent_72%),linear-gradient(165deg,rgba(8,10,14,0.98),rgba(5,7,10,1))]" />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain px-4 py-6 opacity-58 mix-blend-screen sm:px-12 sm:py-14"
        />
      ) : null}
      <div className="absolute inset-0 bg-[radial-gradient(72%_56%_at_50%_52%,transparent_42%,rgba(0,0,0,0.48)_100%)]" />
    </div>
  )
}

function HeroBaseLayer({ mode }: { mode: 'still' | 'gradient' }) {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(90%_72%_at_72%_18%,rgba(109,137,181,0.08),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.03),transparent_72%),linear-gradient(165deg,rgba(8,10,14,0.98),rgba(5,7,10,1))]" />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain px-5 py-7 opacity-18 mix-blend-screen sm:px-10 sm:py-12"
        />
      ) : null}
      <div className="absolute inset-0 bg-[radial-gradient(72%_56%_at_50%_52%,transparent_40%,rgba(0,0,0,0.42)_100%)]" />
    </div>
  )
}

export function HeroFuturisticMobileLegacy({
  className,
  interactive = true,
  fallbackMode = 'still',
}: HeroFuturisticMobileLegacyProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [canvasReady, setCanvasReady] = useState(false)

  useEffect(() => {
    const node = containerRef.current
    if (!node) {
      return
    }

    const syncCanvasReadiness = () => {
      const rect = node.getBoundingClientRect()
      setCanvasReady(rect.width >= 16 && rect.height >= 16)
    }

    syncCanvasReadiness()

    if (typeof ResizeObserver === 'undefined') {
      return
    }

    const observer = new ResizeObserver(() => {
      requestAnimationFrame(syncCanvasReadiness)
    })
    observer.observe(node)

    return () => {
      observer.disconnect()
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative isolate min-h-[260px] overflow-hidden rounded-[2rem] border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] shadow-[0_24px_80px_rgba(0,0,0,0.38)] sm:min-h-[360px]',
        className
      )}
    >
      <HeroBaseLayer mode={canvasReady ? 'gradient' : fallbackMode} />
      {canvasReady ? (
        <MobileWebGPUErrorBoundary fallback={<HeroFallback mode={fallbackMode} />}>
          <Canvas
            flat
            frameloop="always"
            dpr={[1, 1.5]}
            className="absolute inset-0 z-10 h-full w-full mix-blend-screen opacity-[0.88]"
            camera={{ position: [0, 0, 1.6], fov: 32 }}
            onCreated={({ gl }) => {
              const canvas = (gl as any)?.domElement as HTMLCanvasElement | undefined
              if (!canvas) return
              canvas.style.position = 'absolute'
              canvas.style.inset = '0'
              canvas.style.width = '100%'
              canvas.style.height = '100%'
              canvas.style.display = 'block'
              canvas.style.mixBlendMode = 'screen'
              const renderer = gl as unknown as { setClearColor?: (color: number, alpha?: number) => void }
              renderer.setClearColor?.(0x000000, 0)
            }}
            gl={async (props) => {
              const renderer = new THREE.WebGPURenderer({
                ...props,
                antialias: true,
                alpha: true,
                forceWebGL: true,
              } as any)
              await renderer.init()
              return renderer
            }}
          >
            <Suspense fallback={null}>
              <Scene animated={true} interactive={interactive} />
            </Suspense>
          </Canvas>
        </MobileWebGPUErrorBoundary>
      ) : (
        <HeroFallback mode={fallbackMode} />
      )}
      <div className="pointer-events-none absolute inset-0 rounded-[2rem] border border-white/5" />
    </div>
  )
}

export default HeroFuturisticMobileLegacy
