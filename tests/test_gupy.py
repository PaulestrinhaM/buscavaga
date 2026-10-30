"""Paginacao da Gupy: segue o tamanho que a API devolve, nao o limit pedido."""
from datetime import datetime, timedelta, timezone

import config
import importlib
gupy = importlib.import_module("fontes.gupy")


def _item(i, dias):
    data = datetime.now(timezone.utc) - timedelta(days=dias)
    return {"name": f"vaga {i}", "careerPageName": "x", "workplaceType": "remote",
            "publishedDate": data.isoformat(), "url": f"https://x.gupy.io/job/{i}"}


def _fake(paginas, total):
    chamadas = []

    def buscar(termo, offset):
        chamadas.append(offset)
        idx = len(chamadas) - 1
        return (paginas[idx] if idx < len(paginas) else []), total
    return buscar, chamadas


def test_pagina_menor_que_limit_nao_encerra_busca(monkeypatch):
    monkeypatch.setattr(config, "TERMOS_BUSCA", ["dados"])
    monkeypatch.setattr(config, "PAGINAS_GUPY", 2)
    monkeypatch.setattr(gupy, "PAUSA", 0)
    paginas = [[_item(i, 1) for i in range(50)] for _ in range(4)]
    buscar, chamadas = _fake(paginas, total=1000)
    monkeypatch.setattr(gupy, "_buscar", buscar)
    vagas = gupy.coletar()
    assert len(vagas) == 200                 # teto de 2 x 100, em paginas de 50
    assert chamadas == [0, 50, 100, 150]


def test_para_no_total_da_api(monkeypatch):
    monkeypatch.setattr(config, "TERMOS_BUSCA", ["dados"])
    monkeypatch.setattr(gupy, "PAUSA", 0)
    buscar, chamadas = _fake([[_item(i, 1) for i in range(30)]], total=30)
    monkeypatch.setattr(gupy, "_buscar", buscar)
    assert len(gupy.coletar()) == 30
    assert chamadas == [0]


def test_para_quando_pagina_toda_e_velha(monkeypatch):
    monkeypatch.setattr(config, "TERMOS_BUSCA", ["dados"])
    monkeypatch.setattr(config, "PAGINAS_GUPY", 5)
    monkeypatch.setattr(gupy, "PAUSA", 0)
    velha = config.DIAS_MAX_ANUNCIO + 5
    paginas = [[_item(i, 1) for i in range(50)], [_item(i, velha) for i in range(50)],
               [_item(i, 1) for i in range(50)]]
    buscar, chamadas = _fake(paginas, total=1000)
    monkeypatch.setattr(gupy, "_buscar", buscar)
    gupy.coletar()
    assert chamadas == [0, 50]


def test_link_usa_campo_url():
    assert gupy._converter(_item(1, 1)).link == "https://x.gupy.io/job/1"
