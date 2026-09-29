"""Jobicy: vagas remotas abertas ao Brasil, API publica sem chave.

Formato validado contra a API real em 2026-09-29:
  GET /api/v2/remote-jobs?geo=brazil&count=50 -> {"jobs": [...], "jobCount", ...}
Cada item: jobTitle, companyName, jobGeo ("Anywhere", "LATAM", "Brazil", ...),
jobLevel ("Senior", "Midweight", "Entry-Level, Junior", "Any", "Director"),
pubDate (ISO), url, jobDescription (HTML). Uma chamada por ciclo.
Termos de uso: creditar a Jobicy e levar ao link original, que e o que o link faz.
"""
import re
from datetime import datetime

import requests

from vaga import Vaga

URL = "https://jobicy.com/api/v2/remote-jobs"
TIMEOUT = 25

# nivel da fonte para as expressoes que o filtro ja reconhece na descricao
NIVEL = {"senior": "nivel senior", "director": "nivel senior", "midweight": "nivel pleno",
         "entry-level": "nivel junior", "junior": "nivel junior"}


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _converter(item: dict) -> Vaga:
    niveis = {NIVEL[n.strip().lower()] for n in (item.get("jobLevel") or "").split(",")
              if n.strip().lower() in NIVEL}
    publicada = None
    try:
        publicada = datetime.fromisoformat(str(item.get("pubDate")))
    except ValueError:
        pass
    return Vaga(
        titulo=item.get("jobTitle") or "",
        empresa=item.get("companyName") or "",
        local=f"Remoto ({item.get('jobGeo') or 'mundo todo'})",
        link=item.get("url") or "",
        fonte="jobicy",
        descricao=(f"{', '.join(sorted(niveis))}. " if niveis else "")
                  + _texto(item.get("jobDescription"))[:8000],
        publicada_em=publicada,
    )


def coletar() -> list[Vaga]:
    r = requests.get(URL, params={"geo": "brazil", "count": 50}, timeout=TIMEOUT,
                     headers={"User-Agent": "jobradar/1.0 (busca pessoal)"})
    r.raise_for_status()
    itens = r.json().get("jobs") or []
    print(f"  [jobicy] {len(itens)} vagas")
    return [_converter(i) for i in itens]
