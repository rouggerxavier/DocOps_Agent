# ADR-001: Hotspot Tour — biblioteca vs. implementação custom

**Status:** Decidido  
**Data:** 2026-04-24  
**Autores:** Rougger + Claude

## Contexto

A Fase 6 requer um tour guiado por tooltips sequenciais ("hotspot tour") para 3 seções críticas: `ingest`, `chat` e `artifacts`. Cada seção tem 3–4 hotspots que apontam para elementos via `data-tour-id`.

Candidatos avaliados:

| Critério | react-joyride | Implementação custom |
|---|---|---|
| Tamanho (min+gz) | ~30 KB | ~3 KB |
| Dependência nova | Sim | Não |
| A11y pronta | Sim (ARIA completo) | Manual (foco + ESC) |
| Estilo | Overrides de CSS | CSS vars nativas do app |
| Spotlight | Box-shadow nativo | Box-shadow custom |
| Posicionamento | Automático (Popper.js) | Manual (getBoundingClientRect) |
| Manutenção | Biblioteca externa | Nossa |
| Flexibilidade visual | Limitada (override) | Total |

## Decisão

**Implementação custom** (~120 linhas).

## Justificativa

1. O app já usa framer-motion para animações — o toolkit de animação está disponível sem custo extra.
2. O design system usa CSS custom properties (`--ui-*`). Sobrescrever estilos do react-joyride seria mais trabalhoso do que escrever do zero.
3. Apenas 3 seções / 3–4 hotspots cada — a complexidade de posicionamento é baixa e gerenciável com `getBoundingClientRect`.
4. Evita uma dependência de ~30 KB para uma feature que pode ser desabilitada por feature flag.
5. Se a necessidade crescer (>10 seções, posicionamento muito complexo), reavaliamos react-joyride no v2.

## Consequências

- Precisamos manter a lógica de posicionamento. Testada manualmente em viewport estreito e largo.
- A11y implementada manualmente: foco no tooltip ao abrir, ESC fecha, tab-order correto.
- Elementos fora da viewport causam scroll suave antes de calcular o rect.
