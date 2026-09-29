"""Job boards publicos por empresa: Greenhouse, Lever e Ashby.

Util para acompanhar empresas-alvo diretamente, sem depender de agregador.
"""
from datetime import datetime, timezone

import requests

import config
from vaga import Vaga

TIMEOUT = 20
ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def _greenhouse(slug, dados):
    for j in dados.get("jobs", []):
        publicada = None
        if j.get("updated_at"):
            try:
                publicada = datetime.fromisoformat(j["updated_at"].replace("Z", "+00:00"))
            except ValueError:
                pass
        yield Vaga(
            titulo=j.get("title", ""), empresa=slug,
            local=(j.get("location") or {}).get("name", ""),
            link=j.get("absolute_url", ""), fonte=f"greenhouse:{slug}",
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
        yield Vaga(
            titulo=j.get("title", ""), empresa=slug,
            local=j.get("location", ""), link=j.get("jobUrl", ""),
            fonte=f"ashby:{slug}",
        )


PARSERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for plataforma, slug in config.BOARDS:
        url = ENDPOINTS[plataforma].format(slug=slug)
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            continue
        vagas.extend(PARSERS[plataforma](slug, r.json()))
    return vagas
