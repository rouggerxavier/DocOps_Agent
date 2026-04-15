import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  variant?: 'card' | 'hero'
  focus?: 'center' | 'right'
}

function PostProcessing({ animated, scanEnabled = true }: { animated: boolean; scanEnabled?: boolean }) {
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
    const glowOverlay = vec3(0.58, 0.77, 0.99).mul(oneMinus(scanLine)).mul(0.3)

    const withScanEffect = mix(
      scenePassColor,
      add(scenePassColor, glowOverlay),
      smoothstep(0.9, 1.0, oneMinus(scanLine))
    )

    postProcessing.outputNode = scanEnabled ? withScanEffect.add(bloomPass) : scenePassColor.add(bloomPass)
    return postProcessing
  }, [camera, gl, scanEnabled, scene])

  useFrame((_, delta) => {
    elapsedRef.current += delta
    progressRef.current.value = animated && scanEnabled ? Math.sin(elapsedRef.current * 0.45) * 0.5 + 0.5 : 0.44
    void renderPipeline.render()
  }, 1)

  return null
}

function Scene({
  animated,
  interactive,
  focus,
}: {
  animated: boolean
  interactive: boolean
  focus: 'center' | 'right'
}) {
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
  const scaleFactor = focus === 'right' ? 0.32 : 0.48
  const offsetX = focus === 'right' ? 0.84 : 0
  const offsetY = focus === 'right' ? 0.02 : 0

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
    <mesh ref={meshRef} position={[offsetX, offsetY, 0]} scale={[w * scaleFactor, h * scaleFactor, 1]} material={material}>
      <planeGeometry />
    </mesh>
  )
}

function HeroFallback({
  mode,
  variant,
  focus,
}: {
  mode: 'still' | 'gradient'
  variant: 'card' | 'hero'
  focus: 'center' | 'right'
}) {
  const isHero = variant === 'hero'
  const rightFocus = focus === 'right'
  return (
    <div className={cn('absolute inset-0', isHero ? 'overflow-visible' : 'overflow-hidden')}>
      <div
        className={cn(
          'absolute inset-0',
          isHero && rightFocus
            ? 'bg-[linear-gradient(180deg,rgba(6,8,12,1)_0%,rgba(6,8,12,1)_100%)]'
            : 'bg-[radial-gradient(90%_72%_at_72%_18%,rgba(147,197,253,0.2),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.1),transparent_72%),linear-gradient(160deg,rgba(21,24,27,0.96),rgba(12,14,16,1))]'
        )}
      />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className={cn(
            'absolute inset-0 h-full w-full mix-blend-screen',
            isHero
              ? 'hidden'
              : 'object-contain px-4 py-6 opacity-72 sm:px-12 sm:py-14'
          )}
        />
      ) : null}
      <div
        className={cn(
          'absolute h-px -translate-y-1/2 bg-[linear-gradient(90deg,transparent,rgba(147,197,253,0.95),transparent)]',
          isHero ? 'hidden' : 'inset-x-[14%] top-1/2 opacity-85'
        )}
      />
      <div
        className={cn(
          'absolute inset-0',
          isHero
            ? 'bg-[radial-gradient(84%_70%_at_80%_54%,transparent_40%,rgba(6,8,12,0.54)_100%)]'
            : 'bg-[radial-gradient(72%_56%_at_50%_52%,transparent_42%,rgba(0,0,0,0.48)_100%)]'
        )}
      />
    </div>
  )
}

function HeroBaseLayer({
  mode,
  variant,
  focus,
}: {
  mode: 'still' | 'gradient'
  variant: 'card' | 'hero'
  focus: 'center' | 'right'
}) {
  const isHero = variant === 'hero'
  const rightFocus = focus === 'right'
  return (
    <div className={cn('absolute inset-0', isHero ? 'overflow-visible' : 'overflow-hidden')}>
      <div
        className={cn(
          'absolute inset-0',
          isHero && rightFocus
            ? 'bg-[linear-gradient(180deg,rgba(6,8,12,1)_0%,rgba(6,8,12,1)_100%)]'
            : 'bg-[radial-gradient(90%_72%_at_72%_18%,rgba(147,197,253,0.16),transparent_56%),radial-gradient(62%_52%_at_24%_24%,rgba(244,240,232,0.08),transparent_72%),linear-gradient(160deg,rgba(21,24,27,0.96),rgba(12,14,16,1))]'
        )}
      />
      {mode === 'still' ? (
        <img
          src={TEXTUREMAP.src}
          alt=""
          aria-hidden="true"
          className={cn(
            'absolute inset-0 h-full w-full mix-blend-screen',
            isHero
              ? 'hidden'
              : 'object-contain px-5 py-7 opacity-28 sm:px-10 sm:py-12'
          )}
        />
      ) : null}
      <div
        className={cn(
          'absolute h-px -translate-y-1/2 bg-[linear-gradient(90deg,transparent,rgba(147,197,253,0.65),transparent)]',
          isHero ? 'hidden' : 'inset-x-[12%] top-1/2 opacity-70'
        )}
      />
      <div
        className={cn(
          'absolute inset-0',
          isHero
            ? 'bg-[radial-gradient(84%_70%_at_78%_54%,transparent_42%,rgba(6,8,12,0.5)_100%)]'
            : 'bg-[radial-gradient(72%_56%_at_50%_52%,transparent_40%,rgba(0,0,0,0.42)_100%)]'
        )}
      />
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
  variant = 'card',
  focus = 'center',
}: HeroFuturisticProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const rendererRef = useRef<THREE.WebGPURenderer | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const [canvasReady, setCanvasReady] = useState(false)
  const isHero = variant === 'hero'
  const camera = focus === 'right'
    ? { position: [0.02, -0.02, 2.1] as [number, number, number], fov: 38 }
    : { position: [0, 0, 1.6] as [number, number, number], fov: 32 }

  const syncCanvasElementLayout = useCallback(() => {
    const canvas = rendererRef.current?.domElement as HTMLCanvasElement | undefined
    if (!canvas) {
      return
    }

    canvas.setAttribute('data-webgpu-canvas', isHero ? 'hero' : 'card')
    canvas.style.position = 'absolute'
    canvas.style.inset = '0'
    canvas.style.width = '100%'
    canvas.style.height = '100%'
    canvas.style.display = 'block'
    canvas.style.backgroundColor = 'transparent'
    canvas.style.border = '0'
    canvas.style.outline = 'none'
    canvas.style.borderRadius = '0'
    canvas.style.pointerEvents = isHero ? 'none' : 'auto'
  }, [isHero])

  const syncRendererSize = useCallback(() => {
    const node = containerRef.current
    const renderer = rendererRef.current
    const cameraInstance = cameraRef.current
    if (!node || !renderer || !cameraInstance) {
      return
    }

    syncCanvasElementLayout()

    const rect = node.getBoundingClientRect()
    const width = Math.max(1, Math.round(rect.width))
    const height = Math.max(1, Math.round(rect.height))
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)

    renderer.setPixelRatio(pixelRatio)
    renderer.setSize(width, height, false)
    cameraInstance.aspect = width / height
    cameraInstance.updateProjectionMatrix()
  }, [syncCanvasElementLayout])

  useEffect(() => {
    const node = containerRef.current
    if (!node) {
      return
    }

    const syncCanvasReadiness = () => {
      const rect = node.getBoundingClientRect()
      const sized = rect.width >= 16 && rect.height >= 16
      setCanvasReady(sized)
      if (sized) {
        syncRendererSize()
      }
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
  }, [syncRendererSize])

  return (
    <div
      ref={containerRef}
      data-webgpu-layer={isHero ? 'hero' : 'card'}
      className={cn(
        'relative isolate',
        isHero
          ? 'h-full w-full overflow-visible'
          : 'min-h-[260px] rounded-[2rem] border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] shadow-[0_24px_80px_rgba(0,0,0,0.38)] sm:min-h-[360px]',
        className
      )}
    >
      <HeroBaseLayer mode={fallbackMode} variant={variant} focus={focus} />
      {canvasReady && (
        <WebGPUErrorBoundary fallback={<HeroFallback mode={fallbackMode} variant={variant} focus={focus} />}>
          <Canvas
            flat
            frameloop="always"
            dpr={[1, 1.5]}
            className="absolute inset-0 z-10"
            camera={camera}
            onCreated={(state) => {
              rendererRef.current = state.gl as unknown as THREE.WebGPURenderer
              cameraRef.current = state.camera as unknown as THREE.PerspectiveCamera
              syncCanvasElementLayout()
              syncRendererSize()
            }}
            gl={async (props) => {
              const renderer = new THREE.WebGPURenderer({ ...props, antialias: true } as any)
              await renderer.init()
              return renderer
            }}
          >
            <Suspense fallback={null}>
              <PostProcessing animated={true} scanEnabled={!isHero} />
              <Scene animated={true} interactive={interactive} focus={focus} />
            </Suspense>
          </Canvas>
        </WebGPUErrorBoundary>
      )}
      {!isHero && <div className="pointer-events-none absolute inset-0 rounded-[2rem] border border-white/5" />}
      {!isHero && <div className="pointer-events-none absolute inset-x-8 bottom-8 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.16),transparent)]" />}
    </div>
  )
}

export default HeroFuturistic
