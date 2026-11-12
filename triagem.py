"""Segunda triagem opcional por LLM (Gemini), sobre o que o filtro por regra aprovou.

Uma unica chamada por ciclo, com o lote inteiro no mesmo prompt: cabe em
qualquer cota gratuita. Desligada por padrao, liga em config.USAR_IA.
"""
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import requests

import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
TIMEOUT = 90
ESPERAS = [5, 15, 30]      # segundos entre novas tentativas em 429/5xx

# O perfil que a IA le mora em perfil.md, na raiz do repositorio: e o arquivo que se
# atualiza quando o curriculo muda, sem mexer em codigo. Governa o que a IA considera
# aceitavel numa vaga; nao e a lista de competencias do curriculo, onde a regra e
# mais estrita.
ARQUIVO_PERFIL = Path(__file__).parent / "perfil.md"
DIAS_REVISAR_PERFIL = 45


def _ler_perfil() -> tuple[str, date | None]:
    """(texto sem cabecalho nem comentario, data da ultima revisao)."""
    bruto = ARQUIVO_PERFIL.read_text(encoding="utf-8")
    revisado = None
    m = re.match(r"\s*revisado_em:\s*(\d{4}-\d{2}-\d{2})", bruto)
    if m:
        revisado = date.fromisoformat(m.group(1))
        bruto = bruto[m.end():]
    texto = re.sub(r"<!--.*?-->", "", bruto, flags=re.S).strip()
    return texto, revisado


def dias_sem_revisar_perfil(hoje: date | None = None) -> int | None:
    _, revisado = _ler_perfil()
    if revisado is None:
        return None
    return ((hoje or date.today()) - revisado).days


PERFIL, _ = _ler_perfil()

INSTRUCAO = """Avalie cada vaga para este candidato. Leia a descricao, nao so o titulo:
titulo vago ou generico ("Operacoes de Marketing", "Business Operations", "Analista MIS")
pode esconder exatamente o trabalho que ele faz, e titulo bonito pode esconder outro.

O campo "origem" diz como a vaga chegou ate voce:
- "regra": o titulo ja bate com um cargo do perfil. Mantenha (vale=true) a menos que a
  descricao traga um criterio ELIMINATORIO abaixo ou mostre uma area claramente
  diferente. Descricao curta ou generica NAO e motivo de corte. Vaga sem nivel
  declarado e aceitavel.
- "repescagem": o titulo nao bate com nenhum cargo conhecido. So marque vale=true se a
  descricao mostrar, com clareza, que o dia a dia e o que ele faz ou busca (dados, BI,
  analytics, CRM, integracao, automacao, operacoes de receita). Na duvida, vale=false.
O campo "trilha" (dados ou operacoes) e so uma pista; decida pela descricao.

SENIORIDADE
- Junior, estagio, trainee ou sem nivel: aceito em qualquer trilha.
- Pleno: aceito em qualquer trilha, desde que a vaga peca no maximo 3 anos de
  experiencia (ele tem 2,5 anos com dados, integracao e indicadores) e que o nucleo
  do trabalho esteja no que ele tem ou num gap aceitavel (abaixo). Pleno que pede 4
  anos ou mais, ou que tem gap dificil como requisito central, e cortado.
- Senior, especialista, lead, coordenacao, gerencia, head, arquiteto, "III", ou
  lideranca de equipe: corte.
- Titulo que aceita junior ("Junior/Pleno") conta como junior.

GAPS
- Aceitavel (baixe a nota, NAO corte): ferramenta de BI que ele nao usou (Power BI,
  Tableau, Qlik, Metabase), data warehouse em nuvem (BigQuery, Snowflake, Redshift,
  Synapse), dbt, Azure Data Factory, Excel avancado, CRM diferente (Salesforce,
  HubSpot). Ele domina os fundamentos (SQL, modelagem, Python, BI em producao) e
  essas ferramentas se aprendem rapido. Databricks e PySpark contam A FAVOR.
- Dificil (corte se for requisito central): AWS, Azure ou GCP como plataforma
  principal do cargo, Airflow, Kafka, Docker ou Kubernetes em producao, Scala, Java,
  machine learning ou ciencia de dados como funcao principal.

Para cada vaga, nesta ordem:
1. Procure na descricao qualquer criterio ELIMINATORIO (abaixo). Achou: vale=false,
   qualquer que seja a origem.
2. Passou: aplique a regra da origem e a de senioridade.
3. De a nota.

Responda APENAS um JSON valido, sem markdown, no formato:
{"vagas": [{"id": "<id>", "vale": true|false, "nota": 0-10, "motivo": "<ate 12 palavras>"}]}

ELIMINATORIO, sem excecao:
- Senioridade fora do aceito (secao SENIORIDADE).
- Gap dificil como requisito central (secao GAPS).
- Presencial ou hibrido fora de Caxias do Sul e vizinhas (Porto Alegre inclusive).
  Local "Brasil" nao garante remoto: confira a modalidade na descricao.
- Remuneracao DECLARADA abaixo de R$ 4.000 por mes, CLT ou PJ (bolsa de estagio
  inclusive). Vaga sem salario informado NAO e cortada por isso.
- Vaga afirmativa exclusiva para um grupo (mencao a diversidade nao conta).
- Area diferente: desenvolvimento de software puro, automacao industrial, financeiro,
  contabil, RH, vendas diretas, atendimento, logistica, saude.

A nota (0-10) mede o quanto a vaga aproveita a experiencia dele e o quanto ele preenche
os requisitos. 8 ou mais: encaixe forte, vale candidatar hoje. Pleno com gap
aceitavel fica tipicamente entre 5 e 7."""


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


def triar(vagas: list, lote_max: int | None = None) -> tuple[list, list, list]:
    """(mantidas, cortadas, nao_avaliadas), com score e motivo atualizados.

    Com a IA desligada, tudo e mantido. Com a IA ligada, vaga que a IA nao conseguiu
    avaliar (API fora, resposta invalida) volta separada: quem chama decide se adia.
    """
    if not config.USAR_IA or not vagas:
        return vagas, [], []

    # lotes de MAX_VAGAS_IA: um lote que falha nao impede os outros
    lote_max = lote_max or config.MAX_VAGAS_IA
    vereditos: dict[str, dict] = {}
    for inicio in range(0, len(vagas), lote_max):
        lote = [
            {"id": v.id, "origem": "repescagem" if v.repescagem else "regra",
             "titulo": v.titulo, "empresa": v.empresa, "trilha": v.trilha,
             "local": v.local, "descricao": v.descricao[:config.DESCRICAO_IA]}
            for v in vagas[inicio:inicio + lote_max]
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
