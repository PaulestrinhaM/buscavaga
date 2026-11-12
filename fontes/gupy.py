"""Gupy: endpoint publico do portal de vagas, o mesmo que a busca do site usa.

Nao e a api.gupy.io, que exige token de empregador. Uso pessoal, com backoff.

Em 2026-09-30 a Gupy desligou employability-portal.gupy.io/api/v1/jobs (404 em
qualquer rota). A busca do site passou para portal.gupy.io/api/job-search/jobs,
com os mesmos parametros (jobName, limit, offset) e o mesmo envelope:
  {"data": [...], "pagination": {"limit", "offset", "total"}}
Cada item: name, careerPageName, city, state, workplaceType ("remote" | "hybrid"
| "on-site"), publishedDate (ISO, UTC), url/jobUrl, description. Sairam
isRemoteWork, country e companyId: o remoto agora vem so de workplaceType.
Offset >= 10000 devolve 400. Resultado vem do mais novo para o mais antigo.

Medido em 2026-11-12 (sonda no Actions):
- pagination.total nao e o total: com limit=100 devolve total=100 mesmo havendo
  ~200 vagas. Confiar nele fazia o coletor parar na primeira pagina de cada termo.
  O fim da busca e a pagina que vem com menos itens que o limit.
- workplaceType=remote filtra de fato, e city=<cidade> tambem. Por isso sao duas
  buscas: termo + remoto (o resto do Brasil so serve remoto), e cidade da regiao
  sem termo (presencial e hibrido servem, e o titulo e filtrado depois).
"""
import time
from datetime import datetime, timedelta, timezone

import requests

import config
from vaga import Vaga, normalizar

URL = "https://portal.gupy.io/api/job-search/jobs"
TIMEOUT = 25
POR_PAGINA = 100
PAUSA = 1.0          # segundos entre chamadas, para nao martelar o portal
MAX_DESCRICAO = 8000  # aviso de vaga afirmativa costuma estar no fim do anuncio

# A descricao chega com os titulos de secao colados no texto vizinho
# ("Requisitos e qualificacoesExclusivo para..."), o que esconde palavras do filtro.
SECOES = [
    "Responsabilidades e atribuições", "Requisitos e qualificações",
    "Informações adicionais", "Etapas do processo",
]


def _extrair_lista(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    valor = payload.get("data")
    return valor if isinstance(valor, list) else []


def _data(item: dict) -> datetime | None:
    bruto = item.get("publishedDate")
    if not bruto:
        return None
    try:
        return datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None


def _local(item: dict) -> str:
    if item.get("isRemoteWork") or item.get("workplaceType") == "remote":
        return "Remoto"
    partes = [item.get("city"), item.get("state")]
    local = ", ".join(p for p in partes if p)
    tipo = (item.get("workplaceType") or "").strip()
    return f"{local} ({tipo})" if local and tipo else local or tipo


def _descricao(item: dict) -> str:
    texto = item.get("description") or ""
    for secao in SECOES:
        texto = texto.replace(secao, f"\n{secao}\n")
    return texto[:MAX_DESCRICAO]


def _converter(item: dict) -> Vaga:
    return Vaga(
        titulo=item.get("name") or "",
        empresa=item.get("careerPageName") or "",
        local=_local(item),
        link=item.get("jobUrl") or item.get("url") or item.get("careerPageUrl") or "",
        fonte="gupy",
        descricao=_descricao(item),
        publicada_em=_data(item),
        extras={"remoto": _local(item) == "Remoto", "cidade": item.get("city") or ""},
    )


def _buscar(params: dict, offset: int) -> list[dict]:
    """Uma pagina da busca."""
    params = {**params, "limit": POR_PAGINA, "offset": offset}
    for tentativa in range(3):
        r = requests.get(URL, params=params, timeout=TIMEOUT,
                         headers={"User-Agent": "jobradar/1.0 (busca pessoal)"})
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** tentativa)
            continue
        r.raise_for_status()
        return _extrair_lista(r.json())
    return []


def _paginar(params: dict, max_paginas: int, limite: datetime) -> tuple[list[Vaga], list[int]]:
    vagas, tamanhos = [], []
    for pagina in range(max_paginas):
        itens = _buscar(params, offset=pagina * POR_PAGINA)
        if not itens:
            break
        convertidas = [_converter(i) for i in itens]
        vagas.extend(convertidas)
        tamanhos.append(len(itens))
        time.sleep(PAUSA)
        if len(itens) < POR_PAGINA:
            break                       # ultima pagina
        # do mais novo para o mais antigo: pagina cujo ultimo anuncio ja passou do
        # limite encerra, porque a seguinte seria toda velha
        ultima = convertidas[-1].publicada_em
        if ultima and ultima < limite:
            break
    return vagas, tamanhos


def coletar() -> list[Vaga]:
    limite = datetime.now(timezone.utc) - timedelta(days=config.DIAS_MAX_ANUNCIO)
    vagas: list[Vaga] = []
    for termo in config.TERMOS_GUPY:
        achadas, tamanhos = _paginar({"jobName": termo, "workplaceType": "remote"},
                                     config.PAGINAS_GUPY, limite)
        vagas.extend(achadas)
        print(f"  [gupy] remoto '{termo}': {len(achadas)} vagas {tamanhos}")
    for cidade in config.CIDADES_GUPY:
        achadas, tamanhos = _paginar({"city": cidade}, config.PAGINAS_GUPY_CIDADE, limite)
        # se a API ignorar a cidade, volta o Brasil inteiro: fica so o que e dela
        alvo = normalizar(cidade)
        locais = [v for v in achadas if alvo in normalizar(v.extras.get("cidade", ""))]
        vagas.extend(locais)
        print(f"  [gupy] cidade '{cidade}': {len(locais)} de {len(achadas)} vagas {tamanhos}")
    return vagas
