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
"""
import time
from datetime import datetime, timedelta, timezone

import requests

import config
from vaga import Vaga

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
        extras={"remoto": _local(item) == "Remoto"},
    )


def _buscar(termo: str, offset: int) -> tuple[list[dict], int | None]:
    """Uma pagina da busca: (itens, total que a API diz existir, se disser)."""
    params = {"jobName": termo, "limit": POR_PAGINA, "offset": offset}
    for tentativa in range(3):
        r = requests.get(URL, params=params, timeout=TIMEOUT,
                         headers={"User-Agent": "jobradar/1.0 (busca pessoal)"})
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** tentativa)
            continue
        r.raise_for_status()
        payload = r.json()
        total = None
        if isinstance(payload, dict):
            total = (payload.get("pagination") or {}).get("total")
        return _extrair_lista(payload), total if isinstance(total, int) else None
    return [], None


def coletar() -> list[Vaga]:
    limite = datetime.now(timezone.utc) - timedelta(days=config.DIAS_MAX_ANUNCIO)
    teto = config.PAGINAS_GUPY * POR_PAGINA     # vagas por termo, no maximo
    vagas: list[Vaga] = []
    for termo in config.TERMOS_BUSCA:
        offset, recentes, total_api, tamanhos = 0, 0, None, []
        while offset < teto:
            itens, total_api = _buscar(termo, offset=offset)
            if not itens:
                break
            convertidas = [_converter(i) for i in itens]
            vagas.extend(convertidas)
            tamanhos.append(len(itens))
            novas_pag = sum(1 for v in convertidas if v.publicada_em and v.publicada_em >= limite)
            recentes += novas_pag
            # avanca pelo que veio, nao pelo que pedimos: a API nova devolve paginas
            # menores que o limit pedido, e tratar isso como "ultima pagina" cortava a busca
            offset += len(itens)
            time.sleep(PAUSA)
            if total_api is not None and offset >= total_api:
                break
            # pagina inteira velha: com a lista do mais novo para o mais antigo, o resto
            # tambem e velho. O log abaixo mostra se isso segue valendo na API nova.
            if novas_pag == 0:
                break
        print(f"  [gupy] '{termo}': {offset} vagas em {len(tamanhos)} paginas {tamanhos}, "
              f"{recentes} com ate {config.DIAS_MAX_ANUNCIO} dias, total da API {total_api}")
    return vagas
