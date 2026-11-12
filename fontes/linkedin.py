"""LinkedIn: endpoint publico de visitante, o mesmo que a busca sem login usa.

Sem login e sem conta: a conta do usuario nao corre risco. Mas e contra os termos
do LinkedIn e ele limita rapido (429 na quinta chamada seguida com 3 s de pausa,
medido em 2026-11-12 num runner do Actions). Por isso: poucas chamadas, pausa
longa, e um 429 encerra a fonte no ciclo com o que ja veio, sem derrubar nada.

Formato medido:
  GET /jobs-guest/jobs/api/seeMoreJobPostings/search -> HTML com <li> por vaga
    keywords, geoId (Brasil = 106057199; location em texto cai nos EUA),
    location (funciona para cidade), distance (km), f_WT=2 (remoto),
    f_TPR=r<segundos> (publicada nos ultimos N segundos), start (offset)
  GET /jobs-guest/jobs/api/jobPosting/<id> -> HTML do anuncio, com descricao e
    "Nivel de experiencia". Custa uma chamada por vaga: so para titulo que passa.
"""
import html
import re
import time
from datetime import datetime, timezone

import requests

import config
import filtro
from vaga import Vaga

BUSCA = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETALHE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
GEO_BRASIL = "106057199"
TIMEOUT = 25
PAUSA = 7.0
CABECALHO = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
             "Accept-Language": "pt-BR,pt;q=0.9"}


class Limitado(Exception):
    """LinkedIn respondeu 429: para por este ciclo."""


def _get(url: str, params: dict | None = None) -> str:
    r = requests.get(url, params=params, headers=CABECALHO, timeout=TIMEOUT)
    if r.status_code == 429:
        raise Limitado()
    r.raise_for_status()
    return r.text


def _limpo(trecho: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", trecho))).strip()


def _campo(card: str, padrao: str) -> str:
    m = re.search(padrao, card, re.S)
    return _limpo(m.group(1)) if m else ""


def _cards(pagina: str, remoto: bool) -> list[Vaga]:
    vagas = []
    for card in pagina.split("<li>")[1:]:
        id_vaga = re.search(r"urn:li:jobPosting:(\d+)", card)
        titulo = _campo(card, r'base-search-card__title">(.*?)</h3>')
        if not id_vaga or not titulo:
            continue
        local = _campo(card, r'job-search-card__location">(.*?)</span>')
        data = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', card)
        vagas.append(Vaga(
            titulo=titulo,
            empresa=_campo(card, r'base-search-card__subtitle">(.*?)</h4>'),
            # o filtro f_WT=2 garante o remoto; a cidade que vem e so a da sede
            local=f"Remoto ({local})" if remoto else local,
            link=f"https://www.linkedin.com/jobs/view/{id_vaga.group(1)}",
            fonte="linkedin",
            publicada_em=(datetime.fromisoformat(data.group(1)).replace(tzinfo=timezone.utc)
                          if data else None),
            extras={"linkedin_id": id_vaga.group(1)},
        ))
    return vagas


def _detalhar(vaga: Vaga) -> None:
    pagina = _get(DETALHE.format(id=vaga.extras["linkedin_id"]))
    descricao = _campo(pagina, r'show-more-less-html__markup[^>]*>(.*?)</div>')
    criterios = re.findall(r'description__job-criteria-subheader">(.*?)</h3>\s*'
                           r'<span[^>]*description__job-criteria-text[^>]*>(.*?)</span>',
                           pagina, re.S)
    extra = " | ".join(f"{_limpo(k)}: {_limpo(v)}" for k, v in criterios)
    vaga.descricao = f"{extra}\n{descricao}".strip()[:8000]


def _buscas() -> list[tuple[dict, bool]]:
    janela = f"r{config.LINKEDIN_HORAS * 3600}"
    buscas = [({"keywords": t, "geoId": GEO_BRASIL, "f_WT": "2", "f_TPR": janela}, True)
              for t in config.TERMOS_LINKEDIN]
    buscas += [({"keywords": t, "location": config.LINKEDIN_CIDADE, "distance": "25",
                 "f_TPR": janela}, False) for t in config.TERMOS_LINKEDIN_REGIAO]
    return buscas


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    try:
        for params, remoto in _buscas():
            achadas: list[Vaga] = []
            for pagina in range(config.PAGINAS_LINKEDIN):
                cards = _cards(_get(BUSCA, {**params, "start": len(achadas)}), remoto)
                time.sleep(PAUSA)
                if not cards:
                    break
                achadas.extend(cards)
            vagas.extend(achadas)
            print(f"  [linkedin] '{params['keywords']}' {'remoto' if remoto else 'regiao'}: "
                  f"{len(achadas)} vagas")
    except Limitado:
        print(f"  [linkedin] 429: parou com {len(vagas)} vagas neste ciclo")
        return vagas

    # descricao so de quem passa no titulo, ate o teto: o resto nao vale a chamada
    unicas = {v.link: v for v in vagas}
    candidatas = [v for v in unicas.values() if filtro.classificar(v)[0]]
    try:
        for vaga in candidatas[:config.LINKEDIN_DETALHES]:
            _detalhar(vaga)
            time.sleep(PAUSA)
    except Limitado:
        print("  [linkedin] 429 no detalhe: o resto vai sem descricao")
    print(f"  [linkedin] {len(unicas)} unicas, {min(len(candidatas), config.LINKEDIN_DETALHES)} "
          f"com descricao")
    return list(unicas.values())
