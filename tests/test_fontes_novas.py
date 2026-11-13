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
    assert "LinkedIn marcou remoto" in v.local
    assert v.link == "https://www.linkedin.com/jobs/view/4489037187"
    assert v.publicada_em.date().isoformat() == "2026-11-11"


def test_linkedin_detalhe_traz_nivel_e_descricao(monkeypatch):
    monkeypatch.setattr(linkedin, "_get", lambda url, params=None: _ler("linkedin_detalhe.html.gz"))
    vaga = Vaga(titulo="x", empresa="", local="", link="", fonte="linkedin",
                extras={"linkedin_id": "1"})
    linkedin.detalhar(vaga)
    assert vaga.descricao.startswith("Nível de experiência: Pleno-sênior")
    assert "INDI" in vaga.descricao


def test_linkedin_429_encerra_sem_erro(monkeypatch):
    def limitado(url, params=None):
        raise linkedin.Limitado()
    monkeypatch.setattr(linkedin, "_get", limitado)
    monkeypatch.setattr(linkedin, "PAUSA", 0)
    assert linkedin.coletar() == []


def test_linkedin_nao_afirma_remoto_na_coleta():
    vagas = linkedin._cards(_ler("linkedin_busca.html.gz"), remoto=True)
    assert all("a confirmar" in v.local for v in vagas)
    assert all(not v.local.lower().startswith("remoto") for v in vagas)


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


def test_vagascom_403_pula_so_a_url(monkeypatch):
    class R:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

        def raise_for_status(self):
            pass
    pagina = _ler("vagascom.html.gz")
    monkeypatch.setattr(vagascom.requests, "get",
                        lambda url, **kw: R(403) if "vagas-de-" in url else R(200, pagina))
    monkeypatch.setattr(vagascom, "PAUSA", 0)
    monkeypatch.setattr(config, "TERMOS_VAGASCOM", ["dados"])
    monkeypatch.setattr(config, "CIDADES_VAGASCOM", ["Caxias do Sul RS"])
    assert len(vagascom.coletar()) == 40


# ------------------------------------------------------------------ enriquecimento no ciclo
def test_enriquecer_derruba_hibrido_e_adia_sem_descricao(monkeypatch):
    import main
    import filtro
    gravadas = []
    monkeypatch.setattr(main.db, "registrar", lambda con, v, notificada: gravadas.append(v.titulo))
    monkeypatch.setattr(main.linkedin, "PAUSA", 0)
    monkeypatch.setattr(config, "LINKEDIN_DETALHES", 2)
    textos = {"1": "Modelo de trabalho: hibrido, 3x na semana.", "2": "Vaga 100% remota."}

    def detalhar(v):
        v.descricao = textos[v.extras["linkedin_id"]]
    monkeypatch.setattr(main.linkedin, "detalhar", detalhar)

    def nova(i):
        v = Vaga(titulo=f"Analista de Dados {i}", empresa="X",
                 local="São Paulo, SP (LinkedIn marcou remoto, a confirmar)",
                 link=f"https://l/{i}", fonte="linkedin", extras={"linkedin_id": str(i)},
                 publicada_em=datetime.now(timezone.utc))
        assert filtro.avaliar(v)
        return v
    novas = [nova(1), nova(2), nova(3)]
    registros = []
    ficam, _ = main.enriquecer_linkedin(None, novas, [], registros)
    assert [v.titulo for v in ficam] == ["Analista de Dados 2"]   # 1 hibrida, 3 sem cota
    assert gravadas == ["Analista de Dados 1"]                     # a 3 volta no proximo ciclo
