"""Gupy: endpoint publico do portal de vagas, o mesmo que a busca do site usa.

Nao e a api.gupy.io, que exige token de empregador. Uso pessoal, com backoff.

Formato validado contra a API real em 2026-09-28:
  {"data": [...], "pagination": {"limit", "offset", "total"}}
Cada item: name, careerPageName, city, state, country, isRemoteWork,
workplaceType ("remote" | "hybrid" | "on-site"), publishedDate (ISO, UTC),
jobUrl, description. Resultado vem ordenado do mais novo para o mais antigo.
"""
import time
from datetime import datetime, timedelta, timezone

import requests

import config
from vaga import Vaga

URL = "https://employability-portal.gupy.io/api/v1/jobs"
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
        link=item.get("jobUrl") or item.get("careerPageUrl") or "",
        fonte="gupy",
        descricao=_descricao(item),
        publicada_em=_data(item),
        extras={"remoto": _local(item) == "Remoto"},
    )


def _buscar(termo: str, offset: int) -> list[dict]:
    params = {"jobName": termo, "limit": POR_PAGINA, "offset": offset}
    for tentativa in range(3):
        r = requests.get(URL, params=params, timeout=TIMEOUT,
                         headers={"User-Agent": "jobradar/1.0 (busca pessoal)"})
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** tentativa)
            continue
        r.raise_for_status()
        return _extrair_lista(r.json())
    return []


def coletar() -> list[Vaga]:
    limite = datetime.now(timezone.utc) - timedelta(days=config.DIAS_MAX_ANUNCIO)
    vagas: list[Vaga] = []
    for termo in config.TERMOS_BUSCA:
        total = 0
        for pagina in range(config.PAGINAS_GUPY):
            itens = _buscar(termo, offset=pagina * POR_PAGINA)
            if not itens:
                break
            total += len(itens)
            convertidas = [_converter(i) for i in itens]
            vagas.extend(convertidas)
            time.sleep(PAUSA)
            if len(itens) < POR_PAGINA:
                break
            # ordenado por data: se a pagina ja chegou em anuncio velho, a proxima e toda velha
            ultima = convertidas[-1].publicada_em
            if ultima and ultima < limite:
                break
        print(f"  [gupy] '{termo}': {total} vagas")
    return vagas
