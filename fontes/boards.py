"""Job boards publicos por empresa: Greenhouse, Lever e Ashby.

Util para acompanhar empresas-alvo diretamente, sem depender de agregador.
"""
import html
import re
from datetime import datetime, timezone

import requests

import config
from vaga import Vaga

TIMEOUT = 20
ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def _sem_html(texto: str) -> str:
    # o content do Greenhouse vem com o HTML escapado (&lt;p&gt;)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(texto)))).strip()


def _greenhouse(slug, dados):
    for j in dados.get("jobs", []):
        publicada = None
        # first_published e a data do anuncio; updated_at muda a cada edicao
        bruto = j.get("first_published") or j.get("updated_at")
        if bruto:
            try:
                publicada = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
            except ValueError:
                pass
        yield Vaga(
            titulo=j.get("title", ""), empresa=slug,
            local=(j.get("location") or {}).get("name", ""),
            link=j.get("absolute_url", ""), fonte=f"greenhouse:{slug}",
            descricao=_sem_html(j.get("content") or "")[:8000],
            publicada_em=publicada,
        )


def _lever(slug, dados):
    for j in dados:
        publicada = None
        if j.get("createdAt"):
            publicada = datetime.fromtimestamp(j["createdAt"] / 1000, tz=timezone.utc)
        yield Vaga(
            titulo=j.get("text", ""), empresa=slug,
            local=(j.get("categories") or {}).get("location", ""),
            link=j.get("hostedUrl", ""), fonte=f"lever:{slug}",
            descricao=(j.get("descriptionPlain") or "")[:2000],
            publicada_em=publicada,
        )


def _ashby(slug, dados):
    for j in dados.get("jobs", []):
        publicada = None
        if j.get("publishedAt"):
            try:
                publicada = datetime.fromisoformat(j["publishedAt"].replace("Z", "+00:00"))
            except ValueError:
                pass
        local = j.get("location", "")
        if j.get("isRemote"):
            local = f"Remoto ({local})"
        yield Vaga(
            titulo=j.get("title", ""), empresa=slug,
            local=local, link=j.get("jobUrl", ""),
            fonte=f"ashby:{slug}",
            descricao=(j.get("descriptionPlain") or "")[:8000],
            publicada_em=publicada,
        )


PARSERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for plataforma, slug in config.BOARDS:
        url = ENDPOINTS[plataforma].format(slug=slug)
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  [boards] {plataforma}:{slug} respondeu {r.status_code}")
            continue
        achadas = list(PARSERS[plataforma](slug, r.json()))
        vagas.extend(achadas)
        print(f"  [boards] {plataforma}:{slug}: {len(achadas)} vagas")
    return vagas
