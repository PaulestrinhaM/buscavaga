"""Google Jobs via SerpApi: o Google agrega LinkedIn, Gupy, Indeed, Vagas.com e
site de empresa no mesmo lugar. Raspar o Google direto nao da (bloqueio na hora).

Plano gratuito da SerpApi: 250 buscas por mes, 10 vagas por busca. Por isso roda
uma vez por dia, so no primeiro turno, com config.TERMOS_GOOGLE: 8 buscas por dia
ficam em ~240 por mes. Sem SERPAPI_API_KEY no ambiente a fonte fica desligada.

Parametros: engine=google_jobs, q, location (cidade por extenso), gl, hl,
next_page_token (o start foi aposentado). Resposta: jobs_results[] com title,
company_name, location, via, description, detected_extensions (posted_at,
work_from_home, salary, schedule_type), apply_options[{title, link}], share_link.
"""
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import config
from vaga import Vaga

URL = "https://serpapi.com/search.json"
TIMEOUT = 40


def _data(texto: str, agora: datetime) -> datetime | None:
    t = (texto or "").lower()
    m = re.search(r"(\d+)\s*(hora|hour|dia|day|semana|week|m[eê]s|month)", t)
    if not m:
        return None
    n, unidade = int(m.group(1)), m.group(2)
    dias = {"hora": 0, "hour": 0, "dia": 1, "day": 1, "semana": 7, "week": 7}.get(unidade, 30)
    return agora - timedelta(days=n * dias)


def _converter(item: dict, agora: datetime) -> Vaga:
    ext = item.get("detected_extensions") or {}
    remoto = ext.get("work_from_home") or "anywhere" in (item.get("location") or "").lower()
    local = item.get("location") or ""
    opcoes = item.get("apply_options") or []
    link = opcoes[0]["link"] if opcoes and opcoes[0].get("link") else item.get("share_link", "")
    return Vaga(
        titulo=item.get("title") or "",
        empresa=item.get("company_name") or "",
        local=f"Remoto ({local})" if remoto else local,
        link=link,
        fonte="google",
        descricao=(item.get("description") or "")[:8000],
        publicada_em=_data(ext.get("posted_at", ""), agora),
        salario=ext.get("salary", ""),
        extras={"via": item.get("via", "")},
    )


def _hora_de_rodar(agora: datetime) -> bool:
    local = agora + timedelta(hours=config.FUSO_BRASILIA)
    return local.hour < min(config.HORARIOS_CICLO) + 5


def coletar(forcar: bool = False) -> list[Vaga]:
    chave = os.getenv("SERPAPI_API_KEY")
    agora = datetime.now(timezone.utc)
    if not chave:
        print("  [google] sem SERPAPI_API_KEY: fonte desligada")
        return []
    if not forcar and not _hora_de_rodar(agora):
        print("  [google] so roda no primeiro turno do dia (cota de 250 buscas/mes)")
        return []
    vagas: list[Vaga] = []
    for termo, local in config.TERMOS_GOOGLE:
        r = requests.get(URL, timeout=TIMEOUT, params={
            "engine": "google_jobs", "q": termo, "location": local,
            "gl": "br", "hl": "pt-br", "api_key": chave,
        })
        if r.status_code == 429:
            print("  [google] cota da SerpApi esgotada")
            break
        r.raise_for_status()
        itens = r.json().get("jobs_results") or []
        vagas.extend(_converter(i, agora) for i in itens)
        print(f"  [google] '{termo}': {len(itens)} vagas")
    return vagas
