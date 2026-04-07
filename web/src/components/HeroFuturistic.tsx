import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, extend, useFrame, useThree } from '@react-three/fiber'
import { useAspect, useTexture } from '@react-three/drei'
import { Mesh } from 'three'
import * as THREE from 'three/webgpu'
import { bloom } from 'three/examples/jsm/tsl/display/BloomNode.js'
import {
  abs,
  add,
  blendScreen,
  float,
  mix,
  mod,
  mx_cell_noise_float,
  oneMinus,
  pass,
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

type HeroFuturisticProps = {
  className?: string
  interactive?: boolean
  fallbackMode?: 'still' | 'gradient'
}

function PostProcessing({ animated }: { animated: boolean }) {
  const { gl, scene, camera } = useThree()
  const progressRef = useRef({ value: 0 })
  const elapsedRef = useRef(0)

  const renderPipeline = useMemo(() => {
    const postProcessing = new THREE.RenderPipeline(gl as any)
    const scenePass = pass(scene, camera)
    const scenePassColor = scenePass.getTextureNode('output')
    const bloomPass = bloom(scenePassColor, 1, 0.5, 1)

    const scanProgress = uniform(0)
    progressRef.current = scanProgress

    const scanPos = float(scanProgress.value)
    const uvY = uv().y as any
    const scanWidth = float(0.05)
    const scanLine = smoothstep(0, scanWidth, abs(uvY.sub(scanPos) as any))
    const glowOverlay = vec3(0.94, 0.56, 0.29).mul(oneMinus(scanLine)).mul(0.3)

    const withScanEffect = mix(
      scenePassColor,
      add(scenePassColor, glowOverlay),
      smoothstep(0.9, 1.0, oneMinus(scanLine))
    )

    postProcessing.outputNode = withScanEffect.add(bloomPass)
    return postProcessing
  }, [camera, gl, scene])

  useFrame((_, delta) => {
    elapsedRef.current += delta
    progressRef.current.value = animated ? Math.sin(elapsedRef.current * 0.45) * 0.5 + 0.5 : 0.44
    void renderPipeline.render()
  }, 1)

  return null
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
    const strength = 0.012

    const depthTexture = texture(depthMap)
    const colorTexture = texture(rawMap, uv().add(depthTexture.r.mul(pointer as any).mul(strength)) as any)

    const aspect = float(WIDTH).div(HEIGHT)
    const mappedUv = vec2(uv().x.mul(aspect) as any, uv().y as any)
    const tiledUv = mod(mappedUv.mul(vec2(120.0)), 2.0).sub(1.0)
    const brightness = mx_cell_noise_float(mappedUv.mul(vec2(120.0)).div(2))
    const dist = float(tiledUv.length())
    const dot = float(smoothstep(0.5, 0.49, dist)).mul(brightness)
    const flow = oneMinus(smoothstep(0, 0.02, abs(depthTexture.sub(progress) as any)) as any)
    const mask = dot.mul(flow as any).mul(vec3(8.2, 2.8, 0.6))
    const final = blendScreen(colorTexture, mask)

    return {
      material: new THREE.MeshBasicNodeMaterial({
        colorNode: final,
        transparent: true,
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
      <div className="absolute inset-0 bg-[radial-gradient(90%_72%_at_72%_18%,rgba(201,139,94,0.2),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.1),transparent_72%),linear-gradient(160deg,rgba(21,24,27,0.96),rgba(12,14,16,1))]" />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain px-4 py-6 opacity-72 mix-blend-screen sm:px-12 sm:py-14"
        />
      ) : null}
      <div className="absolute inset-x-[14%] top-1/2 h-px -translate-y-1/2 bg-[linear-gradient(90deg,transparent,rgba(201,139,94,0.95),transparent)] opacity-85" />
      <div className="absolute inset-0 bg-[radial-gradient(72%_56%_at_50%_52%,transparent_42%,rgba(0,0,0,0.48)_100%)]" />
    </div>
  )
}

function HeroBaseLayer({ mode }: { mode: 'still' | 'gradient' }) {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(90%_72%_at_72%_18%,rgba(201,139,94,0.16),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.08),transparent_72%),linear-gradient(160deg,rgba(21,24,27,0.96),rgba(12,14,16,1))]" />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-contain px-5 py-7 opacity-28 mix-blend-screen sm:px-10 sm:py-12"
        />
      ) : null}
      <div className="absolute inset-x-[12%] top-1/2 h-px -translate-y-1/2 bg-[linear-gradient(90deg,transparent,rgba(201,139,94,0.65),transparent)] opacity-70" />
      <div className="absolute inset-0 bg-[radial-gradient(72%_56%_at_50%_52%,transparent_40%,rgba(0,0,0,0.42)_100%)]" />
    </div>
  )
}

class WebGPUErrorBoundary extends React.Component<
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

export function HeroFuturistic({
  className,
  interactive = true,
  fallbackMode = 'still',
}: HeroFuturisticProps) {
  return (
    <div
      className={cn(
        'relative isolate min-h-[260px] overflow-hidden rounded-[2rem] border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] shadow-[0_24px_80px_rgba(0,0,0,0.38)] sm:min-h-[360px]',
        className
      )}
    >
      <HeroBaseLayer mode={fallbackMode} />
      <WebGPUErrorBoundary fallback={<HeroFallback mode={fallbackMode} />}>
        <Canvas
          flat
          dpr={[1, 1.5]}
          className="relative z-10"
          camera={{ position: [0, 0, 1.6], fov: 32 }}
          gl={async (props) => {
            const renderer = new THREE.WebGPURenderer({ ...props, antialias: true } as any)
            await renderer.init()
            return renderer
          }}
        >
          <Suspense fallback={null}>
            <PostProcessing animated={true} />
            <Scene animated={true} interactive={interactive} />
          </Suspense>
        </Canvas>
      </WebGPUErrorBoundary>
      <div className="pointer-events-none absolute inset-0 rounded-[2rem] border border-white/5" />
      <div className="pointer-events-none absolute inset-x-8 bottom-8 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.16),transparent)]" />
    </div>
  )
}

export default HeroFuturistic
