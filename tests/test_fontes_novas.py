"""Parsers das fontes novas contra paginas reais capturadas em 2026-11-12."""
import gzip
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from vaga import Vaga

FIX = Path(__file__).parent / "fixtures"
linkedin = importlib.import_module("fontes.linkedin")
vagascom = importlib.import_module("fontes.vagascom")
solides = importlib.import_module("fontes.solides")
google = importlib.import_module("fontes.google")
boards = importlib.import_module("fontes.boards")


def _ler(nome):
    return gzip.open(FIX / nome, "rt", encoding="utf-8").read()


# ------------------------------------------------------------------ linkedin
def test_linkedin_le_os_cards_da_busca():
    vagas = linkedin._cards(_ler("linkedin_busca.html.gz"), remoto=True)
    assert len(vagas) == 10
    v = vagas[1]
    assert v.titulo == "Analista de Dados - Trabalho Remoto"
    assert v.empresa == "BairesDev"
    assert v.local.startswith("Remoto")
    assert v.link == "https://www.linkedin.com/jobs/view/4489037187"
    assert v.publicada_em.date().isoformat() == "2026-11-11"


def test_linkedin_detalhe_traz_nivel_e_descricao(monkeypatch):
    monkeypatch.setattr(linkedin, "_get", lambda url, params=None: _ler("linkedin_detalhe.html.gz"))
    vaga = Vaga(titulo="x", empresa="", local="", link="", fonte="linkedin",
                extras={"linkedin_id": "1"})
    linkedin._detalhar(vaga)
    assert vaga.descricao.startswith("Nível de experiência: Pleno-sênior")
    assert "INDI" in vaga.descricao


def test_linkedin_429_encerra_sem_erro(monkeypatch):
    def limitado(url, params=None):
        raise linkedin.Limitado()
    monkeypatch.setattr(linkedin, "_get", limitado)
    monkeypatch.setattr(linkedin, "PAUSA", 0)
    assert linkedin.coletar() == []


def test_linkedin_so_busca_descricao_de_titulo_que_passa(monkeypatch):
    busca = _ler("linkedin_busca.html.gz")
    detalhes = []

    def get(url, params=None):
        if "jobPosting" in url:
            detalhes.append(url)
            return "<div></div>"
        return busca if params.get("start") == 0 else ""
    monkeypatch.setattr(linkedin, "_get", get)
    monkeypatch.setattr(linkedin, "PAUSA", 0)
    monkeypatch.setattr(config, "TERMOS_LINKEDIN", ["analista de dados"])
    monkeypatch.setattr(config, "TERMOS_LINKEDIN_REGIAO", [])
    vagas = linkedin.coletar()
    assert len(vagas) == 10
    # "Talent Data Analyst", "Analista de Dados", "Data Analyst (Azure...)" etc. passam;
    # nem todo card da pagina vira chamada de detalhe
    assert 0 < len(detalhes) <= config.LINKEDIN_DETALHES


# ------------------------------------------------------------------ vagas.com
def test_vagascom_le_a_lista():
    vagas = vagascom._vagas(_ler("vagascom.html.gz"), remoto=False)
    assert len(vagas) == 40
    v = vagas[0]
    assert v.titulo == "Analista Administrativo Crédito e Cobrança - Pcd"
    assert v.empresa == "GrupoSC"
    assert v.local == "São Paulo / SP"
    assert v.link.startswith("https://www.vagas.com.br/vagas/v2842872/")
    assert "Exclusivo para PCD" in v.descricao
    assert v.publicada_em is not None


def test_vagascom_selo_pcd_bloqueia_no_filtro():
    import filtro
    v = vagascom._vagas(_ler("vagascom.html.gz"), remoto=True)[0]
    assert filtro.bloqueada(v) and "afirmativa" in filtro.bloqueada(v)


def test_vagascom_datas_relativas():
    agora = datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert vagascom._data("Hoje", agora) == agora
    assert vagascom._data("Ontem", agora) == agora - timedelta(days=1)
    assert vagascom._data("Há 3 dias", agora) == agora - timedelta(days=3)
    assert vagascom._data("05/11/2026", agora).day == 5


# ------------------------------------------------------------------ solides
def test_solides_extrai_vagas_do_payload():
    itens = solides._dados(_ler("solides.html.gz"))
    assert len(itens) == 14
    v = solides._converter(itens[0])
    assert v.titulo == "Analista de Planejamento de Produção PL/SR"
    assert v.local == "Santa Isabel, SP (presencial)"
    assert v.link == "https://gestamp.vagas.solides.com.br/vaga/952431"
    assert "Pleno, Sênior" in v.descricao
    assert "Planejar e programar a produção" in v.descricao
    assert v.publicada_em.date().isoformat() == "2026-11-12"


def test_solides_pcd_e_home_office():
    v = solides._converter({"title": "Analista de Dados", "homeOffice": True, "pcdOnly": True,
                            "slug": "x", "id": 1, "createdAt": "2026-11-12"})
    assert v.local == "Remoto"
    assert "exclusiva para PcD" in v.descricao


# ------------------------------------------------------------------ google
def test_google_sem_chave_fica_desligado(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    assert google.coletar(forcar=True) == []


def test_google_converte_item():
    agora = datetime(2026, 11, 12, tzinfo=timezone.utc)
    v = google._converter({
        "title": "Analista de Dados Jr", "company_name": "ACME", "location": "Qualquer lugar",
        "description": "SQL e Python", "via": "LinkedIn",
        "detected_extensions": {"posted_at": "há 3 dias", "work_from_home": True},
        "apply_options": [{"title": "LinkedIn", "link": "https://exemplo/vaga"}],
    }, agora)
    assert v.local.startswith("Remoto")
    assert v.link == "https://exemplo/vaga"
    assert v.publicada_em == agora - timedelta(days=3)


def test_google_so_roda_no_primeiro_turno():
    manha = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)    # 07h em Brasilia
    noite = datetime(2026, 11, 12, 22, tzinfo=timezone.utc)    # 19h em Brasilia
    assert google._hora_de_rodar(manha)
    assert not google._hora_de_rodar(noite)


# ------------------------------------------------------------------ boards
def test_greenhouse_usa_first_published_e_tira_html():
    dados = {"jobs": [{"title": "Analista de Dados", "location": {"name": "Remoto"},
                       "absolute_url": "https://x", "first_published": "2026-11-10T12:00:00Z",
                       "updated_at": "2026-11-12T12:00:00Z",
                       "content": "&lt;p&gt;SQL &amp;amp; Python&lt;/p&gt;"}]}
    v = next(boards._greenhouse("stone", dados))
    assert v.publicada_em.day == 10
    assert v.descricao == "SQL & Python"


def test_ashby_marca_remoto():
    dados = {"jobs": [{"title": "Data Analyst", "location": "São Paulo", "isRemote": True,
                       "jobUrl": "https://x", "publishedAt": "2026-11-10T12:00:00Z"}]}
    v = next(boards._ashby("nubank", dados))
    assert v.local == "Remoto (São Paulo)"
    assert v.publicada_em.day == 10
