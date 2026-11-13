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

INSTRUCAO = """Avalie cada vaga para este candidato. Leia a descricao inteira, nao so o
titulo. O campo "destaques" traz, ja separados, os trechos do anuncio que falam de
modalidade, local, salario e anos de experiencia: confira-os sempre.

O OBJETIVO DELE e entrar em engenharia de dados ou analise de dados. BI e analytics
servem. CRM, martech e operacoes de receita sao plano B: valem so quando o dia a dia
e tecnico (dados, integracao, automacao, BI), e nunca como encaixe perfeito. Ter
trabalhado com CRM NAO faz uma vaga de CRM ser "encaixe exato": ele esta saindo disso.

AREA (campo "area", escolha uma):
- "dados": engenharia de dados, analise de dados, analytics engineering, governanca
  ou qualidade de dados. O nucleo e SQL, Python, pipeline, modelagem, analise.
- "bi": BI, dashboards, reporting, inteligencia comercial/de mercado, MIS, product
  analytics, pricing analitico. O nucleo e indicador, painel e analise.
- "operacoes_tecnicas": CRM, martech, marketing/revenue ops, integracao de sistemas,
  automacao, quando o trabalho e configurar ferramenta, integrar, tratar base,
  automatizar, medir.
- "marketing": execucao de marketing ou relacionamento: copy, conteudo, redes sociais,
  criacao de campanha, planejar e disparar e-mail/reguas, segmentacao de lead como
  tarefa principal, CRM de relacionamento com cliente, comunicacao, e-commerce ou
  marketplace operacional, pre-vendas/BDR.
- "outra": qualquer outra coisa (administrativo, financeiro, custos, credito, logistica,
  exportacao, compras, RH, vendas, atendimento, software puro, suporte de TI, estagio
  generico). Relatorio em planilha como parte de rotina administrativa NAO faz a vaga
  ser de dados.

MODALIDADE (campo "modalidade"): "remoto", "hibrido", "presencial" ou "nao_informado",
pelo que a DESCRICAO diz. O campo "local" pode estar errado: o LinkedIn marca vaga
hibrida como remota. Se a descricao fala em dias no escritorio, modelo hibrido ou
presencial, e isso que vale. "Auxilio home office" e beneficio, nao modalidade.

SENIORIDADE
- Junior, estagio, trainee ou sem nivel: aceito.
- Pleno: aceito se pedir no maximo 3 anos de experiencia (ele tem 2,5 anos com dados,
  integracao e indicadores) e o nucleo estiver no que ele tem ou num gap aceitavel.
  Pleno que pede 4 anos ou mais, ou com gap dificil como requisito central: corte.
- Senior, especialista, lead, coordenacao, gerencia, head, arquiteto, "III", "pleno-
  senior" no nivel do LinkedIn, ou lideranca de equipe: corte.
- Titulo que aceita junior ("Junior/Pleno") conta como junior.

GAPS
- Aceitavel (baixe a nota, NAO corte): Power BI, Tableau, Qlik, Metabase, BigQuery,
  Snowflake, Redshift, Synapse, dbt, Azure Data Factory, Excel avancado, Salesforce,
  HubSpot. Ele domina os fundamentos e essas ferramentas se aprendem rapido.
  Databricks e PySpark contam A FAVOR.
- Dificil (corte se for requisito central): AWS, Azure ou GCP como plataforma principal
  do cargo, Airflow, Kafka, Docker ou Kubernetes em producao, Scala, Java, machine
  learning ou ciencia de dados como funcao principal.

ORIGEM: "regra" = o titulo bateu com um cargo do perfil; "repescagem" = nao bateu, e
so vale se a descricao mostrar com clareza area "dados", "bi" ou "operacoes_tecnicas".

ELIMINATORIO (vale=false):
- Area "marketing" ou "outra".
- Modalidade hibrido ou presencial fora de Caxias do Sul e vizinhas (Farroupilha,
  Bento Goncalves, Flores da Cunha, Garibaldi, Sao Marcos). Porto Alegre e Sao Paulo
  inclusive.
- Senioridade fora do aceito, ou gap dificil como requisito central.
- Remuneracao DECLARADA abaixo de R$ 4.000 por mes, CLT ou PJ (bolsa inclusive). Sem
  salario informado NAO e corte.
- Vaga afirmativa exclusiva para um grupo (mencao a diversidade nao conta).

NOTA (0-10): quanto a vaga o aproxima de engenharia/analise de dados E quanto ele
preenche os requisitos.
- "dados" com encaixe bom: 8 a 10. Com gaps aceitaveis: 6 a 7.
- "bi": 6 a 9.
- "operacoes_tecnicas": no maximo 6, mesmo com encaixe perfeito.
Descricao vazia ou curta demais para julgar: nota no maximo 5.

Responda APENAS um JSON valido, sem markdown, no formato:
{"vagas": [{"id": "<id>", "area": "...", "modalidade": "...", "vale": true|false,
"nota": 0-10, "motivo": "<ate 12 palavras>"}]}"""

# Trechos que decidem a vaga e costumam estar no fim do anuncio, depois do corte de
# tamanho: vao separados no campo "destaques", para a IA nunca deixar de ver.
PADRAO_DESTAQUE = re.compile(
    r"remot|h[ií]brid|hybrid|presencial|on-?site|escrit[oó]rio|home office|modelo de trabalho|"
    r"modalidade|local de trabalho|localiza|dias? (?:na|por) semana|\d+x|sal[aá]rio|"
    r"remunera|R\$|bolsa|CLT|PJ\b|anos de experi|years of experience|experi[eê]ncia (?:m[ií]nima|de \d)",
    re.I)
# Consequencias aplicadas em codigo, nao na confianca na nota da IA
AREAS_CORTADAS = {"marketing", "outra"}
TETO_NOTA_POR_AREA = {"operacoes_tecnicas": 6}


def destaques(descricao: str, limite: int = 900) -> str:
    frases = re.split(r"(?<=[.!?;])\s+|\n+", descricao or "")
    achadas = []
    for f in frases:
        f = f.strip()
        if f and PADRAO_DESTAQUE.search(f) and f not in achadas:
            achadas.append(f[:220])
    return " | ".join(achadas)[:limite]


def _na_regiao(vaga) -> bool:
    from vaga import normalizar
    alvo = normalizar(vaga.local)
    return any(c in alvo for c in config.CIDADES_REGIAO)


def aplicar_veredito(vaga, veredito: dict) -> tuple[bool, str]:
    """(vale, motivo) depois das regras que nao dependem da boa vontade da IA."""
    area = str(veredito.get("area", "")).lower()
    modalidade = str(veredito.get("modalidade", "")).lower()
    motivo = veredito.get("motivo", "")
    if not veredito.get("vale"):
        return False, motivo
    if area in AREAS_CORTADAS:
        return False, f"area {area}: {motivo}"
    if modalidade in ("hibrido", "presencial") and not _na_regiao(vaga):
        return False, f"{modalidade} fora da regiao: {motivo}"
    try:
        nota = float(veredito.get("nota", vaga.score))
    except (TypeError, ValueError):
        nota = vaga.score
    teto = TETO_NOTA_POR_AREA.get(area)
    if teto is not None:
        nota = min(nota, teto)
    vaga.score = round(nota)
    return True, f"[{area or '?'}] {motivo}"


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
             "titulo": v.titulo, "empresa": v.empresa, "local": v.local,
             "destaques": destaques(v.descricao),
             "descricao": v.descricao[:config.DESCRICAO_IA]}
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
        vale, motivo = aplicar_veredito(vaga, veredito)
        if not vale:
            print(f"[triagem] cortada: {vaga.titulo[:45]} -> {motivo}")
            vaga.motivo = f"IA: {motivo}"
            cortadas.append(vaga)
            continue
        vaga.motivo = f"{vaga.motivo} | IA: {motivo}"
        mantidas.append(vaga)
    return mantidas, cortadas, nao_avaliadas
