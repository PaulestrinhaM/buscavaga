# JobRadar: ajustes, lote 2

Continuação do `CONTEXTO.md`. Assume que os itens 1 a 6 daquele documento já foram
aplicados. Se os itens 5 (registrar descartadas) e 6 (publicar no GitHub Pages) ainda
não foram, eles seguem válidos.

## A. Senioridade depende da trilha da vaga

Hoje a regra de senioridade é única para todas as vagas. Precisa ser diferente por
trilha, porque o candidato tem dois anos de experiência em integração e operações,
e nenhuma experiência formal em dados.

**Trilha de dados** (analista de dados, engenheiro de dados, analista de BI,
business intelligence, analytics, analytics engineer, data analyst, data engineer,
inteligência de mercado, indicadores):

- Aceita: júnior, trainee, estágio, sem indicação de nível.
- Descarta: pleno, sênior, especialista, coordenação para cima.

**Trilha de operações** (marketing operations, revenue operations, sales operations,
CRM operations, analista de CRM, especialista em CRM, martech, analista de integração
de sistemas, web analytics, performance digital):

- Aceita: júnior, pleno, sem indicação de nível.
- Descarta: sênior, coordenação para cima.

Regra comum às duas: se o título menciona júnior em qualquer forma ("Júnior/Pleno",
"Jr/Pl"), o nível júnior prevalece e a vaga passa.

Implementação sugerida: a função que classifica já identifica qual termo de
`CARGOS_FORTES` casou. Marcar cada termo com a trilha a que pertence (dicionário ou
duas listas separadas), guardar a trilha na `Vaga`, e aplicar o bloqueio de
senioridade conforme a trilha. Vaga aprovada por cargo ambíguo ou por ferramenta,
sem trilha definida, segue a regra mais estrita, que é a de dados.

Critério de aceitação: "Digital Analytics Pleno" descartada; "Analista de CRM Pleno"
aprovada; "Engenheiro de Dados Pleno" descartada; "Marketing Operations Sênior"
descartada; "Analista de Dados Júnior/Pleno" aprovada.

## B. Machine learning sai do escopo

O candidato tem um projeto acadêmico de lead scoring em scikit-learn e considera que
isso não sustenta candidatura a vaga de ML. Vagas dessa área não devem mais chegar.

- Remover de `CARGOS_FORTES`: "cientista de dados", "data scientist".
- Não incluir termos de ML em `TERMOS_BUSCA`.
- Acrescentar ao bloqueio de ruído, quando aparecerem no título: "machine learning
  engineer", "ml engineer", "cientista de dados", "data scientist", "deep learning",
  "visao computacional", "nlp engineer", "mlops".
- Cuidado: menção a machine learning dentro da descrição de uma vaga de analista de
  dados não deve bloquear. O corte é por cargo no título, não por tema no corpo.

Critério de aceitação: "Cientista de Dados Júnior" descartada; "Analista de Dados
Júnior" com "conhecimento em machine learning é diferencial" na descrição, aprovada.

## C. Perfil do candidato em `triagem.py` precisa ser atualizado

O texto do perfil que vai no prompt está incompleto e em um ponto está errado.

**Acrescentar como forte:**

- Domínio da lógica de CRM: estrutura de funil, campos, etapas, motivos de perda,
  roteamento de leads, higiene e deduplicação de base. Fez onboarding e manutenção de
  CRM para uma carteira de cerca de vinte clientes simultâneos.
- Vivência ampla em marketing digital, com domínio de inbound: automação de
  marketing, segmentação, nutrição, lead scoring em ferramenta, atribuição de origem.
- Tagueamento e mensuração: Google Tag Manager, GA4, parametrização de UTM, captura
  first-party, conversões em Google Ads, Meta e LinkedIn.
- Experiência com clientes B2B do setor industrial, que é o perfil predominante da
  serra gaúcha.

**Retirar da lista de "não tem":** Salesforce, HubSpot e Power BI. O candidato não os
usou, mas são equivalentes diretos do que ele já opera (CRMs e ferramenta de BI), e
ele considera a curva de aprendizado curta. Vaga que peça essas ferramentas não deve
ser descartada por isso.

**Manter na lista de "não tem":** AWS, Airflow, Kafka, Docker em produção. Esses
continuam sendo motivo legítimo de descarte quando aparecem como requisito central.

**Ajustar a expectativa de nível** conforme o item A: júnior estrito em dados,
júnior ou pleno em operações e integração.

Observação: essa lista governa o que a IA considera aceitável numa vaga. Ela não é a
mesma coisa que a lista de competências declaráveis num currículo, onde a regra do
candidato é mais estrita e ferramenta não usada fica de fora.

## D. Deixar claro no README quando a triagem por IA roda

O usuário não entendeu em que ponto do fluxo a LLM entra. Documentar a ordem:

1. Cada fonte é coletada.
2. O filtro por regra descarta o que não serve.
3. O que sobra é deduplicado contra o banco.
4. Só o que é novo vai para a triagem por IA, em uma única chamada com o lote inteiro.
5. A IA devolve veredito por vaga, ajusta o score e corta o que não faz sentido.
6. O que sobreviveu é notificado e gravado.

Ou seja, a IA nunca vê o volume bruto, só as poucas dezenas que já passaram pela
regra e são novidade. Se a chamada falhar, o ciclo segue com o resultado da regra.

## Status (2026-09-28)

A, B, C e D aplicados; `python -m pytest tests/ -q` passa com 107 casos.

- **A.** `CARGOS_FORTES` virou `CARGOS_DADOS + CARGOS_OPERACOES`. `filtro.trilha()`
  devolve "operacoes" só quando o título casa cargo de operações e nenhum de dados;
  o resto (misto, ambíguo, ferramenta) fica em "dados". A trilha é gravada em
  `Vaga.trilha`. `BLOQUEIO_PLENO` (pleno, pl, mid-level, especialista, specialist)
  só vale para dados; `BLOQUEIO_SENIORIDADE` vale para as duas.
- **B.** Termos de ML em `BLOQUEIO_RUIDO`, só no título. "cientista" saiu de
  `PALAVRAS_CARGO`, senão "Cientista Python" passaria pela regra de ferramenta.
- **C.** Perfil reescrito em `triagem.py`. O lote enviado à IA agora leva a trilha de
  cada vaga, para ela aplicar o nível certo.
- **D.** Ordem do fluxo documentada no README. `GEMINI_API_KEY` foi acrescentada ao
  workflow, que antes não a repassava: no Actions a IA falharia em silêncio.

Correções no caminho:
- `USAR_IA = true` em `config.py` quebrava o import; corrigido para `True`.
- `test_dedup_no_mesmo_ciclo` rodava um ciclo sem isolar a rede: com o `.env` local,
  cada `pytest` mandava uma vaga falsa ao Telegram e chamava o Gemini. Agora usa stubs.

Em aberto:
- Itens 5 (registrar descartadas) e 6 (GitHub Pages) do `CONTEXTO.md`: não constam da
  versão que está nesta pasta, que só tinha 1 a 4.

## Cargo por palavra-chave (2026-09-28)

Cargos e qualificadores deixaram de casar por frase e passaram a casar por
palavra-chave (`filtro._cargo`), no modelo de um índice full text: tokeniza o título,
descarta `PALAVRAS_IGNORADAS`, exige palavra inteira, `*` para prefixo e aspas para
frase exata. Quando mais de um cargo casa, vence o de mais palavras-chave, e isso
também decide a trilha.

Motivo: a busca por frase perdia "Engenheiro(a) de Dados" e "Analista CRM Pl", e a
busca por substring aprovava "Analista de Mobilidade" (o "bi" de "mobilidade"),
"Consultor ABAP / Datasphere" e "Analista de ContentOps".

Na mesma rodada, "hibrida" (feminino) entrou em `TERMOS_HIBRIDO`: vaga "híbrida em
Joinville" passava como se fosse remota.

Não usei o FTS5 do SQLite de fato: as vagas são avaliadas em memória antes de irem
ao banco, e o FTS5 não tem stemmer para português, então o ganho seria só sintaxe.
A sintaxe dos termos em `config.py` é a mesma, para facilitar se um dia migrar.
