"""Gupy: paginacao e as duas buscas (termo remoto e cidade da regiao)."""
import importlib
from datetime import datetime, timedelta, timezone

import config

gupy = importlib.import_module("fontes.gupy")


def _item(i, dias, cidade="", tipo="remote"):
    data = datetime.now(timezone.utc) - timedelta(days=dias)
    return {"name": f"vaga {i}", "careerPageName": "x", "workplaceType": tipo, "city": cidade,
            "publishedDate": data.isoformat(), "jobUrl": f"https://x.gupy.io/job/{i}"}


def _fake(monkeypatch, respostas):
    """respostas: funcao (params, offset) -> lista de itens."""
    chamadas = []

    def buscar(params, offset):
        chamadas.append((dict(params), offset))
        return respostas(params, offset)
    monkeypatch.setattr(gupy, "_buscar", buscar)
    monkeypatch.setattr(gupy, "PAUSA", 0)
    return chamadas


def _so_termo(monkeypatch, termos=("dados",)):
    monkeypatch.setattr(config, "TERMOS_GUPY", list(termos))
    monkeypatch.setattr(config, "CIDADES_GUPY", [])


def test_pagina_cheia_segue_mesmo_com_total_mentiroso(monkeypatch):
    """A API diz total=100 com 200 vagas: o fim e a pagina curta, nao o total."""
    _so_termo(monkeypatch)
    monkeypatch.setattr(config, "PAGINAS_GUPY", 3)
    paginas = {0: [_item(i, 1) for i in range(100)], 100: [_item(i, 2) for i in range(98)]}
    chamadas = _fake(monkeypatch, lambda p, off: paginas.get(off, []))
    assert len(gupy.coletar()) == 198
    assert [off for _, off in chamadas] == [0, 100]


def test_busca_por_termo_pede_so_remoto(monkeypatch):
    _so_termo(monkeypatch)
    chamadas = _fake(monkeypatch, lambda p, off: [])
    gupy.coletar()
    assert chamadas[0][0] == {"jobName": "dados", "workplaceType": "remote"}


def test_para_quando_ultima_vaga_da_pagina_e_velha(monkeypatch):
    _so_termo(monkeypatch)
    monkeypatch.setattr(config, "PAGINAS_GUPY", 5)
    velha = config.DIAS_MAX_ANUNCIO + 5
    pagina = [_item(i, 1) for i in range(99)] + [_item(99, velha)]
    chamadas = _fake(monkeypatch, lambda p, off: pagina)
    gupy.coletar()
    assert len(chamadas) == 1


def test_busca_por_cidade_descarta_o_que_nao_e_da_cidade(monkeypatch):
    """Se a API ignorar o filtro de cidade, volta o Brasil todo: nao pode entrar."""
    monkeypatch.setattr(config, "TERMOS_GUPY", [])
    monkeypatch.setattr(config, "CIDADES_GUPY", ["Bento Gonçalves"])
    itens = [_item(1, 1, "Bento Gonçalves", "on-site"), _item(2, 1, "São Paulo", "hybrid")]
    chamadas = _fake(monkeypatch, lambda p, off: itens)
    vagas = gupy.coletar()
    assert [v.titulo for v in vagas] == ["vaga 1"]
    assert chamadas[0][0] == {"city": "Bento Gonçalves"}


def test_link_aceita_campo_url():
    item = _item(1, 1)
    item.pop("jobUrl")
    item["url"] = "https://x.gupy.io/job/1"
    assert gupy._converter(item).link == "https://x.gupy.io/job/1"


def test_busca_por_cidade_nao_para_pela_data(monkeypatch):
    monkeypatch.setattr(config, "TERMOS_GUPY", [])
    monkeypatch.setattr(config, "CIDADES_GUPY", ["Caxias do Sul"])
    monkeypatch.setattr(config, "PAGINAS_GUPY_CIDADE", 3)
    velha = config.DIAS_MAX_ANUNCIO + 5
    pagina = [_item(i, velha, "Caxias do Sul", "on-site") for i in range(100)]
    chamadas = _fake(monkeypatch, lambda p, off: pagina)
    gupy.coletar()
    assert len(chamadas) == 3
