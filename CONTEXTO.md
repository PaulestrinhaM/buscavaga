# JobRadar: contexto e ajustes pendentes

Documento de passagem de bastão. Lê antes de mexer no código.

## O que é

Monitor de vagas para um candidato específico. Coleta de várias fontes, filtra por
regra, pontua, deduplica e notifica no Telegram. Roda local e no GitHub Actions.

Stack: Python 3.11, SQLite, requests, pytest. Sem framework, sem dependência além
de `requests` e `pytest`.

## Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `config.py` | Toda a configuração: termos, listas de filtro, pesos, fontes. Nenhuma regra aqui, só dados |
| `vaga.py` | Modelo `Vaga`, normalização de texto e as duas chaves de identidade |
| `filtro.py` | Bloqueios, classificação em três níveis de confiança, score |
| `db.py` | SQLite: dedup, histórico, fila do resumo, relatório |
| `fontes/` | Um módulo por fonte, cada um expondo `coletar() -> list[Vaga]` |
| `notificador.py` | Telegram: envio imediato, resumo paginado, alerta |
| `triagem.py` | Segunda triagem opcional por LLM (Gemini), desligada por padrão |
| `main.py` | Orquestração e CLI |
| `tests/test_filtro.py` | 123 casos, cada um documentando uma decisão de filtro |

## Decisões de design que devem ser preservadas

1. **Nada aprova por palavra-chave solta.** O filtro tem três níveis: cargo
   inequívoco passa sozinho; cargo ambíguo ("Business Analyst") só passa com
   qualificador de dados no mesmo título; nome de ferramenta ("Power BI") só passa
   junto com palavra de cargo.
2. **Bloqueio casa palavra inteira, não substring.** Existe `_contem_palavra()` com
   regex por causa disso: "head" bloqueia "Head of Data" e não pode bloquear
   "Headless". Já foi bug uma vez.
3. **A vaga só é marcada como notificada depois que o envio confirma.** Falha de
   rede não pode fazer vaga sumir. O resumo é paginado em mensagens de até 3.800
   caracteres e marca apenas as que efetivamente saíram. Isso também já foi bug.
4. **Anúncio sem data de publicação é descartado** (`EXIGIR_DATA`). Na prática é
   republicação antiga, e foi a origem de vaga já fechada chegando na notificação.
5. **A IA refina, nunca bloqueia.** Se a API falhar, o ciclo segue com o resultado
   do filtro por regra.
6. **Sem scraping do LinkedIn.** Decisão consciente: a conta do candidato é o
   principal canal de candidatura dele e não pode ser posta em risco. O custo é
   cobertura menor, e está registrado nas limitações do README.
7. **Falha de uma fonte não derruba o ciclo.** Se metade das fontes cair no mesmo
   ciclo, dispara alerta, porque isso é problema de código e não escassez de vagas.

## Perfil do candidato (é o que o filtro serve)

Paulo Reis, mora em Caxias do Sul (RS).

Tem: Python (pandas, NumPy), SQL intermediário, PySpark e Databricks em projeto
acadêmico (lakehouse medalhão), APIs REST e webhooks, n8n, RD Station, Pipedrive,
Ploomes, Google Tag Manager, GA4, Looker Studio, Git, scikit-learn em projeto.

Não tem: AWS, Airflow, Kafka, Docker em produção, Salesforce, HubSpot, Power BI.

Busca: júnior em dados, BI, engenharia de dados, analytics, ou marketing/revenue/
sales operations. Dois anos de experiência formal como analista de integração de
sistemas numa agência de marketing digital.

## Ajustes feitos (2026-09-28)

### 1. Vagas afirmativas exclusivas são descartadas

`filtro._exclusiva_afirmativa()`, com listas em `config.py` (`TERMOS_EXCLUSIVIDADE`,
`CONECTIVOS_AFIRMATIVA`, `GRUPOS_AFIRMATIVOS`, `NEGACOES_AFIRMATIVA`). Vale para
título e descrição.

A janela de caracteres sugerida não foi usada: nos dados reais da Gupy ela dá falso
positivo. Muitos anúncios trazem o texto padrão "vagas exclusivas ou não para pessoas
com deficiência", e benefícios como "exclusivos para colaboradores PcDs". A regra
exige que o grupo venha logo depois da palavra de exclusividade, separado só por
conectivos ("exclusiva para pessoas com deficiência", "Vaga Exclusiva PcD"), e ignora
negação logo antes ("não é exclusiva para PcD").

"Preferencialmente para pessoas negras" passa: preferência não é exclusividade.

### 2. Localização mais estrita

`CIDADES_ALVO` virou `CIDADES_REGIAO` (Caxias do Sul, Farroupilha, Bento Gonçalves,
Flores da Cunha, São Marcos, Garibaldi). Em `local_aceito()`, a ordem é:

1. cidade da região: passa em qualquer modalidade;
2. híbrido ou presencial no local ou no título: descarta;
3. remoto (no local, no título ou com expressão forte na descrição): passa.

O passo 2 também fecha um furo antigo: "auxílio home office" na descrição fazia vaga
híbrida passar como remota. `TERMOS_HIBRIDO` existia mas não era usado.

### 3. Vagas pleno são descartadas

`BLOQUEIO_PLENO` e `TERMOS_JUNIOR` em `config.py`, e a regra em
`filtro._pleno_sem_junior()`. "PL/SQL" não conta como pleno (`EXCECOES_PLENO`). O peso
"pleno" saiu de `PESOS`.

### 4. Fonte Gupy

A fonte funcionava: o endpoint responde, o envelope é `data` e os campos presumidos
estavam certos (o último ciclo gravado tinha 522 coletadas). O que quebrava a suíte era
um `__init__.py` na raiz com o YAML do workflow dentro, que fazia o pytest falhar ao
importar. Foi removido; o original está em `.github/workflows/radar.yml`.

Mudanças em `fontes/gupy.py`, com o formato validado documentado no topo do arquivo:
- os títulos de seção vêm colados no texto ("Requisitos e qualificaçõesExclusivo
  para..."), o que escondia o aviso de vaga exclusiva; agora são separados;
- a descrição sobe de 2.000 para 8.000 caracteres, porque o aviso fica no fim;
- a paginação para quando a página chega em anúncio mais velho que
  `DIAS_MAX_ANUNCIO` (o resultado vem do mais novo para o mais antigo);
- saíram os fallbacks de envelope e de campo que não existem na API.

### Limpeza e senioridade

- Saíram da raiz quatro arquivos que eram cópias com nome trocado: `adzuna.py`
  (era `fontes/remotive.py`), `remoteok.py` (era `fontes/__init__.py`), `download`
  (era `fontes/adzuna.py`) e `test_filtro.py` (versão antiga de `fontes/gupy.py`).
  Nenhum era fonte nova. Fonte nova entra em `fontes/` e em `fontes/__init__.py`.
- "Especialista" e "Specialist" entraram em `BLOQUEIO_SENIORIDADE`: na trilha
  Jr > Pl > Sr > Especialista, o termo fica acima de sênior. Por coerência, saíram
  das listas de cargo que aprovam ("especialista em crm" inclusive).

## Convenções

- Identificadores e comentários sem acento; textos de interface podem ter.
- Todo ajuste de filtro vem com teste em `tests/test_filtro.py`, no estilo dos que
  já estão lá: um caso por decisão, com nome que descreve a regra.
- `python -m pytest tests/ -q` tem que passar antes de qualquer entrega.
- Para validar contra fonte real, sem gravar nada:
  `python main.py --testar-fontes --fontes gupy`
- Config muda em `config.py`; regra muda em `filtro.py`. Não misturar.

## Comandos

```bash
python main.py                          # ciclo completo
python main.py --testar-fontes          # diagnóstico das fontes, sem gravar
python main.py --listar --dias 30       # tudo que foi aprovado
python main.py --exportar vagas.csv
python main.py --resumo
python main.py --relatorio              # precisão por fonte
```

Credenciais em `.env` (ver `.env.example`): Telegram, Adzuna e, opcionalmente,
Gemini para a triagem por LLM.
