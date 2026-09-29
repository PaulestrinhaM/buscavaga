"""Segunda triagem opcional por LLM (Gemini), sobre o que o filtro por regra aprovou.

Uma unica chamada por ciclo, com o lote inteiro no mesmo prompt: cabe em
qualquer cota gratuita. Desligada por padrao, liga em config.USAR_IA.
"""
import json
import os
import time

import requests

import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
TIMEOUT = 90
ESPERAS = [5, 15, 30]      # segundos entre novas tentativas em 429/5xx

# Governa o que a IA considera aceitavel numa vaga. Nao e a lista de competencias
# do curriculo, onde a regra e mais estrita e ferramenta nao usada fica de fora.
# Base: dados validados do curriculo (skill curriculo-ats-paulo). Sem contato pessoal:
# o repositorio e publico.
PERFIL = """CANDIDATO: Paulo Reis, Caxias do Sul (RS), Brasil.

EXPERIENCIA
- Analista de Integracao de Sistemas numa agencia de marketing digital, desde marco de
  2024 (entrou como assistente e foi promovido). Trabalha na fronteira entre marketing,
  vendas e tecnologia:
  - camada de sincronizacao via API entre RD Station Marketing, RD CRM e RD Conversas:
    resolucao de identidade de cliente, roteamento de leads, deduplicacao, criacao
    condicional de negociacoes, atribuicao de venda por canal;
  - cerca de 10 integracoes entre RD Station e CRMs externos (Pipedrive, Ploomes);
  - webhooks e automacoes no n8n, com GTM e JavaScript;
  - tracking e atribuicao de 26 contas de midia (Google Ads, Meta Ads) via Google Tag
    Manager, com captura de origem first-party e parametrizacao de UTM;
  - automacao de relatorios de leads e vendas por origem em Python (pandas);
  - dashboards de KPI em codigo (Chart.js);
  - onboarding e manutencao de CRM para uma carteira de cerca de vinte clientes:
    funil, campos, etapas, motivos de perda, higiene e deduplicacao de base;
  - inbound: automacao de marketing, segmentacao, nutricao, lead scoring em ferramenta;
  - clientes B2B do setor industrial, perfil predominante da serra gaucha.
- Jornalista (2021-2024): apuracao, investigacao, sintese e redacao. Comunicacao escrita
  forte e habito de investigar causa e efeito.

FORMACAO
- Pos-graduacao em Data Science e Analytics na PUC-Rio (em andamento, ate 2027).
  Engenharia de dados, modelagem e governanca sao conhecimento academico, nao pratica
  profissional. Projeto academico de lead scoring em scikit-learn (nao sustenta vaga de ML).
- Bacharel em Jornalismo.

NIVEIS HONESTOS
- Forte: Python (pandas, NumPy), integracao via API e webhooks, n8n, RD Station (inclusive
  API), Google Tag Manager, Git/GitHub, IA generativa como copiloto, ingles avancado.
- Intermediario: SQL (consultas, nunca avancado), Excel, atribuicao (UTM, last-click,
  Google Analytics), espanhol.
- Basico ou contato inicial: JavaScript, HTML, Looker Studio.
- Salesforce, HubSpot e Power BI: nao usou, mas sao equivalentes diretos dos CRMs e da
  ferramenta de BI que ja opera; pedir essas ferramentas NAO e motivo de descarte.
- NAO tem: AWS, Airflow, Kafka, Docker em producao, deep learning.

O QUE ELE BUSCA
- Dados, BI, analytics e engenharia de dados: SO junior, estagio, trainee ou vaga sem
  nivel declarado. Nao tem experiencia formal na area, mas e o alvo principal: vaga de
  engenharia de dados junior ou sem nivel E desejada, e ele esta se formando nisso.
- Marketing/revenue/sales operations, CRM, martech, automacao e integracao de sistemas:
  junior ou pleno. E onde tem os dois anos de experiencia.
- Local: remoto de qualquer lugar do Brasil, ou qualquer modalidade em Caxias do Sul e
  vizinhas (Farroupilha, Bento Goncalves, Flores da Cunha, Sao Marcos, Garibaldi).
- Nao busca machine learning nem ciencia de dados.
- Nao e elegivel a vagas afirmativas exclusivas (pessoas negras, mulheres, PcD, pessoas
  trans, 50+)."""

INSTRUCAO = """Avalie cada vaga para este candidato. Leia a descricao, nao so o titulo:
titulo vago ou generico ("Operacoes de Marketing", "Business Operations", "Analista MIS")
pode esconder exatamente o trabalho que ele faz, e titulo bonito pode esconder outro.

O campo "origem" diz como a vaga chegou ate voce:
- "regra": o titulo ja bate com um cargo do perfil. Mantenha (vale=true) a menos que a
  descricao traga um criterio ELIMINATORIO abaixo ou mostre uma area claramente
  diferente. Descricao curta ou generica NAO e motivo de corte. Vaga sem nivel
  declarado e aceitavel: so corte por senioridade se a descricao pedir nivel ou anos
  de experiencia acima do aceito. Stack que ele ainda nao
  usou (Azure, GCP, Snowflake, Databricks, Spark, Power BI, dbt) NAO e motivo de corte:
  vaga junior pressupoe aprender; baixe a nota, nao corte.
- "repescagem": o titulo nao bate com nenhum cargo conhecido. So marque vale=true se a
  descricao mostrar, com clareza, que o dia a dia e o que ele faz (CRM, integracao,
  automacao, dados de marketing, analise de dados, operacoes de receita). Na duvida,
  vale=false.
O campo "trilha" (dados ou operacoes) e so uma pista; decida a trilha pela descricao.

Para cada vaga, nesta ordem:
1. Procure na descricao qualquer criterio ELIMINATORIO (abaixo). Achou: vale=false,
   qualquer que seja a origem. Cidade e modalidade sempre: presencial ou hibrido fora
   da regiao elimina, mesmo que o resto seja perfeito.
2. Passou: aplique a regra da origem ("regra" ou "repescagem").
3. De a nota.

Responda APENAS um JSON valido, sem markdown, no formato:
{"vagas": [{"id": "<id>", "vale": true|false, "nota": 0-10, "motivo": "<ate 12 palavras>"}]}

ELIMINATORIO, sem excecao, mesmo que o resto combine perfeitamente:
- Senioridade acima do aceito para a trilha: senior, especialista, lead, coordenacao,
  gerencia, head, arquiteto, "II"/"III", e pleno na trilha de dados. Vale tambem quando a
  descricao exige 4 anos ou mais de experiencia, ou "solida experiencia" na funcao, ou
  lideranca de equipe. Titulo que aceita junior ("Junior/Pleno") conta como junior.
- Presencial ou hibrido fora de Caxias do Sul e vizinhas (Porto Alegre inclusive). Local
  "Brasil" nao garante remoto: confira a modalidade na descricao.
- Vaga afirmativa exclusiva para um grupo (mencao a diversidade nao conta).
- Machine learning ou ciencia de dados como funcao principal.
- Requisito central de AWS, Airflow, Kafka ou Docker em producao.
- Area diferente: desenvolvimento de software puro, automacao industrial, financeiro,
  contabil, RH, vendas diretas, atendimento, logistica.

A nota (0-10) mede o quanto a vaga aproveita a experiencia dele e o quanto ele preenche
os requisitos. 8 ou mais: encaixe forte, vale candidatar hoje."""


def _chamar_modelo(modelo: str, prompt: str, chave: str) -> str:
    # O modelo "pensa" antes de responder e esse raciocinio conta no limite de saida:
    # com 4000 tokens o JSON saia cortado. Limite folgado e raciocinio curto.
    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 16000,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    for tentativa in range(len(ESPERAS) + 1):
        r = requests.post(
            URL.format(modelo=modelo),
            headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
            json=corpo, timeout=TIMEOUT,
        )
        # 503 ("alta demanda") e comum no free tier e costuma passar em segundos
        if r.status_code in (429, 500, 503) and tentativa < len(ESPERAS):
            time.sleep(ESPERAS[tentativa])
            continue
        if not r.ok:
            raise RuntimeError(f"{modelo} respondeu {r.status_code}")
        candidato = r.json()["candidates"][0]
        if candidato.get("finishReason") == "MAX_TOKENS":
            raise RuntimeError(f"{modelo} cortou a resposta no limite de tokens")
        return "".join(p.get("text", "") for p in candidato["content"]["parts"])
    raise RuntimeError(f"{modelo} indisponivel")


def _chamar(prompt: str) -> str:
    """Tenta o modelo principal e, se ele nao responder, o reserva."""
    chave = os.getenv("GEMINI_API_KEY")
    if not chave:
        raise RuntimeError("GEMINI_API_KEY ausente no .env")
    erros = []
    for modelo in (config.MODELO_IA, config.MODELO_IA_RESERVA):
        try:
            return _chamar_modelo(modelo, prompt, chave)
        except (RuntimeError, requests.RequestException) as e:
            erros.append(str(e))
    raise RuntimeError("; ".join(erros))


def _parsear(bruto: str) -> dict[str, dict]:
    texto = bruto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    dados = json.loads(texto)
    return {str(v["id"]): v for v in dados.get("vagas", [])}


def triar(vagas: list) -> tuple[list, list, list]:
    """(mantidas, cortadas, nao_avaliadas), com score e motivo atualizados.

    Com a IA desligada, tudo e mantido. Com a IA ligada, vaga que a IA nao conseguiu
    avaliar (API fora, resposta invalida) volta separada: quem chama decide se adia.
    """
    if not config.USAR_IA or not vagas:
        return vagas, [], []

    # lotes de MAX_VAGAS_IA: um lote que falha nao impede os outros
    vereditos: dict[str, dict] = {}
    for inicio in range(0, len(vagas), config.MAX_VAGAS_IA):
        lote = [
            {"id": v.id, "origem": "repescagem" if v.repescagem else "regra",
             "titulo": v.titulo, "empresa": v.empresa, "trilha": v.trilha,
             "local": v.local, "descricao": v.descricao[:config.DESCRICAO_IA]}
            for v in vagas[inicio:inicio + config.MAX_VAGAS_IA]
        ]
        prompt = (f"{PERFIL}\n\n{INSTRUCAO}\n\nVagas:\n"
                  f"{json.dumps(lote, ensure_ascii=False)}")
        try:
            vereditos.update(_parsear(_chamar(prompt)))
        except Exception as e:
            print(f"[triagem] IA indisponivel ({e}), lote de {len(lote)} sem avaliacao")

    mantidas, cortadas, nao_avaliadas = [], [], []
    for vaga in vagas:
        veredito = vereditos.get(vaga.id)
        if veredito is None:
            nao_avaliadas.append(vaga)
            continue
        if not veredito.get("vale"):
            print(f"[triagem] cortada: {vaga.titulo[:45]} -> {veredito.get('motivo','')}")
            vaga.motivo = f"IA: {veredito.get('motivo', '')}"
            cortadas.append(vaga)
            continue
        try:
            vaga.score = round(float(veredito.get("nota", vaga.score)))
        except (TypeError, ValueError):
            pass                            # nota ilegivel: fica o score da regra
        vaga.motivo = f"{vaga.motivo} | IA: {veredito.get('motivo','')}"
        mantidas.append(vaga)
    return mantidas, cortadas, nao_avaliadas
