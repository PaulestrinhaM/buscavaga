# JobRadar

Monitor automatizado de vagas de dados, BI e operações, com filtro por regra,
score de relevância e notificação no Telegram. Roda de graça no GitHub Actions,
sem servidor.

## Por que existe

Buscar vaga na mão é improdutivo: o board repete anúncio antigo, a vaga boa some
rápido e quem olha na primeira hora leva vantagem sobre quem olha duas vezes por
dia. Este projeto substitui a checagem manual por um ciclo automático em três turnos
por dia, 7h, 12h e 18h de Brasília (`HORARIOS_CICLO` em `config.py`). Mais que isso
esbarra no limite mensal gratuito da Adzuna.

O GitHub atrasa e às vezes descarta disparos agendados, então o workflow não depende
de acertar o horário: ele dispara de hora em hora (minuto 17) e cada disparo consulta
o banco. Se a coleta do turno ainda não rodou, roda a coleta e o resumo; se já rodou,
só tenta o stand-by. Disparo perdido é coberto pelo seguinte.

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
"mobilidade"), `*` aceita variação ("engenh*" casa engenheiro, engenheira e engenharia) e
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
- **Júnior é o alvo, pleno passa com critério.** Em dados (analista e engenheiro
  de dados, BI, analytics) e em operações (marketing, revenue e sales ops, CRM,
  martech, integração) passa júnior, estágio, trainee, vaga sem nível e pleno.
  O pleno é julgado pela IA: passa se pedir até 3 anos de experiência e o gap for
  de ferramenta (Power BI, Tableau, BigQuery, Snowflake, dbt); cai se pedir 4
  anos ou mais, ou se o núcleo for cloud, Airflow, Kafka ou Docker em produção.
  Especialista em dados, sênior e acima caem já na regra.
- **Piso de R$ 4.000 por mês, CLT ou PJ.** Só corta salário declarado: a
  estimativa da Adzuna não conta, e vaga sem salário segue.
- **Machine learning está fora do escopo.** Cientista de dados, ML engineer,
  MLOps e afins são bloqueados pelo título. Machine learning citado na
  descrição de uma vaga de analista não bloqueia.
- **Vaga afirmativa exclusiva é descartada, menção a diversidade não.** O grupo
  precisa vir logo depois da palavra de exclusividade ("exclusiva para PcD");
  "exclusivas ou não para PcD" e "incentivamos candidaturas" continuam passando.
- **LinkedIn sem login.** O radar usa o endpoint público de visitante, o mesmo da
  busca deslogada: a conta usada nas candidaturas não entra em nada. É contra os
  termos do LinkedIn e ele limita rápido, então são poucas buscas, pausa longa, e
  um 429 encerra a fonte naquele ciclo sem derrubar as outras.
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
baixo, cortada pela IA, adiada (IA fora do ar), já vista em ciclo anterior, repetida entre fontes e
descartada pelo filtro por regra.

Esse registro não vai para o banco: são cerca de 1.500 vagas por dia, e o banco é
versionado no Git. Rodando localmente, a planilha fica em `saida/`.

## Fontes

| Fonte | Acesso | Cobertura |
| --- | --- | --- |
| Gupy | Endpoint público do portal | Termos remotos no Brasil e todas as vagas das cidades da região |
| LinkedIn | Endpoint público de visitante, sem login | Remoto no Brasil (`geoId`) e raio de 25 km de Caxias |
| Adzuna | API oficial, chave gratuita | Brasil, com faixa salarial |
| Solides | Dados embutidos na página | Só cidades da região: a busca por texto dela é solta demais |
| Google Jobs | SerpApi, chave gratuita (250 buscas/mês) | Agrega LinkedIn, Gupy, Indeed e sites de empresa; uma rodada por dia |
| Job boards | Greenhouse, Lever e Ashby por empresa | 14 empresas brasileiras conferidas, direto na origem |
| Himalayas | API pública, sem chave | Vagas remotas abertas ao Brasil |

Para acompanhar uma empresa específica, basta adicionar em `config.BOARDS`.

RemoteOK, Jobicy e Remotive saíram em nov/2026: zero vagas aprovadas em 14 dias. O
Vagas.com tem coletor pronto (`fontes/vagascom.py`), mas fica desligado: a busca por
termo responde 403 para o IP do GitHub Actions e as páginas de cidade quase não têm
vaga de dados. Solides é raspagem de HTML e quebra quando o site muda.

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
python main.py --standby                # tenta de novo a IA sobre as vagas em stand-by
python main.py --agendado               # o que o Actions roda: coleta do turno ou stand-by
python main.py --listar                 # tudo que o radar aprovou nos últimos 7 dias
python main.py --listar --dias 30 --score-min 7
python main.py --exportar vagas.csv     # exporta a lista para planilha
python main.py --relatorio              # precisão por fonte
```

### Triagem opcional por LLM

**Repescagem.** Vaga cujo título não bate com nenhum cargo conhecido, mas que passou em
todos os bloqueios rígidos (senioridade, local, data, afirmativa, área), também vai para
a IA, marcada como `"origem": "repescagem"`. A IA lê a descrição e só aprova se o dia a
dia for claramente o que o candidato faz. Pega título vago como "Operações de Marketing"
ou "Customer Success Operations". Teto de `MAX_REPESCAGEM` vagas por ciclo; o
excedente fica para o ciclo seguinte. Sem veredito da IA, vaga de repescagem nunca é
enviada.

Com `USAR_IA = True` em `config.py` e uma `GEMINI_API_KEY` no `.env`, o radar faz uma
segunda passagem avaliando cada vaga contra o perfil em `perfil.md`. O perfil mora num
arquivo à parte para ser atualizado sem mexer em código: quando o currículo mudar,
edita o arquivo e a data na primeira linha. Com mais de 45 dias sem revisão, o radar
manda um lembrete no Telegram na coleta de segunda de manhã. A IA
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
regra e são novidade. Isso cabe folgado na cota gratuita. Vaga cortada pela IA fica
gravada no banco, sem envio, para não voltar no ciclo seguinte.

**Stand-by.** Se a IA não conseguir avaliar uma vaga (API fora, cota, resposta
inválida), a vaga não é enviada nem descartada: vai inteira, com a descrição, para a
tabela `standby` do banco. Os disparos de hora em hora que não são de coleta tentam de
novo (`python main.py --standby`), em lotes menores. Aprovada segue o fluxo normal; cortada é gravada como
cortada; falhou de novo, continua esperando. Se a vaga ficar `STANDBY_DIAS_MAX` dias
(3) em stand-by sem avaliação, ou o anúncio passar de `DIAS_MAX_ANUNCIO` dias, sai da
fila e chega no Telegram com título e link, para olhar na mão. Enviar só pela regra quando a IA cai mandaria de uma vez tudo o que ela teria
cortado.

No GitHub Actions, cadastrar os mesmos valores em Settings, Secrets and variables,
Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` e,
se a triagem por IA estiver ligada, `GEMINI_API_KEY`. Para o Google Jobs,
`SERPAPI_API_KEY` (sem ela a fonte fica desligada).

## Testes

```bash
python -m pytest tests/ -v
```

Cerca de 200 casos cobrindo os três níveis de filtro, os bloqueios, o cálculo de score,
a identidade usada na deduplicação e os parsers das fontes, estes contra páginas reais
capturadas em `tests/fixtures/`. Rodam em CI a cada push.

## Limitações conhecidas

- O LinkedIn de visitante pode passar a bloquear o IP do Actions a qualquer momento.
  Se a fonte zerar por vários ciclos, o contorno é o alerta nativo do LinkedIn.
- O filtro olha o título. Vaga com título vago e descrição boa é perdida.
- Os pesos do score foram calibrados por julgamento, não contra histórico. Depois
  de algumas semanas de base, valem recalibração com os dados reais.
