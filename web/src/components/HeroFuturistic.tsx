/**
 * Componente Hero Futurista 3D com WebGPU
 * 
 * Características:
 * - Animação 3D interativa com Three.js WebGPU
 * - Efeito de bloom e scan line
 * - Texto animado palavra por palavra
 * - Responsivo e otimizado
 * 
 * Dependências:
 * - @react-three/fiber
 * - @react-three/drei
 * - three (com WebGPU)
 */

import { Canvas, extend, useFrame, useThree } from '@react-three/fiber';
import { useAspect, useTexture } from '@react-three/drei';
import { useMemo, useRef, useState, useEffect } from 'react';
import * as THREE from 'three/webgpu';
import { bloom } from 'three/examples/jsm/tsl/display/BloomNode.js';
import { Mesh } from 'three';

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
  pass,
  mix,
  add
} from 'three/tsl';

// URLs das texturas (hospedadas externamente)
const TEXTUREMAP = { src: 'https://i.postimg.cc/XYwvXN8D/img-4.png' };
const DEPTHMAP = { src: 'https://i.postimg.cc/2SHKQh2q/raw-4.webp' };

extend(THREE as any);

/**
 * Componente de Pós-Processamento
 * Aplica bloom e efeito de scan line
 */
const PostProcessing = ({
  strength = 1,
  threshold = 1,
  fullScreenEffect = true,
}: {
  strength?: number;
  threshold?: number;
  fullScreenEffect?: boolean;
}) => {
  const { gl, scene, camera } = useThree();
  const progressRef = useRef({ value: 0 });

  const render = useMemo(() => {
    const postProcessing = new THREE.PostProcessing(gl as any);
    const scenePass = pass(scene, camera);
    const scenePassColor = scenePass.getTextureNode('output');
    const bloomPass = bloom(scenePassColor, strength, 0.5, threshold);

    // Criar uniforme para controlar o progresso do scan
    const uScanProgress = uniform(0);
    progressRef.current = uScanProgress;

    // Criar efeito de linha vermelha que segue o scan
    const scanPos = float(uScanProgress.value);
    const uvY = uv().y as any;
    const scanWidth = float(0.05);
    const scanLine = smoothstep(0, scanWidth, abs(uvY.sub(scanPos) as any));
    const redOverlay = vec3(1, 0, 0).mul(oneMinus(scanLine)).mul(0.4);

    // Misturar cena original com overlay vermelho
    const withScanEffect = mix(
      scenePassColor,
      add(scenePassColor, redOverlay),
      fullScreenEffect ? smoothstep(0.9, 1.0, oneMinus(scanLine)) : 1.0
    );

    // Adicionar bloom após o efeito de scan
    const final = withScanEffect.add(bloomPass);

    postProcessing.outputNode = final;

    return postProcessing;
  }, [camera, gl, scene, strength, threshold, fullScreenEffect]);

  useFrame(({ clock }) => {
    // Animar a linha de scan de cima para baixo
    progressRef.current.value = (Math.sin(clock.getElapsedTime() * 0.5) * 0.5 + 0.5);
    render.renderAsync();
  }, 1);

  return null;
};

const WIDTH = 300;
const HEIGHT = 300;

/**
 * Componente de Cena 3D
 * Renderiza a geometria com shader customizado
 */
const Scene = () => {
  const [rawMap, depthMap] = useTexture([TEXTUREMAP.src, DEPTHMAP.src]);

  const meshRef = useRef<Mesh>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Mostrar imagem após texturas serem carregadas
    if (rawMap && depthMap) {
      setVisible(true);
    }
  }, [rawMap, depthMap]);

  const { material, uniforms } = useMemo(() => {
    const uPointer = uniform(new THREE.Vector2(0));
    const uProgress = uniform(0);

    const strength = 0.01;

    const tDepthMap = texture(depthMap);

    const tMap = texture(
      rawMap,
      uv().add(tDepthMap.r.mul(uPointer as any).mul(strength)) as any
    );

    const aspect = float(WIDTH).div(HEIGHT);
    const tUv = vec2(uv().x.mul(aspect) as any, uv().y as any);

    const tiling = vec2(120.0);
    const tiledUv = mod(tUv.mul(tiling), 2.0).sub(1.0);

    const brightness = mx_cell_noise_float(tUv.mul(tiling).div(2));

    const dist = float(tiledUv.length());
    const dot = float(smoothstep(0.5, 0.49, dist)).mul(brightness);

    const depth = tDepthMap;

    const flow = oneMinus(smoothstep(0, 0.02, abs(depth.sub(uProgress) as any)) as any);

    const mask = dot.mul(flow as any).mul(vec3(10, 0, 0));

    const final = blendScreen(tMap, mask);

    const material = new THREE.MeshBasicNodeMaterial({
      colorNode: final,
      transparent: true,
      opacity: 0,
    });

    return {
      material,
      uniforms: {
        uPointer,
        uProgress,
      },
    };
  }, [rawMap, depthMap]);

  const [w, h] = useAspect(WIDTH, HEIGHT);

  // Animar o progresso (efeito de profundidade)
  useFrame(({ clock }) => {
    uniforms.uProgress.value = (Math.sin(clock.getElapsedTime() * 0.5) * 0.5 + 0.5);
    // Fade suave na entrada
    if (meshRef.current && 'material' in meshRef.current && meshRef.current.material) {
      const mat = meshRef.current.material as any;
      if ('opacity' in mat) {
        mat.opacity = THREE.MathUtils.lerp(
          mat.opacity,
          visible ? 1 : 0,
          0.07
        );
      }
    }
  });

  // Rastrear movimento do mouse
  useFrame(({ pointer }) => {
    uniforms.uPointer.value = pointer;
  });

  const scaleFactor = 0.40;
  return (
    <mesh ref={meshRef} scale={[w * scaleFactor, h * scaleFactor, 1]} material={material}>
      <planeGeometry />
    </mesh>
  );
};

/**
 * Componente Principal - Hero Futurista
 * 
 * Props (opcionais):
 * - titleLine1: string - Primeira linha do título
 * - titleLine2: string - Segunda linha do título
 * - subtitle: string - Subtítulo
 * - onExploreClick: () => void - Callback ao clicar em "Rolar para explorar"
 */
export const HeroFuturistic = ({
  titleLine1 = 'respostas confiáveis para cada',
  titleLine2 = 'um dos seus documentos',
  subtitle = 'Análise inteligente de documentos com inteligência artificial.',
  onExploreClick,
}: {
  titleLine1?: string;
  titleLine2?: string;
  subtitle?: string;
  onExploreClick?: () => void;
} = {}) => {
  const titleWords = (titleLine1 + ' ' + titleLine2).split(' ');
  const [visibleWords, setVisibleWords] = useState(0);
  const [subtitleVisible, setSubtitleVisible] = useState(false);
  const [delays, setDelays] = useState<number[]>([]);
  const [subtitleDelay, setSubtitleDelay] = useState(0);

  useEffect(() => {
    // Gerar delays aleatórios para efeito de glitch (apenas no cliente)
    setDelays(titleWords.map(() => Math.random() * 0.07));
    setSubtitleDelay(Math.random() * 0.1);
  }, [titleWords.length]);

  // Animar entrada das palavras do título
  useEffect(() => {
    if (visibleWords < titleWords.length) {
      const timeout = setTimeout(() => setVisibleWords(visibleWords + 1), 600);
      return () => clearTimeout(timeout);
    } else {
      const timeout = setTimeout(() => setSubtitleVisible(true), 800);
      return () => clearTimeout(timeout);
    }
  }, [visibleWords, titleWords.length]);

  const handleExploreClick = () => {
    if (onExploreClick) {
      onExploreClick();
    } else {
      // Comportamento padrão: scroll para a próxima seção
      const nextSection = document.querySelector('main > section:nth-child(2)');
      if (nextSection) {
        nextSection.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  return (
    <div className="h-svh relative overflow-hidden">
      <style>{`
        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes fade-in-subtitle {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes explore-pulse {
          0%, 100% {
            opacity: 1;
          }
          50% {
            opacity: 0.5;
          }
        }

        .fade-in {
          animation: fade-in 0.8s ease-out forwards;
        }

        .fade-in-subtitle {
          animation: fade-in-subtitle 0.8s ease-out forwards;
        }

        .explore-btn {
          position: absolute;
          bottom: 40px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          background: transparent;
          border: 2px solid white;
          color: white;
          padding: 12px 20px;
          border-radius: 50px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          z-index: 50;
          animation: explore-pulse 2s ease-in-out infinite;
          animation-delay: 2.2s;
          opacity: 0;
          animation-fill-mode: forwards;
          transition: all 0.3s ease;
        }

        .explore-btn:hover {
          background: rgba(255, 255, 255, 0.1);
          transform: translateX(-50%) translateY(-5px);
        }

        .explore-arrow {
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .arrow-svg {
          animation: bounce 2s ease-in-out infinite;
          animation-delay: 2.2s;
        }

        @keyframes bounce {
          0%, 100% {
            transform: translateY(0);
          }
          50% {
            transform: translateY(8px);
          }
        }
      `}</style>

      {/* Camada de texto sobreposta */}
      <div className="h-svh absolute z-60 pointer-events-none px-10 flex justify-center flex-col w-full items-center">
        {/* Título em duas linhas */}
        <div className="text-3xl md:text-5xl xl:text-6xl 2xl:text-7xl font-extrabold">
          <div className="flex flex-col items-center">
            {/* Primeira linha do título */}
            <div className="flex space-x-2 lg:space-x-6 overflow-hidden text-white justify-center">
              {titleLine1.split(' ').map((word, index) => (
                <div
                  key={index}
                  className={index < visibleWords ? 'fade-in' : ''}
                  style={{
                    animationDelay: `${index * 0.13 + (delays[index] || 0)}s`,
                    opacity: index < visibleWords ? undefined : 0,
                  }}
                >
                  {word}
                </div>
              ))}
            </div>
            {/* Segunda linha do título */}
            <div className="flex space-x-2 lg:space-x-6 overflow-hidden text-white justify-center">
              {titleLine2.split(' ').map((word, index) => {
                const line1WordCount = titleLine1.split(' ').length;
                return (
                  <div
                    key={index}
                    className={index + line1WordCount < visibleWords ? 'fade-in' : ''}
                    style={{
                      animationDelay: `${(index + line1WordCount) * 0.13 + (delays[index + line1WordCount] || 0)}s`,
                      opacity: index + line1WordCount < visibleWords ? undefined : 0,
                    }}
                  >
                    {word}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Subtítulo */}
        <div className="text-xs md:text-xl xl:text-2xl 2xl:text-3xl mt-2 overflow-hidden text-white font-bold">
          <div
            className={subtitleVisible ? 'fade-in-subtitle' : ''}
            style={{
              animationDelay: `${titleWords.length * 0.13 + 0.2 + subtitleDelay}s`,
              opacity: subtitleVisible ? undefined : 0,
            }}
          >
            {subtitle}
          </div>
        </div>
      </div>

      {/* Botão "Rolar para explorar" */}
      <button
        className="explore-btn pointer-events-auto"
        style={{ animationDelay: '2.2s' }}
        onClick={handleExploreClick}
        aria-label="Rolar para explorar"
      >
        Rolar para explorar
        <span className="explore-arrow">
          <svg
            width="22"
            height="22"
            viewBox="0 0 22 22"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="arrow-svg"
          >
            <path d="M11 5V17" stroke="white" strokeWidth="2" strokeLinecap="round" />
            <path d="M6 12L11 17L16 12" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {/* Canvas Three.js com WebGPU */}
      <Canvas
        flat
        gl={async (props) => {
          const renderer = new THREE.WebGPURenderer(props as any);
          await renderer.init();
          return renderer;
        }}
      >
        <PostProcessing fullScreenEffect={true} />
        <Scene />
      </Canvas>
    </div>
  );
};

export default HeroFuturistic;
