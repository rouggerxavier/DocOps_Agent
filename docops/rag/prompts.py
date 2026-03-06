"""Prompt templates for the DocOps Agent."""

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

# ──────────────────────────────────────────────────────────────────────────────
# System prompt (injected into every chat interaction)
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
Você é o DocOps Agent, um assistente especializado em análise e operação sobre documentos.

Regras fundamentais:
1. Responda SEMPRE com base nos trechos de documentos fornecidos no contexto.
2. NUNCA invente fatos, dados, números ou referências que não estejam no contexto.
3. Se o contexto não contiver informação suficiente, diga claramente que não encontrou
   nos documentos e sugira o que o usuário pode fazer (ex.: adicionar mais documentos,
   reformular a pergunta).
4. Ao fazer afirmações factuais, cite a fonte no formato [Fonte N].
5. Ao final de toda resposta, inclua a seção "Fontes:" listando cada fonte usada.
6. Seja objetivo, claro e estruturado. Use markdown quando ajudar a leitura.
7. Se a intenção for gerar um artefato (resumo, plano de estudos, checklist),
   estruture-o em seções bem definidas.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Intent classification prompt
# ──────────────────────────────────────────────────────────────────────────────
INTENT_CLASSIFICATION_PROMPT = """\
Classifique a intenção da mensagem do usuário em UMA das seguintes categorias:
- qa: pergunta e resposta simples sobre o conteúdo dos documentos
- summary: pedido de resumo de um ou mais documentos
- comparison: pedido de comparação entre dois ou mais documentos
- checklist: pedido de checklist ou lista de verificação
- study_plan: pedido de plano de estudo ou roteiro de aprendizado
- artifact: pedido de geração de artefato (ex.: README, relatório, documento)
- other: qualquer outra intenção

Responda SOMENTE com a palavra da categoria, sem explicação.

Mensagem do usuário: {query}
"""

# ──────────────────────────────────────────────────────────────────────────────
# RAG synthesis prompt
# ──────────────────────────────────────────────────────────────────────────────
RAG_SYNTHESIS_PROMPT = """\
Você é o DocOps Agent. Use os trechos de documentos abaixo para responder à pergunta do usuário.

TRECHOS DE DOCUMENTOS:
{context}

PERGUNTA DO USUÁRIO:
{query}

INSTRUÇÕES:
- Responda com base EXCLUSIVAMENTE nos trechos fornecidos.
- Cite as fontes inline usando [Fonte 1], [Fonte 2], etc. (correspondendo à lista de trechos).
- Se a informação não estiver nos trechos, diga: "Não encontrei informação suficiente nos
  documentos indexados para responder isso com segurança."
- Estruture a resposta claramente com markdown se necessário.
- Ao final, inclua a seção "Fontes:" com os detalhes de cada fonte citada.

FORMATO DE RESPOSTA:
**Resposta:**
[sua resposta aqui com citações inline como [Fonte 1]]

**Fontes:**
[lista formatada de fontes]
"""

# ──────────────────────────────────────────────────────────────────────────────
# Summary prompts  (brief / deep)
# ──────────────────────────────────────────────────────────────────────────────

# Alias mantido para retrocompatibilidade.
SUMMARY_PROMPT = """\
Com base nos trechos do documento abaixo, crie um resumo estruturado por tópicos.

TRECHOS:
{context}

DOCUMENTO: {doc_name}

Organize o resumo com:
1. **Visão Geral**: 2-3 frases sobre o conteúdo principal
2. **Tópicos Principais**: lista dos temas abordados
3. **Pontos Chave**: bullet points com as informações mais importantes
4. **Conclusão**: síntese final

Cite as fontes relevantes usando [Fonte N].

**Fontes:**
[lista de fontes usadas]
"""

BRIEF_SUMMARY_PROMPT = """\
Você é um assistente especializado em síntese de documentos técnicos e acadêmicos.
Leia com atenção os trechos do documento abaixo e produza um **resumo breve e direto**.

TRECHOS DO DOCUMENTO ({doc_name}):
{context}

INSTRUÇÕES:
- O resumo deve ter no máximo 300 palavras.
- Capture a essência do documento: tema central, objetivo e conclusão principal.
- Use linguagem clara e objetiva, sem jargões desnecessários.
- Cite apenas as fontes mais relevantes no formato [Fonte N].
- Não inclua subseções longas — prefira parágrafos curtos e fluidos.
- Elimine detalhes secundários, exemplos extensos e repetições.
- Ao final, inclua uma única linha "**Palavras-chave:**" com 4-6 termos centrais.

FORMATO DE SAÍDA:
**Resumo Breve — {doc_name}**

[2-3 parágrafos concisos cobrindo: o que é o documento, o que ele ensina/propõe, e a conclusão principal]

**Palavras-chave:** [termo1, termo2, ...]

**Fontes:**
[apenas as fontes mais relevantes citadas acima]
"""

DEEP_SUMMARY_PROMPT = """\
Você é um especialista em análise documental. Sua tarefa é produzir um \
**resumo aprofundado e detalhado** do documento abaixo, cobrindo **todo o seu conteúdo** \
de forma organizada, precisa e rica em detalhes técnicos.

TRECHOS DO DOCUMENTO ({doc_name}):
{context}

INSTRUÇÕES GERAIS:
- Leia e processe TODOS os trechos fornecidos — nenhuma parte do documento deve ser ignorada.
- Estruture o resumo em seções que reflitam a organização real do documento.
- Para cada seção, detalhe: conceitos introduzidos, definições formais, exemplos, \
  algoritmos, fórmulas, resultados e conclusões parciais.
- Seja específico: cite números, fórmulas, nomes de algoritmos e termos técnicos exatos \
  quando presentes no documento.
- Cite as fontes inline usando [Fonte N] sempre que fizer uma afirmação baseada num trecho.
- Não omita seções, mesmo que pareçam introdutórias ou de recapitulação — elas podem \
  conter definições fundamentais.
- Não invente informações. Se um trecho estiver incompleto, indique brevemente \
  que "o documento não detalha este ponto nos trechos disponíveis".
- Ao final, inclua uma seção de Síntese Geral conectando todos os temas.

FORMATO DE SAÍDA:
# Resumo Aprofundado — {doc_name}

## 1. Visão Geral do Documento
[Objetivo, público-alvo, estrutura geral e contribuição principal do documento]

## 2. [Título da Seção/Tópico 1 do documento]
[Detalhamento completo: conceitos, definições, exemplos, fórmulas, resultados — com citações [Fonte N]]

## 3. [Título da Seção/Tópico 2 do documento]
[idem — continue para quantas seções o documento tiver]

(adicione quantas seções forem necessárias para cobrir TODO o documento)

## N. Síntese Geral
[Conecte todos os temas abordados. Quais são as ideias centrais? O que o documento conclui? Quais limitações ou trabalhos futuros são mencionados?]

**Fontes:**
[lista completa de todas as fontes citadas]
"""

# ──────────────────────────────────────────────────────────────────────────────
# Comparison prompt
# ──────────────────────────────────────────────────────────────────────────────
COMPARISON_PROMPT = """\
Compare os dois documentos com base nos trechos fornecidos.

TRECHOS DO DOCUMENTO 1 ({doc1}):
{context1}

TRECHOS DO DOCUMENTO 2 ({doc2}):
{context2}

Crie uma comparação estruturada:
1. **Semelhanças**: o que os documentos têm em comum
2. **Diferenças**: principais diferenças de conteúdo, abordagem ou escopo
3. **Tabela Comparativa** (use markdown):
   | Aspecto | {doc1} | {doc2} |
   |---------|--------|--------|
4. **Conclusão**: qual documento cobre melhor cada aspecto

Cite as fontes usando [Doc1-Fonte N] e [Doc2-Fonte N].

**Fontes:**
[lista de fontes]
"""

# ──────────────────────────────────────────────────────────────────────────────
# Study plan prompt
# ──────────────────────────────────────────────────────────────────────────────
STUDY_PLAN_PROMPT = """\
Com base nos trechos dos documentos, crie um plano de estudo detalhado sobre o tópico: {topic}

TRECHOS DOS DOCUMENTOS:
{context}

Estruture o plano de estudo com:
1. **Objetivo de Aprendizado**: o que o estudante dominará ao final
2. **Pré-requisitos**: conhecimentos necessários
3. **Módulos de Estudo** (divida em semanas ou sessões):
   - Módulo N: [título]
     - Conteúdo: ...
     - Exercícios: ...
     - Recursos: [referência aos documentos]
4. **Exercícios Práticos**: lista de atividades concretas
5. **Autoavaliação**: perguntas para verificar o aprendizado
6. **Referências**: documentos usados [Fonte N]

**Fontes:**
[lista de fontes]
"""

# Repair prompt: used when semantic grounding support is below threshold.
GROUNDING_REPAIR_PROMPT = """\
Reescreva a resposta abaixo usando SOMENTE informacoes suportadas pelos trechos.

PERGUNTA:
{query}

RESPOSTA ORIGINAL:
{answer}

CLAIMS PROBLEMATICAS (sem suporte suficiente):
{unsupported_claims}

TRECHOS DISPONIVEIS:
{context}

REGRAS:
- Mantenha apenas fatos suportados pelos trechos.
- Sempre cite no formato [Fonte N] para afirmacoes factuais.
- Se nao houver suporte suficiente para uma parte, remova essa parte.
- Se nada puder ser afirmado com seguranca, responda:
  "Nao encontrei informacao suficiente nos documentos para responder com seguranca."
- Inclua ao final a secao "**Fontes:**".
"""
