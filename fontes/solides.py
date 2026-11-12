"""Solides Vagas: dados embutidos na pagina (Next.js), sem API publica.

Formato medido em 2026-11-12: a pagina de busca carrega, dentro de
self.__next_f.push(...), um objeto "initialData" com {totalPages, currentPage,
count, data: [...]}, 14 vagas por pagina. Cada vaga traz title, companyName,
city.name, state.code, homeOffice, jobType ("presencial" | "hibrido" | ...),
seniority [{name}], createdAt (AAAA-MM-DD), initialRange/finalRange (salario),
pcdOnly, slug e id. A descricao vem como referencia ("$1e") a outro trecho.
A busca por texto e muito solta (traz analista de RH para "analista de dados"):
por isso a fonte so e usada por cidade da regiao, e o titulo e filtrado depois.
"""
import json
import re
import time
from datetime import datetime, timezone

import requests

import config
from vaga import Vaga

BASE = "https://vagas.solides.com.br"
TIMEOUT = 25
PAUSA = 2.0
CABECALHO = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
             "Accept-Language": "pt-BR,pt;q=0.9"}


def _payload(pagina_html: str) -> str:
    partes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', pagina_html, re.S)
    return "".join(json.loads(f'"{p}"') for p in partes)


def _textos(payload: str) -> dict[str, str]:
    """Trechos referenciados ("$1e" -> texto). Formato: '\\n1e:T6c2,<texto de 0x6c2 bytes>'."""
    textos = {}
    for m in re.finditer(r"(?:^|\n)([0-9a-f]+):T([0-9a-f]+),", payload):
        tamanho = int(m.group(2), 16)
        bruto = payload[m.end():].encode("utf-8")[:tamanho].decode("utf-8", "ignore")
        textos[f"${m.group(1)}"] = re.sub(r"<[^>]+>", " ", bruto)
    return textos


def _dados(pagina_html: str) -> list[dict]:
    payload = _payload(pagina_html)
    i = payload.find('"initialData":')
    if i < 0:
        return []
    inicial, _ = json.JSONDecoder().raw_decode(payload, i + len('"initialData":'))
    textos = _textos(payload)
    itens = inicial.get("data") or []
    for item in itens:
        desc = item.get("description") or ""
        item["_descricao"] = textos.get(desc, desc if not desc.startswith("$") else "")
    return itens


def _converter(item: dict) -> Vaga:
    cidade = (item.get("city") or {}).get("name") or ""
    uf = (item.get("state") or {}).get("code") or ""
    tipo = item.get("jobType") or ""
    if item.get("homeOffice") or tipo == "remoto":
        local = "Remoto"
    else:
        local = f"{cidade}, {uf} ({tipo})".strip(", ")
    niveis = ", ".join(s.get("name", "") for s in item.get("seniority") or [])
    pcd = "Vaga exclusiva para PcD. " if item.get("pcdOnly") else ""
    publicada = None
    if item.get("createdAt"):
        try:
            publicada = datetime.fromisoformat(str(item["createdAt"])[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    teto = item.get("finalRange") or item.get("initialRange")
    return Vaga(
        titulo=(item.get("title") or "").strip(),
        empresa=item.get("companyName") or "",
        local=local,
        link=f"https://{item.get('slug')}.vagas.solides.com.br/vaga/{item.get('id')}",
        fonte="solides",
        descricao=f"{pcd}Nivel: {niveis or 'nao informado'}.\n{item.get('_descricao', '')}"[:8000],
        publicada_em=publicada,
        salario_max=float(teto) if isinstance(teto, (int, float)) and teto > 0 else None,
    )


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for caminho in config.CIDADES_SOLIDES:
        achadas: list[Vaga] = []
        for pagina in range(1, config.PAGINAS_SOLIDES + 1):
            r = requests.get(f"{BASE}/vagas/todas/{caminho}", params={"page": pagina},
                             headers=CABECALHO, timeout=TIMEOUT)
            if r.status_code == 404:
                break
            r.raise_for_status()
            itens = _dados(r.text)
            time.sleep(PAUSA)
            novas = [_converter(i) for i in itens]
            # pagina repetida: o parametro de pagina foi ignorado
            if not novas or (achadas and novas[0].link == achadas[0].link):
                break
            achadas.extend(novas)
        vagas.extend(achadas)
        print(f"  [solides] '{caminho}': {len(achadas)} vagas")
    return vagas
