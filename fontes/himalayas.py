"""Himalayas: vagas remotas com filtro de pais, API publica sem chave.

Formato validado contra a API real em 2026-09-29:
  GET /jobs/api/search?q=<termo>&country=Brazil -> {"jobs": [...], "totalCount", ...}
Cada item: title, companyName, locationRestrictions (lista de paises; vazia = mundo
todo), seniority (lista: "Entry-level", "Mid-level", "Senior", ...), pubDate (epoch
em segundos), applicationLink, description (HTML). Busca devolve 20 por termo,
ordenada por relevancia. A API e em ingles, por isso os termos de busca sao outros.
"""
import re
import time
from datetime import datetime, timezone

import requests

import config
from vaga import Vaga

URL = "https://himalayas.app/jobs/api/search"
TIMEOUT = 25
PAUSA = 1.0

# O titulo em ingles raramente traz o nivel; a fonte informa em campo proprio.
# Vai para o comeco da descricao com as expressoes que o filtro ja reconhece
# ("nivel senior" em SENIORIDADE_DESCRICAO), e a IA le o resto.
NIVEL = {
    "Entry-level": "nivel junior", "Internship": "nivel estagio",
    "Mid-level": "nivel pleno", "Senior": "nivel senior",
    "Manager": "nivel senior", "Director": "nivel senior", "Executive": "nivel senior",
}


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _converter(item: dict) -> Vaga:
    paises = item.get("locationRestrictions") or []
    niveis = [NIVEL.get(n, n) for n in item.get("seniority") or []]
    # so conta como senior se a vaga nao aceitar nenhum nivel abaixo
    if any(n != "nivel senior" for n in niveis):
        niveis = [n for n in niveis if n != "nivel senior"]
    publicada = None
    if item.get("pubDate"):
        publicada = datetime.fromtimestamp(int(item["pubDate"]), tz=timezone.utc)
    return Vaga(
        titulo=item.get("title") or "",
        empresa=item.get("companyName") or "",
        local="Remoto (" + (", ".join(paises[:5]) if paises else "mundo todo") + ")",
        link=item.get("applicationLink") or "",
        fonte="himalayas",
        descricao=(f"{', '.join(sorted(set(niveis)))}. " if niveis else "")
                  + _texto(item.get("description"))[:8000],
        publicada_em=publicada,
    )


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for termo in config.TERMOS_BUSCA_EN:
        r = requests.get(URL, params={"q": termo, "country": "Brazil"}, timeout=TIMEOUT,
                         headers={"User-Agent": "jobradar/1.0 (busca pessoal)"})
        if r.status_code == 429:
            time.sleep(5)
            continue
        r.raise_for_status()
        itens = r.json().get("jobs") or []
        vagas.extend(_converter(i) for i in itens)
        print(f"  [himalayas] '{termo}': {len(itens)} vagas")
        time.sleep(PAUSA)
    return vagas
