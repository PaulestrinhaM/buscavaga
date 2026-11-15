"""Adzuna: API oficial, cadastro gratuito em developer.adzuna.com.

Principal fonte de vagas brasileiras do projeto.
"""
import os
from datetime import datetime

import requests

import config
from vaga import Vaga

URL = "https://api.adzuna.com/v1/api/jobs/{pais}/search/{pagina}"
TIMEOUT = 20
POR_PAGINA = 50


def _credenciais() -> tuple[str, str]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError(
            "ADZUNA_APP_ID ou ADZUNA_APP_KEY nao encontrados. Confirme que o arquivo .env "
            "esta na pasta do projeto, com esse nome exato (cuidado com .env.txt no Windows), "
            "e que as linhas nao tem aspas."
        )
    return app_id, app_key


def _converter(item: dict) -> Vaga:
    publicada = None
    if item.get("created"):
        try:
            publicada = datetime.fromisoformat(item["created"].replace("Z", "+00:00"))
        except ValueError:
            pass
    salario = f"R$ {item['salary_min']:.0f}" if item.get("salary_min") else ""
    # salary_is_predicted "1" e chute da Adzuna, nao vale para o piso
    declarado = str(item.get("salary_is_predicted", "1")) == "0"
    teto = item.get("salary_max") or item.get("salary_min")
    return Vaga(
        titulo=item.get("title", ""),
        empresa=(item.get("company") or {}).get("display_name", ""),
        local=(item.get("location") or {}).get("display_name", ""),
        link=item.get("redirect_url", ""),
        fonte="adzuna",
        descricao=item.get("description", ""),
        publicada_em=publicada,
        salario=salario,
        salario_max=float(teto) if declarado and teto else None,
    )


def _buscar(termo: str, pagina: int, app_id: str, app_key: str) -> list[dict]:
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": termo,
        "results_per_page": POR_PAGINA,
        "max_days_old": config.DIAS_MAX_ANUNCIO,
        "content-type": "application/json",
    }
    r = requests.get(
        URL.format(pais=config.PAIS_ADZUNA, pagina=pagina), params=params, timeout=TIMEOUT
    )
    if r.status_code == 401:
        raise RuntimeError("Adzuna recusou as credenciais (401). Confira o App ID e o App Key.")
    r.raise_for_status()
    return r.json().get("results", [])


def coletar() -> list[Vaga]:
    app_id, app_key = _credenciais()
    vagas: list[Vaga] = []

    for termo in config.TERMOS_BUSCA:
        total = 0
        for pagina in range(1, config.PAGINAS_ADZUNA + 1):
            itens = _buscar(termo, pagina, app_id, app_key)
            if not itens:
                break                      # acabaram as paginas desse termo
            total += len(itens)
            vagas.extend(_converter(i) for i in itens)
            if len(itens) < POR_PAGINA:
                break                      # ultima pagina veio incompleta
        print(f"  [adzuna] '{termo}': {total} vagas")

    return vagas


# A API devolve so os primeiros 500 caracteres da descricao, e a modalidade quase
# sempre esta depois disso. A pagina do redirect_url (com os utm_ da propria API)
# abre sem verificacao e traz a vaga inteira num JobPosting em JSON-LD, medido em
# 2026-11-14. Sem os utm_, a mesma pagina cai num desafio anti-robo (405).
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
             "Accept-Language": "pt-BR,pt;q=0.9"}
PAUSA_DETALHE = 1.5


def descricao_da_pagina(pagina: str) -> str:
    import html as _html
    import json as _json
    import re as _re
    for bloco in _re.findall(r'<script type="application/ld\+json">(.*?)</script>', pagina, _re.S):
        try:
            dados = _json.loads(bloco)
        except ValueError:
            continue
        if isinstance(dados, dict) and dados.get("@type") == "JobPosting":
            texto = _re.sub(r"<[^>]+>", " ", _html.unescape(dados.get("description") or ""))
            return _re.sub(r"\s+", " ", texto).strip()
    return ""


def detalhar(vaga: Vaga) -> bool:
    """Troca o trecho da API pela descricao inteira. False se a pagina nao veio."""
    if not vaga.link:
        return False
    r = requests.get(vaga.link, headers=NAVEGADOR, timeout=TIMEOUT)
    if r.status_code != 200:
        return False
    texto = descricao_da_pagina(r.text)
    if len(texto) <= len(vaga.descricao or ""):
        return False
    vaga.descricao = texto[:8000]
    return True
