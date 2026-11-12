"""Vagas.com.br: HTML da lista de busca. Sem API publica.

Formato medido em 2026-11-12: cada vaga e um <li class="vaga ...">, com o titulo no
atributo title do link "link-detalhes-vaga", empresa em "emprVaga", nivel em
"nivelVaga", trecho da descricao em "detalhes", cidade em "vaga-local", data
relativa em "data-publicacao" ("Hoje", "Ontem", "Ha 3 dias") e o selo
"Exclusivo para PCD" em "vaga-pne". 40 vagas por pagina.
O filtro m[]=100% Home Office vem da propria pagina. Busca e por qualquer palavra,
entao vem muito ruido: o filtro de titulo do radar e que separa.
"""
import html
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

import config
from vaga import Vaga

BASE = "https://www.vagas.com.br"
TIMEOUT = 25
PAUSA = 2.0
CABECALHO = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
             "Accept-Language": "pt-BR,pt;q=0.9"}


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def _limpo(trecho: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", trecho))).strip()


def _data(texto: str, agora: datetime) -> datetime | None:
    t = texto.lower()
    if "hoje" in t:
        return agora
    if "ontem" in t:
        return agora - timedelta(days=1)
    m = re.search(r"(\d+)\s+dias?", t)
    if m:
        return agora - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
    return None


def _vagas(pagina: str, remoto: bool) -> list[Vaga]:
    agora = datetime.now(timezone.utc)
    vagas = []
    for bloco in re.findall(r'<li class="vaga[^"]*">(.*?)</li>\s*(?=<li class="vaga|</ul>)',
                            pagina, re.S):
        link = re.search(r'class="link-detalhes-vaga"[^>]*title="([^"]+)"[^>]*href="([^"]+)"',
                         bloco, re.S)
        if not link:
            continue

        def campo(classe):
            m = re.search(rf'class="{classe}[^"]*"[^>]*>(.*?)</(?:span|div|p)>', bloco, re.S)
            return _limpo(m.group(1)) if m else ""

        local_m = re.search(r'class="vaga-local">(.*?)<div', bloco, re.S)
        local = _limpo(local_m.group(1)) if local_m else campo("vaga-local")
        pcd = "Exclusivo para PCD" if 'class="vaga-pne"' in bloco else ""
        nivel = campo("nivelVaga")
        vagas.append(Vaga(
            titulo=html.unescape(link.group(1)).strip(),
            empresa=campo("emprVaga"),
            local=f"Remoto ({local})" if remoto else local,
            link=BASE + link.group(2).split("?")[0],
            fonte="vagascom",
            descricao=f"Nivel: {nivel}. {pcd}\n{campo('detalhes')}".strip(),
            publicada_em=_data(campo("data-publicacao"), agora),
        ))
    return vagas


def _get(caminho: str, params: dict | None = None) -> str | None:
    r = requests.get(BASE + caminho, params=params, headers=CABECALHO, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for termo in config.TERMOS_VAGASCOM:
        pagina = _get(f"/vagas-de-{_slug(termo)}",
                      {"m[]": "100% Home Office", "ordenar_por": "mais_recentes"})
        achadas = _vagas(pagina, remoto=True) if pagina else []
        vagas.extend(achadas)
        print(f"  [vagascom] remoto '{termo}': {len(achadas)} vagas")
        time.sleep(PAUSA)
    for cidade in config.CIDADES_VAGASCOM:
        pagina = _get(f"/vagas-em-{_slug(cidade)}", {"ordenar_por": "mais_recentes"})
        achadas = _vagas(pagina, remoto=False) if pagina else []
        vagas.extend(achadas)
        print(f"  [vagascom] cidade '{cidade}': {len(achadas)} vagas")
        time.sleep(PAUSA)
    return vagas
