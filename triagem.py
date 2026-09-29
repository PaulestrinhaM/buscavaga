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
PERFIL = """Paulo Reis, Caxias do Sul (RS), Brasil.
Dois anos como analista de integracao de sistemas numa agencia de marketing digital:
integracao via API e webhook entre RD Station e CRMs (Pipedrive, Ploomes), n8n,
administracao de CRM, atribuicao de origem de lead e de venda, automacao de relatorios
em Python e pandas, paineis no Looker Studio.
Pontos fortes:
- Logica de CRM: estrutura de funil, campos, etapas, motivos de perda, roteamento de
  leads, higiene e deduplicacao de base. Fez onboarding e manutencao de CRM para uma
  carteira de cerca de vinte clientes simultaneos.
- Marketing digital com dominio de inbound: automacao de marketing, segmentacao,
  nutricao, lead scoring em ferramenta, atribuicao de origem.
- Tagueamento e mensuracao: Google Tag Manager, GA4, parametrizacao de UTM, captura
  first-party, conversoes em Google Ads, Meta e LinkedIn.
- Clientes B2B do setor industrial, perfil predominante da serra gaucha.
Cursando pos-graduacao em Data Science e Analytics na PUC-Rio, com projeto de lakehouse
em arquitetura medalhao no Databricks com PySpark, e projeto academico de lead scoring
em scikit-learn (nao sustenta vaga de ML). SQL em nivel intermediario.
Ingles para leitura tecnica e conversacao.
Salesforce, HubSpot e Power BI: nao usou, mas sao equivalentes diretos dos CRMs e da
ferramenta de BI que ja opera; pedir essas ferramentas NAO e motivo de descarte.
NAO tem: AWS, Airflow, Kafka, Docker em producao.
Nao busca machine learning nem ciencia de dados.
Nivel: junior estrito em dados, BI, engenharia de dados e analytics (sem experiencia
formal na area); junior ou pleno em marketing/revenue/sales operations, CRM e
integracao de sistemas (onde tem os dois anos). Aceita remoto de qualquer lugar do Brasil,
ou qualquer modalidade em Caxias do Sul e vizinhas (Farroupilha, Bento Goncalves,
Flores da Cunha, Sao Marcos, Garibaldi).
Nao e elegivel a vagas afirmativas exclusivas (pessoas negras, mulheres, PcD,
pessoas trans, 50+)."""

INSTRUCAO = """Avalie cada vaga para este candidato. Responda APENAS um JSON valido,
sem markdown, no formato:
{"vagas": [{"id": "<id>", "vale": true|false, "nota": 0-10, "motivo": "<ate 12 palavras>"}]}

Criterios para vale=false:
- exige nivel acima do aceito para a trilha da vaga (campo "trilha": dados ou
  operacoes; ver "Nivel" acima), ou anos de
  experiencia que ele nao tem; titulo que aceita junior ("Junior/Pleno") conta como junior
- exige como requisito central AWS, Airflow, Kafka ou Docker em producao
- vaga de machine learning ou ciencia de dados
- presencial ou hibrido fora de Caxias do Sul e vizinhas (Porto Alegre inclusive)
- vaga afirmativa exclusiva para um grupo (mencao a diversidade nao conta)
- area diferente (desenvolvimento puro, automacao industrial, financeiro, RH)
A nota mede o quanto a vaga aproveita a experiencia dele e o quanto ele preenche os requisitos."""


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


def triar(vagas: list) -> list:
    """Devolve as vagas aprovadas pela IA, com score e motivo atualizados.

    Em qualquer falha devolve a lista original: a IA refina, nunca bloqueia.
    """
    if not config.USAR_IA or not vagas:
        return vagas

    # lotes de MAX_VAGAS_IA: um lote que falha nao impede os outros
    vereditos: dict[str, dict] = {}
    for inicio in range(0, len(vagas), config.MAX_VAGAS_IA):
        lote = [
            {"id": v.id, "titulo": v.titulo, "empresa": v.empresa, "trilha": v.trilha,
             "local": v.local, "descricao": v.descricao[:600]}
            for v in vagas[inicio:inicio + config.MAX_VAGAS_IA]
        ]
        prompt = (f"{PERFIL}\n\n{INSTRUCAO}\n\nVagas:\n"
                  f"{json.dumps(lote, ensure_ascii=False)}")
        try:
            vereditos.update(_parsear(_chamar(prompt)))
        except Exception as e:
            print(f"[triagem] IA indisponivel ({e}), lote de {len(lote)} segue pelo filtro por regra")

    aprovadas = []
    for vaga in vagas:
        veredito = vereditos.get(vaga.id)
        if veredito is None:
            aprovadas.append(vaga)          # nao avaliada, nao descarta
            continue
        if not veredito.get("vale"):
            print(f"[triagem] cortada: {vaga.titulo[:45]} -> {veredito.get('motivo','')}")
            continue
        try:
            vaga.score = round(float(veredito.get("nota", vaga.score)))
        except (TypeError, ValueError):
            pass                            # nota ilegivel: fica o score da regra
        vaga.motivo = f"{vaga.motivo} | IA: {veredito.get('motivo','')}"
        aprovadas.append(vaga)
    return aprovadas
