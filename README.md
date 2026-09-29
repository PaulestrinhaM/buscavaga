# JobRadar

Monitor automatizado de vagas de dados, BI e operações, com filtro por regra,
score de relevância e notificação no Telegram. Roda de graça no GitHub Actions,
sem servidor.

## Por que existe

Buscar vaga na mão é improdutivo: o board repete anúncio antigo, a vaga boa some
rápido e quem olha na primeira hora leva vantagem sobre quem olha duas vezes por
dia. Este projeto substitui a checagem manual por um ciclo automático todo dia às
7h de Brasília (10h UTC no `.github/workflows/radar.yml`).

## Como funciona

| Etapa | O que faz |
| --- | --- |
| Coleta | Consulta cada fonte em sequência; falha de uma fonte não derruba o ciclo |
| Filtra | Três níveis de confiança no título, mais bloqueio de senioridade, ruído e anúncio velho |
| Pontua | Score 0 a 10 por soma de sinais conhecidos: cargo, ferramentas, senioridade, local |
| Deduplica | Por link normalizado e por empresa mais título, pegando a mesma vaga republicada |
| Notifica | Score 8 ou mais vira uma mensagem por vaga; o resto (score 5+) vai num resumo ranqueado logo em seguida |
| Mede | Relatório de vistas, notificadas e score médio por fonte |

### O filtro em três níveis

Nada aprova por palavra-chave solta. Essa é a decisão central do projeto.

1. **Cargo inequívoco** passa sozinho: "Analista de Dados", "Data Engineer".
2. **Cargo ambíguo** só passa com qualificador no mesmo título: "Business Analyst"
   sozinho é rejeitado, "Business Analyst de Dados" passa.
3. **Ferramenta** só passa junto com palavra de cargo: "Power BI" sozinho é
   rejeitado, "Analista Power BI" passa.

Cargos e qualificadores casam por palavra-chave, como um índice full text: "analista
de crm" vira {analista, crm} e casa "Analista CRM Jr" ou "Analista de Marketing
Pleno - CRM", em qualquer ordem. A palavra tem que ser inteira ("bi" não casa em
"mobilidade"), `*` aceita variação ("engenheir*" casa engenheiro e engenheira) e
aspas exigem frase exata ('"analytics engineer"'). Palavras de ligação ficam em
`PALAVRAS_IGNORADAS`.

### Decisões de arquitetura

- **Senioridade e regime de trabalho são lidos no título e no corpo.** O título
  sozinho deixa passar vaga sênior anunciada como "Analista de Dados", e o campo
  de local sozinho descarta vaga remota anunciada com a cidade da sede.
- **Anúncio sem data de publicação é descartado.** Na prática é quase sempre
  republicação antiga, e foi a origem de vaga já fechada chegando na notificação.
- **Híbrido não é remoto.** Passa vaga 100% remota de qualquer lugar do Brasil,
  ou qualquer modalidade em Caxias do Sul e vizinhas (Farroupilha, Bento
  Gonçalves, Flores da Cunha, São Marcos, Garibaldi). Híbrido ou presencial fora
  disso, Porto Alegre inclusive, é descartado.
- **Senioridade depende da trilha da vaga.** Em dados (analista e engenheiro de
  dados, BI, analytics) só passa júnior ou vaga sem nível: pleno, "Pl",
  mid-level e especialista são descartados. Em operações (marketing, revenue e
  sales ops, CRM, martech, integração de sistemas) passa júnior ou pleno. Sênior
  para cima cai nas duas. Título que aceita júnior ("Júnior/Pleno", "Jr/Pl")
  passa sempre, e vaga sem trilha clara segue a regra de dados, que é a mais
  estrita.
- **Machine learning está fora do escopo.** Cientista de dados, ML engineer,
  MLOps e afins são bloqueados pelo título. Machine learning citado na
  descrição de uma vaga de analista não bloqueia.
- **Vaga afirmativa exclusiva é descartada, menção a diversidade não.** O grupo
  precisa vir logo depois da palavra de exclusividade ("exclusiva para PcD");
  "exclusivas ou não para PcD" e "incentivamos candidaturas" continuam passando.
- **Sem scraping de LinkedIn.** Só fontes com API ou feed público. O LinkedIn é
  a maior fonte de vagas do país, e essa ausência é o custo assumido para não
  arriscar a conta usada nas candidaturas.
- **Score sem modelo.** Cinco sinais conhecidos com pesos declarados em
  `config.py`. Auditável e ajustável à mão, que é o que importa numa base pequena.
- **A vaga só é marcada como notificada depois que o envio confirma.** Falha de
  rede não faz vaga sumir.
- **Alerta automático** quando metade das fontes falha no mesmo ciclo: isso é
  problema de código, não escassez de mercado.
- **SQLite versionado no Git.** O histórico de deduplicação é o próprio commit,
  sem banco gerenciado nem custo.

## Onde ver as vagas que não chegaram no Telegram

O Telegram recebe só o que foi aprovado. Cada execução no GitHub Actions também
registra **todas** as vagas coletadas, com a etapa em que cada uma parou:

- **Resumo na página da execução** (aba Actions, clicar na execução): quantas vagas
  pararam em cada etapa, a lista das cortadas pela IA com o motivo, e a contagem dos
  motivos do filtro por regra.
- **Planilha completa** em *Artifacts*, no fim da mesma página: `vagas-do-ciclo.csv`,
  com etapa, motivo, score, título, empresa, local e link. Abre direto no Excel e fica
  disponível por 30 dias.

As etapas, na ordem do fluxo: enviada na hora, vai para o resumo, gravada com score
baixo, cortada pela IA, já vista em ciclo anterior, repetida entre fontes e
descartada pelo filtro por regra.

Esse registro não vai para o banco: são cerca de 1.500 vagas por dia, e o banco é
versionado no Git. Rodando localmente, a planilha fica em `saida/`.

## Fontes

| Fonte | Acesso | Cobertura |
| --- | --- | --- |
| Gupy | Endpoint público do portal de vagas | Brasil, maior ATS do país |
| Adzuna | API oficial, chave gratuita | Brasil, com faixa salarial |
| Remotive | Feed JSON público | Vagas remotas, categoria de dados |
| RemoteOK | Feed JSON público | Vagas remotas |
| Job boards | Greenhouse, Lever e Ashby por empresa | Empresas-alvo, direto na origem |

Para acompanhar uma empresa específica, basta adicionar em `config.BOARDS`.

## Como rodar

```bash
git clone <repo> && cd jobradar
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # preencher as credenciais
python main.py
```

Comandos:

```bash
python main.py                          # um ciclo completo
python main.py --testar-fontes          # testa cada fonte sem gravar nada
python main.py --fontes gupy            # limita a fontes específicas
python main.py --resumo                 # envia o resumo pendente
python main.py --listar                 # tudo que o radar aprovou nos últimos 7 dias
python main.py --listar --dias 30 --score-min 7
python main.py --exportar vagas.csv     # exporta a lista para planilha
python main.py --relatorio              # precisão por fonte
```

### Triagem opcional por LLM

Com `USAR_IA = True` em `config.py` e uma `GEMINI_API_KEY` no `.env`, o radar faz uma
segunda passagem avaliando cada vaga contra o perfil descrito em `triagem.py`. A IA
entra depois da regra e da deduplicação, nesta ordem:

1. Cada fonte é coletada.
2. O filtro por regra descarta o que não serve.
3. O que sobra é deduplicado contra o banco.
4. Só o que é novo vai para a triagem por IA, em uma única chamada com o lote
   inteiro (até `MAX_VAGAS_IA` vagas; as que passarem disso seguem sem avaliação).
5. A IA devolve um veredito por vaga, substitui o score pela nota dela e corta o que
   não faz sentido.
6. O que sobreviveu é notificado e gravado.

Ou seja, a IA nunca vê o volume bruto, só as poucas dezenas que já passaram pela
regra e são novidade. Isso cabe folgado na cota gratuita. Se a chamada falhar, o ciclo
segue com o resultado da regra: a IA refina, nunca bloqueia. Vaga cortada pela IA não
é gravada, então volta a ser avaliada no ciclo seguinte se ainda estiver no ar.

No GitHub Actions, cadastrar os mesmos valores em Settings, Secrets and variables,
Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` e,
se a triagem por IA estiver ligada, `GEMINI_API_KEY`.

## Testes

```bash
python -m pytest tests/ -v
```

123 casos cobrindo os três níveis de filtro, os bloqueios, o cálculo de score e a
identidade usada na deduplicação. Rodam em CI a cada push.

## Limitações conhecidas

- Sem o LinkedIn, a cobertura de vagas brasileiras fica incompleta. O contorno é
  manter alerta nativo do LinkedIn em paralelo.
- O filtro olha o título. Vaga com título vago e descrição boa é perdida.
- Os pesos do score foram calibrados por julgamento, não contra histórico. Depois
  de algumas semanas de base, valem recalibração com os dados reais.
