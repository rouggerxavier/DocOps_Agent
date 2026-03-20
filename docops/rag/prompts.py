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

Regras de clarificação — MUITO IMPORTANTE:
8. Se a mensagem do usuário for ambígua, incompleta ou puder ser interpretada de mais
   de uma forma, NÃO assuma nem invente uma interpretação. Pergunte de volta antes de agir.
   Exemplos: "Você quer que eu resuma o documento X ou o Y?", "Prefere um checklist ou
   um plano de estudos?", "Qual documento você quer comparar com qual?"
9. Se você não tiver certeza do que está sendo pedido, seja direto: "Não entendi
   completamente o que você quer. Você quer que eu [opção A] ou [opção B]?"
10. Perguntas de clarificação devem ser curtas, diretas e apresentar opções concretas
    sempre que possível. Não faça múltiplas perguntas de uma vez — foque na dúvida principal.
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
- clarification_needed: mensagem ambígua, incompleta ou que requer esclarecimento antes de agir
- other: qualquer outra intenção que não se encaixa nas categorias acima

Use "clarification_needed" quando a mensagem puder ser interpretada de múltiplas formas
e uma pergunta de volta seria necessária para agir corretamente.

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
- Responda diretamente: sobre o que é o documento e o que ele ensina ou propõe.
- Capture o tema central, o objetivo e a conclusão principal em texto fluido.
- Prefira parágrafos curtos e coesos. Evite listas, subseções e enumerações.
- Cite apenas as 2–3 fontes mais relevantes no formato [Fonte N]. Não force citações.
- Elimine detalhes secundários, exemplos extensos e repetições.
- EVITE verbos mecânicos repetitivos: "apresenta", "aborda", "introduz", "trata de", "discute".
  Use "explica", "demonstra", "define", "conclui", "relaciona" quando precisar de um verbo de síntese.
- Ao final, inclua uma única linha "**Palavras-chave:**" com 4–6 termos centrais.

FORMATO DE SAÍDA:
**Resumo Breve — {doc_name}**

[2–3 parágrafos concisos e fluidos]

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
- Não invente informações. Se um ponto realmente não aparecer nas fontes, \
  indique a limitação de forma breve. Antes disso, verifique se o tema não \
  está coberto em outros trechos do documento.
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

# ──────────────────────────────────────────────────────────────────────────────
# Deep summary pipeline prompts (multi-step: partial → consolidate → final)
# ──────────────────────────────────────────────────────────────────────────────

DEEP_SUMMARY_PARTIAL_PROMPT = """\
Você é um especialista em análise documental.
Está processando a seção "{section_label}" do documento "{doc_name}".

TRECHOS DESTA SEÇÃO:
{context}

TAREFA:
Produza um resumo analítico desta seção (150–250 palavras).

INSTRUÇÕES:
- Identifique o tema central desta seção e o que ela contribui para o documento como um todo.
- Extraia conceitos, definições e termos técnicos importantes com precisão.
- Registre fórmulas, algoritmos ou procedimentos usando notação textual legível quando
  símbolos estiverem corrompidos ou ambíguos (ex.: "somatório de i=1 a n de f(i)").
- Mencione exemplos concretos e resultados apresentados, se existirem.
- Aponte conclusões ou proposições estabelecidas nesta seção.
- Se os trechos estiverem fragmentados, incompletos ou com qualidade degradada (artefatos de PDF),
  extraia o máximo de sentido possível e sinalize brevemente: "(trecho parcialmente ilegível)".
- Seja direto: não repita o texto literalmente nem abra com frases mecânicas como
  "esta seção apresenta" ou "este trecho aborda".
- Escreva em prosa fluida e técnica — não em lista de tópicos.

RESUMO PARCIAL DA SEÇÃO "{section_label}":
"""

DEEP_SUMMARY_CONSOLIDATE_PROMPT = """\
Você recebeu resumos parciais de todas as seções do documento "{doc_name}".

RESUMOS POR SEÇÃO:
{partials_block}

TAREFA:
Produza uma VISÃO CONSOLIDADA do documento inteiro (300–500 palavras).

INSTRUÇÕES:
- Identifique o objetivo central e a motivação do documento.
- Descreva a linha lógica do material: como as seções se encadeiam e constroem
  umas sobre as outras.
- Determine quais temas e conceitos são fundamentais e quais são secundários.
- Identifique conexões explícitas entre tópicos: dependências, contrastes, extensões.
- Destaque definições ou conceitos que aparecem em múltiplas seções.
- Seja analítico: explique o "porquê" da organização do documento, não apenas liste o "quê".
- Evite verbos mecânicos repetitivos como "apresenta", "aborda", "introduz".

VISÃO CONSOLIDADA:
"""

DEEP_SUMMARY_FINAL_PROMPT = """\
Você é um especialista em síntese documental e elaboração de material de estudo.
Sua tarefa é produzir o RESUMO APROFUNDADO FINAL do documento "{doc_name}".

Você dispõe de:
1. Uma visão consolidada analítica do documento.
2. Resumos parciais de cada seção.
3. Trechos de referência para citações inline.

VISÃO CONSOLIDADA:
{consolidated}

RESUMOS PARCIAIS DAS SEÇÕES:
{partials_block}

TRECHOS DE REFERÊNCIA (para citações [Fonte N]):
{context_sample}

PERFIL DE COBERTURA DETECTADO (gerado automaticamente a partir do documento):
{coverage_contract}

TAREFA:
Escreva um resumo aprofundado completo, estruturado e útil como material de estudo.

INSTRUÇÕES OBRIGATÓRIAS:
- Identifique e explique o OBJETIVO CENTRAL do documento: o que ele propõe, resolve ou ensina.
- Explique a LINHA LÓGICA do material: como os conceitos se encadeiam do início ao fim.
- Conecte os tópicos entre si — mostre como A fundamenta B, como C contrasta com D.
- Distinga o que é CENTRAL do que é secundário ou ilustrativo.
- Detalhe CONCEITOS, DEFINIÇÕES e TERMOS TÉCNICOS com clareza — não apenas cite os nomes.
- AGRUPE conceitos relacionados na mesma explicação. Não transforme o resumo em glossário.
- Em vez de empilhar mini-definições isoladas, explique por que cada conceito importa
  dentro do raciocínio do documento.
- Para FÓRMULAS e PROCEDIMENTOS: use notação textual legível quando necessário.
  Exemplo: "Gini(t) = 1 menos somatório de p_i ao quadrado" em vez de símbolos que
  possam aparecer corrompidos.
- Mencione EXEMPLOS concretos usados no documento — eles ajudam a compreender os conceitos.
- Escreva como MATERIAL ÚTIL DE ESTUDO: quem ler este resumo deve entender o documento
  sem precisar ler o original inteiro.
- Mantenha FIDELIDADE ao documento: não invente fatos nem extrapole além do conteúdo.
- Cumpra o PERFIL DE COBERTURA DETECTADO:
  cada faceta marcada como "obrigatória" deve aparecer de forma explícita e com citação.
- Para fórmulas/notação: preserve a forma técnica da fonte quando houver risco de ambiguidade
  (ex.: cardinalidade |T|, α_eff, log2). Não simplifique símbolos que mudem o significado.
- Use LINGUAGEM CLARA e técnica, sem jargão desnecessário.
- Não use linguagem promocional ou vaga: evite termos como "guia completo", "abrangente",
  "valioso", "adequado para estudantes e profissionais" se isso não estiver explicitamente
  sustentado no material.
- Não infira público-alvo, intenção pedagógica, completude ou qualidade do documento sem
  evidência explícita. Se não houver evidência clara, escreva "não explicitado no material".
- Evite sínteses interpretativas amplas (ex.: "tratado", "visão robusta", "superioridade de abordagem",
  "otimizado para cenários reais") quando isso não estiver literal e explicitamente sustentado
  pelos trechos citados. Prefira formulação factual e local.
- EVITE verbos mecânicos repetitivos: "apresenta", "aborda", "introduz", "discute", "trata de".
  Prefira: "explica", "demonstra", "define", "conclui", "relaciona", "contrasta", "fundamenta".
- Prefira PARÁGRAFOS EXPLICATIVOS; use listas somente na seção de tópicos, quando ajudar a leitura.
- Estrutura-alvo: use EXATAMENTE 5 seções `##` seguindo o modelo abaixo.
- Use 4 seções `##` apenas quando não houver conteúdo técnico suficiente para a seção de métodos/fórmulas.
- Não crie novas seções `##` fora do modelo. Se precisar detalhar, use parágrafos dentro das seções existentes.
- Limite absoluto: NO MÁXIMO 6 seções de nível `##`.
- OMITA seções vazias ou fracas. Não crie uma seção só para repetir nomes de tópicos.
- Não inclua uma seção "Fontes:" no texto final; as fontes serão anexadas separadamente.
- O resultado final deve soar como uma explicação integrada para estudo, não como índice comentado.
- Ao fazer afirmações factuais baseadas nos trechos de referência, cite [Fonte N].
- DISTRIBUA citações ao longo de TODAS as seções do resumo. Evite concentrar citações em
  apenas 2–3 fontes. Quando houver suporte real em diferentes trechos de referência, prefira
  citar fontes variadas ([Fonte 1], [Fonte 3], [Fonte 5], etc.) para cobrir partes distintas
  do documento. NÃO invente citações — cite apenas quando houver suporte factual.
- Use no máximo 1–2 citações por parágrafo (ou por item de lista) para não poluir leitura.
- Nunca escreva linhas órfãs como "Fonte 9", "[Fonte 3]" isolado, ou listas de mapeamento
  de fonte dentro do corpo.
- A conclusão deve ser substantiva: 4–7 frases integrando os principais blocos do documento.
- O resultado final deve ser COESO: um texto que flui, não uma lista de tópicos soltos.
- FIDELIDADE TÉCNICA OBRIGATÓRIA — não extrapole além do material citado:
  Para afirmações QUANTITATIVAS (percentuais, magnitudes, razões, contagens), COMPARATIVAS
  ("X é melhor que Y", "A diferencia-se de B por...", "em contraste com", "ao contrário de")
  e MATEMÁTICAS (equações, variáveis, notação formal, fórmulas): cite [Fonte N]
  OBRIGATORIAMENTE e use APENAS os valores/relações EXATOS que aparecem literalmente
  na fonte citada. Não interpole, não generalize, não derive valores por inferência.
  Quando a fonte não detalhar um valor ou relação, afirme a limitação de forma
  precisa e apenas se realmente não houver suporte em outras fontes do contexto
  — nunca complete por dedução própria.
- NÃO use fontes de baixo teor (Sumário, Índice, Conteúdo, Table of Contents) para
  sustentar detalhes técnicos, quantitativos, comparativos ou matemáticos.
  Essas fontes só podem sustentar escopo/roteiro do documento.

FORMATO DE SAÍDA:
# Resumo Aprofundado — {doc_name}

## Visão Geral
[Tema central, escopo e objetivo do documento em 1–2 parágrafos fluidos.]

## Encadeamento e Principais Tópicos
[Abra com uma frase-guia ("A seguir, os principais tópicos abordados:") e use lista
curta por tópico com explicação útil (não só nome da seção). Cubra o documento inteiro.]

## Conceitos e Métodos Fundamentais
[Conecte conceitos-chave, fórmulas e procedimentos com linguagem clara e didática.
Quando útil, use notação textual legível.]

## Aplicações e Variações
[Mostre exemplos, cenários de uso, extensões (ex.: random forest, regressão) e relação
com os conceitos centrais.]

## Síntese Final
[Conclusão de verdade (4–7 frases), integrando os tópicos e o que o documento efetivamente
entrega em termos de entendimento técnico.]
"""

DEEP_SUMMARY_STYLE_POLISH_PROMPT = """\
Você está revisando o rascunho final de um resumo aprofundado do documento "{doc_name}".

RASCUNHO ATUAL:
{draft}

TAREFA:
Reescreva o texto para deixá-lo mais coeso, pedagógico e útil como material de estudo,
sem alterar o conteúdo factual sustentado pelas citações existentes.

REGRAS OBRIGATÓRIAS:
- Preserve as citações inline já existentes no formato [Fonte N]. Não invente novas.
- Mantenha no máximo 6 seções `##`.
- Una seções excessivamente fragmentadas ou enciclopédicas quando isso melhorar a fluidez.
- Substitua sequências de mini-definições por explicações integradas em prosa.
- Deixe explícito o encadeamento lógico do documento: o que fundamenta, deriva, contrasta ou amplia.
- Destaque apenas fórmulas, definições e exemplos realmente importantes.
- Prefira parágrafos explicativos. Não transforme a saída em lista ou glossário.
- Evite verbos mecânicos repetitivos como "apresenta", "aborda", "introduz", "discute".
- Remova frases promocionais, genéricas ou não sustentadas pelo texto-base.
- Se houver afirmação sobre público-alvo, escopo "completo" ou intenção do autor sem base
  explícita, substitua por formulação neutra ou "não explicitado no material".
- Use notação matemática textual legível quando símbolos parecerem quebrados.
- Não inclua a seção "Fontes:"; ela será anexada separadamente.

RETORNE APENAS A VERSÃO FINAL POLIDA.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Repair prompt: used when semantic grounding support is below threshold.
DEEP_SUMMARY_RESYNTHESIS_PROMPT = """\
Voce esta reescrevendo um resumo aprofundado que falhou em alguns criterios de qualidade.
Documento: "{doc_name}"

DIAGNOSTICO DE QUALIDADE:
{quality_feedback}

LACUNAS PRIORITARIAS A CORRIGIR:
{gap_contract}

RASCUNHO ATUAL:
{draft}

VISAO CONSOLIDADA:
{consolidated}

RESUMOS PARCIAIS:
{partials_block}

TRECHOS DE REFERENCIA PARA CITACOES [Fonte N]:
{context_sample}

TAREFA:
Reescreva o resumo aprofundado inteiro para ficar coeso, fiel e util para estudo.

REGRAS OBRIGATORIAS:
- Preserve apenas afirmacoes sustentadas pelos trechos de referencia.
- Use citacoes inline [Fonte N] para afirmacoes factuais.
- Corrija explicitamente as lacunas listadas em "LACUNAS PRIORITARIAS A CORRIGIR".
- Se houver lacuna de notacao/fidelidade formal, prefira a notacao da fonte
  (por exemplo: |T| em vez de T quando a fonte representa cardinalidade).
- Distribua citacoes ao longo de TODAS as secoes do texto. Use pelo menos {min_unique_sources}
  fontes distintas quando houver suporte. Evite concentrar em 2-3 fontes — cite fontes variadas
  ([Fonte 1], [Fonte 3], [Fonte 5], etc.) para cobrir partes diferentes do documento.
- FIDELIDADE TECNICA: Para afirmacoes quantitativas (percentuais, magnitudes, razoes),
  comparativas ("X e melhor que Y", "A diferencia-se de B") e matematicas (equacoes,
  notacao formal): use APENAS valores e relacoes literalmente presentes nos trechos de
  referencia. Nao derive valores por inferencia, nao interpole, nao extrapole.
  Quando a fonte nao detalhar, registre a limitacao em vez de completar por deducao.
- Nao use fontes de baixo teor (sumario, indice, conteudo, table of contents)
  para sustentar detalhes tecnicos. Essas fontes servem apenas para escopo/roteiro.
- Estrutura-alvo: 5 secoes com titulo "##" (aceitavel: 4 a 6).
- Use este scaffold de titulos (ou variacao semantica equivalente):
  1) Visao Geral
  2) Encadeamento e Principais Topicos
  3) Conceitos e Metodos Fundamentais
  4) Aplicacoes e Variacoes
  5) Sintese Final
- Nao crie novas secoes "##" fora desse scaffold.
- Na secao de topicos, use lista curta com cobertura ampla do documento (evite itens telegráficos).
- Em cada secao, use no maximo 1-2 citacoes por paragrafo/item.
- Nao gere linhas orfas de citacao/fonte ("Fonte N", "[Fonte N]" isolado, mapping com pagina/pdf).
- Nao inclua secoes fracas, vazias, genericas ou meta-comentarios.
- Nao inclua "Fontes:" no corpo do texto final.
- Nao escreva frases de processo como "nao foi possivel reescrever" ou "as fontes tratam de".
- Evite linguagem mecanica repetitiva.
- Prefira explicacao integrada em paragrafos.
- Se nao houver evidencia para algo, remova em vez de especular.
- Evite frases conclusivas amplas e interpretativas quando os trechos só suportam descrição local.
  Prefira formulação factual, curta e ancorada na fonte.

RETORNE APENAS O RESUMO FINAL.
"""

SUMMARY_BLOCK_REPAIR_PROMPT = """\
Um bloco de um resumo aprofundado apresenta baixa sobreposição com as fontes que cita.
Sua tarefa: reescreva o bloco usando APENAS informações presentes nas fontes fornecidas.

REGRAS:
- Mantenha as referências [Fonte N] apenas quando a afirmação for diretamente sustentada.
- Remova afirmações que não estejam nas fontes.
- Preserve o escopo temático do bloco original.
- Mantenha estilo analítico e objetivo; evite repetir o texto fonte literalmente.
- Não escreva metacomentários sobre o processo (ex.: "não encontrei informações",
  "as fontes tratam de", "seria necessário fornecer documentos").
- Se algo não for suportado pelas fontes, simplesmente remova o trecho.
- Não gere linha de fontes no corpo, como: "Fontes:", "[Fonte N]" isolado,
  "Fonte N", ou "[Fonte N]: ...".
- Retorne apenas o bloco reescrito, sem comentários adicionais.

BLOCO ORIGINAL:
{block}

FONTES CITADAS:
{sources_block}

BLOCO REESCRITO:
"""

DEEP_SUMMARY_STRUCTURE_FIX_PROMPT = """\
Você está reorganizando um resumo aprofundado com problemas de estrutura.
Documento: "{doc_name}"

RASCUNHO ATUAL:
{draft}

TAREFA:
Reorganize o resumo corrigindo APENAS estrutura e coesão, sem alterar o conteúdo factual.

REGRAS OBRIGATÓRIAS:
- Preserve todas as citações inline [Fonte N] existentes — não invente novas nem remova as válidas.
- Meta de estrutura: 5 seções ## (faixa aceitável: no mínimo 4 e no máximo 6).
- Reescreva os títulos para o scaffold canônico abaixo (ou variação semântica muito próxima):
  1) Visão Geral
  2) Encadeamento e Principais Tópicos
  3) Conceitos e Métodos Fundamentais
  4) Aplicações e Variações
  5) Síntese Final
- OBRIGATÓRIO: os títulos das seções ## devem cobrir TODAS estas categorias temáticas:
  1. Objetivo/Contexto/Introdução — o que o documento propõe
  2. Estrutura/Metodologia/Organização — como o conteúdo se encadeia
  3. Conceitos/Definições/Fundamentos — termos e ideias centrais
  4. Síntese/Conclusão/Resultados — fechamento e contribuições
- Os títulos podem variar na redação, mas devem claramente pertencer a cada categoria.
- Não crie seções ## extras fora do scaffold.
- Se houver seção de tópicos, mantenha lista curta e explicativa (cada item com informação real).
- Remova qualquer linha órfã de fonte/citação no corpo ("Fonte N", "[Fonte N]" isolado, mapping).
- Garanta que "Síntese Final" tenha conteúdo substantivo (não aceitar conclusão de 1 frase).
- Remova seções fracas, vazias ou genéricas (com menos de 3 frases úteis de conteúdo real).
- Una seções sobrepostas ou excessivamente fragmentadas quando melhorar a fluidez.
- Prefira parágrafos explicativos a listas de tópicos soltos.
- Não inclua bloco "Fontes:" no corpo — ele será anexado separadamente.
- Não invente fatos nem extrapole além do conteúdo existente.
- Não escreva metacomentários sobre o processo de reorganização.

RETORNE APENAS O RESUMO REORGANIZADO.
"""

DEEP_SUMMARY_MICRO_BACKFILL_PROMPT = """\
Voce esta complementando um resumo aprofundado do documento "{doc_name}".
Um topico especifico ficou ausente e precisa de cobertura factual minima.

TOPICO FALTANTE:
{topic_label}

TRECHO DE REFERENCIA (fonte canonica disponivel):
{source_label}: {source_snippet}

TAREFA:
Escreva APENAS 1 paragrafo curto (60-120 palavras) que:
1. Cobre o topico "{topic_label}" com informacao factual retirada do trecho acima.
2. Inclui a citacao canonica {source_label} no proprio paragrafo.
3. Usa linguagem analitica e fluida, compativel com o estilo do resumo existente.

REGRAS OBRIGATORIAS:
- Escreva SOMENTE o paragrafo, sem titulo, sem introducao, sem metacomentario.
- Use APENAS fatos suportados pelo trecho de referencia acima.
- Inclua {source_label} como citacao inline no paragrafo.
- Nao reescreva o resumo nem adicione outro conteudo.
- Nao use citacoes nao-canonicas (ex.: [Contexto adicional], [p. N], etc.).
- Nao inclua secao "Fontes:" nem lista de fontes.
- Se o trecho nao fornecer informacao suficiente para o topico, retorne exatamente:
  INSUFICIENTE

RETORNE APENAS O PARAGRAFO (ou a palavra INSUFICIENTE).
"""

DEEP_SUMMARY_TOPIC_BACKFILL_PROMPT = """\
Voce esta ajustando um resumo aprofundado do documento "{doc_name}" para cobrir
topicos que ficaram ausentes na versao atual.

RESUMO ATUAL:
{draft}

TOPICOS FALTANTES (devem ser cobertos nesta reescrita):
{missing_topics_description}

TRECHOS DE REFERENCIA DOS TOPICOS FALTANTES (para citacoes [Fonte N]):
{backfill_context}

TAREFA:
Reescreva o resumo integrando cobertura factual dos topicos faltantes listados acima.

REGRAS OBRIGATORIAS:
- Preserve a estrutura existente de 4-6 secoes `##`. Nao crie novas secoes `##`.
- Preserve TODAS as citacoes inline [Fonte N] existentes no rascunho.
- Adicione cobertura dos topicos faltantes com [Fonte N] adequadas dos trechos fornecidos.
- Insira o conteudo novo nas secoes mais tematicamnte adequadas — nao force secoes novas.
- Nao remova conteudo existente valido; apenas amplie.
- Nao inclua secao "Fontes:" no corpo do texto.
- Nao escreva metacomentarios sobre o processo.
- Mantenha linguagem analitica e fluida.
- Se nao houver evidencia suficiente nos trechos para cobrir um topico, omita-o em vez de inventar.

RETORNE APENAS O RESUMO FINAL REESCRITO.
"""

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

# ──────────────────────────────────────────────────────────────────────────────
# De-overreach rewrite prompt — removes extrapolations from deep summary.
# Triggered when inference_density gate fails, unsupported high-risk claims are
# detected, or formula claims lack math support in conservative mode.
# ──────────────────────────────────────────────────────────────────────────────
DEEP_SUMMARY_DEOVERREACH_PROMPT = """\
Voce esta revisando um resumo aprofundado do documento "{doc_name}" para remover
afirmacoes que extrapolam o que esta explicitamente sustentado nas fontes citadas.

RASCUNHO ATUAL:
{draft}

TRECHOS DE REFERENCIA (fontes [Fonte N] disponiveis):
{context_sample}

TAREFA:
Reescreva o resumo removendo ou reformulando afirmacoes de alto risco nao sustentadas.

REGRAS OBRIGATORIAS:
1. PRESERVE a estrutura do resumo: secoes ##, titulos, ordem das secoes.
2. PRESERVE todas as citacoes inline [Fonte N] que sao validas (nao invente novas).
3. REMOVA ou REFORMULE:
   - Afirmacoes QUANTITATIVAS (numeros, percentuais, razoes, magnitudes) que nao aparecem
     literalmente em nenhuma das fontes citadas no mesmo paragrafo.
   - Afirmacoes COMPARATIVAS ("X e melhor que Y", "A supera B", "em contraste com C",
     "A diferencia-se de B por...") que nao estao explicitamente no material citado.
   - Afirmacoes MATEMATICAS (equacoes, variaveis, notacao formal) cujas fontes citadas
     nao contenham matematica real (expressoes, simbolos, formulas).
   - Afirmacoes TECNICAS assertivas (ex.: "mitiga variancia", "aumenta robustez",
     "melhora capacidade preditiva", "integra validacao") quando sustentadas apenas
     por fontes de baixo teor como sumario/indice/conteudo.
4. Para afirmacoes que nao podem ser verificadas: substitua por formulacao conceitual.
   Exemplo: "O material formaliza esta relacao matematicamente [Fonte N]" em vez de
   reproduzir uma equacao sem suporte.
5. Quando a fonte nao detalhar um ponto tecnico, registre a limitacao apenas
   se esse detalhe nao estiver coberto por nenhuma outra fonte do contexto.
6. Nao remova afirmacoes DESCRITIVAS ou PROCEDURAIS bem sustentadas.
7. Nao adicione conteudo novo — apenas remova ou reformule extrapolacoes.
8. Nao inclua secao "Fontes:" no corpo — ela sera anexada separadamente.
9. Nao escreva metacomentarios sobre o processo de revisao.
10. Mantenha linguagem analitica e fluida; nao reduza a qualidade do texto.

RETORNE APENAS O RESUMO REVISADO.
"""
