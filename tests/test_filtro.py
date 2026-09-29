"""Cada caso aqui documenta uma decisao de filtro, nao um cenario hipotetico."""
from datetime import datetime, timedelta, timezone

import pytest

import filtro
from vaga import Vaga


def v(titulo, local="Remoto", empresa="Empresa", descricao="", dias=1):
    return Vaga(
        titulo=titulo, empresa=empresa, local=local, link=f"http://x/{titulo}",
        fonte="teste", descricao=descricao,
        publicada_em=datetime.now(timezone.utc) - timedelta(days=dias),
    )


# --------------------------------------------------- nivel 1: cargo forte
@pytest.mark.parametrize("titulo", [
    "Analista de Dados Junior",
    "Pessoa Engenheira de Dados Junior",
    "Analista de BI",
    "Marketing Operations Analyst",
    "Revenue Operations",
    "Data Engineer",
])
def test_cargo_forte_aprova_sozinho(titulo):
    vaga = v(titulo)
    assert filtro.avaliar(vaga)
    assert vaga.nivel_confianca == "alta"


# --------------------------------------------------- nivel 2: ambiguo + qualificador
def test_ambiguo_sem_qualificador_reprova():
    assert not filtro.avaliar(v("Business Analyst"))


def test_ambiguo_com_qualificador_aprova():
    vaga = v("Business Analyst de Dados")
    assert filtro.avaliar(vaga)
    assert vaga.nivel_confianca == "media"


def test_analista_puro_reprova():
    assert not filtro.avaliar(v("Analista Junior"))


# --------------------------------------------------- nivel 3: ferramenta + cargo
def test_ferramenta_sozinha_reprova():
    assert not filtro.avaliar(v("Power BI"))


def test_ferramenta_com_cargo_aprova():
    vaga = v("Desenvolvedor Python")
    assert filtro.avaliar(vaga)
    assert vaga.nivel_confianca == "media"


# --------------------------------------------------- bloqueios
@pytest.mark.parametrize("titulo", [
    "Analista de Dados Senior",
    "Coordenador de Dados",
    "Head of Data",
    "Tech Lead de Dados",
])
def test_senioridade_acima_do_alvo_bloqueia(titulo):
    assert not filtro.avaliar(v(titulo))


def test_anuncio_velho_bloqueia():
    assert not filtro.avaliar(v("Analista de Dados", dias=60))


def test_ruido_de_board_bloqueia():
    assert not filtro.avaliar(v("Vendedor de Dados Cadastrais"))


# --------------------------------------------------- localizacao
def test_local_fora_do_alvo_reprova():
    assert not filtro.avaliar(v("Analista de Dados", local="Sao Paulo, SP"))


def test_cidade_alvo_aprova():
    assert filtro.avaliar(v("Analista de Dados", local="Caxias do Sul, RS"))


def test_remoto_aprova():
    assert filtro.avaliar(v("Analista de Dados", local="100% remoto"))


# --------------------------------------------------- score
def test_junior_remoto_pontua_mais_que_sem_nivel_presencial():
    jr = v("Analista de Dados Junior", local="Remoto")
    outro = v("Analista de Dados", local="Caxias do Sul, RS")
    filtro.avaliar(jr)
    filtro.avaliar(outro)
    assert jr.score > outro.score


def test_pleno_nao_pontua_mais():
    """Pleno deixou de ser alvo: Junior/Pleno pontua como junior, nao como pleno."""
    import config
    assert "pleno" not in config.PESOS


def test_ferramentas_no_texto_somam_ate_tres():
    # cargo de confianca media, longe do teto, para medir so o efeito das ferramentas
    sem = v("Business Analyst de Dados")
    com = v("Business Analyst de Dados", descricao="SQL, Python, Airflow, dbt, Looker")
    filtro.avaliar(sem)
    filtro.avaliar(com)
    assert com.score - sem.score == 3


def test_score_nunca_passa_de_dez():
    vaga = v("Analista de Dados Junior", local="Remoto",
             descricao="SQL Python Airflow dbt Looker Databricks")
    filtro.avaliar(vaga)
    assert vaga.score <= 10


# --------------------------------------------------- identidade e dedup
def test_mesma_vaga_em_fontes_diferentes_tem_mesmo_id_de_conteudo():
    a = Vaga("Analista de Dados", "ACME", "Remoto", "http://a/1", "adzuna")
    b = Vaga("analista de dados", "acme", "Remoto", "http://b/2", "remotive")
    assert a.id_conteudo == b.id_conteudo
    assert a.id != b.id


def test_query_string_nao_cria_vaga_nova():
    a = Vaga("X", "ACME", "Remoto", "http://a/1", "adzuna")
    b = Vaga("X", "ACME", "Remoto", "http://a/1?utm_source=linkedin", "adzuna")
    assert a.id == b.id


# --------------------------------------------------- dedup dentro do ciclo
def test_dedup_no_mesmo_ciclo(tmp_path, monkeypatch):
    """Mesma vaga em duas fontes, antes de qualquer gravacao, conta uma vez."""
    import db as _db
    import main as _main
    import fontes as _fontes

    monkeypatch.setattr(_db, "CAMINHO", tmp_path / "t.db")
    # sem rede: o .env local tem credenciais reais de Telegram e Gemini
    monkeypatch.setattr(_main.notificador, "vaga_urgente", lambda vaga: True)
    monkeypatch.setattr(_main.notificador, "alerta", lambda texto: True)
    monkeypatch.setattr(_main.triagem, "triar", lambda vagas: (vagas, [], []))
    monkeypatch.setattr("time.sleep", lambda s: None)
    import auditoria as _auditoria
    monkeypatch.setattr(_auditoria, "PASTA", tmp_path / "saida")

    agora = datetime.now(timezone.utc)

    def falsa():
        return [
            Vaga("Analista de Dados Junior", "ACME", "Remoto", "http://a/1", "f1",
                 publicada_em=agora),
            Vaga("analista de dados junior", "acme", "Remoto", "http://b/9", "f2",
                 publicada_em=agora),
        ]

    monkeypatch.setattr(_main, "TODAS", {"falsa": falsa})
    con = _db.conectar()
    r = _main.rodar_ciclo(con)
    con.close()
    assert r["aprovadas"] == 2
    assert r["novas"] == 1


# --------------------------------------------------- regiao em fonte internacional
def test_restrito_a_outro_pais_reprova():
    assert not filtro.avaliar(v("Data Analyst", local="USA Only"))
    assert not filtro.avaliar(v("Data Engineer", local="Europe Only"))


def test_worldwide_aprova():
    assert filtro.avaliar(v("Data Analyst", local="Worldwide"))


def test_brasil_em_fonte_internacional_aprova():
    assert filtro.avaliar(v("Data Engineer", local="Brazil"))


def test_latam_aprova():
    assert filtro.avaliar(v("Data Analyst", local="LATAM"))


# --------------------------------------------------- bloqueio por palavra inteira
def test_head_nao_casa_dentro_de_outra_palavra():
    """'head' bloqueia 'Head of Data', nao pode bloquear 'Headless CMS'."""
    assert filtro.avaliar(v("Analista de Dados Headless CMS"))
    assert not filtro.avaliar(v("Head of Data"))


def test_sr_isolado_bloqueia_mas_nao_dentro_de_palavra():
    assert not filtro.avaliar(v("Analista de Dados Sr"))
    assert filtro.avaliar(v("Analista de Dados Srisk"))


# --------------------------------------------------- remoto declarado so na descricao
def test_remoto_na_descricao_aprova_mesmo_com_cidade_no_local():
    vaga = v("Analista de Dados", local="Sao Paulo, SP",
             descricao="Vaga 100% remota, atuacao em home office")
    assert filtro.avaliar(vaga)


def test_cidade_sem_mencao_a_remoto_continua_reprovando():
    vaga = v("Analista de Dados", local="Sao Paulo, SP",
             descricao="Atuacao presencial no escritorio da Faria Lima")
    assert not filtro.avaliar(vaga)


# --------------------------------------------------- senioridade no corpo do anuncio
def test_senioridade_na_descricao_bloqueia():
    assert not filtro.avaliar(v("Analista de Dados", descricao="Vaga senior, time de dados"))
    assert not filtro.avaliar(v("Analista de Dados", descricao="Experiencia minima de 5 anos"))


def test_mencao_a_gerente_na_descricao_nao_bloqueia():
    """Reportar a um gerente nao torna a vaga senior."""
    assert filtro.avaliar(v("Analista de Dados", descricao="Reporta ao gerente de BI"))


# --------------------------------------------------- remoto exige expressao forte
def test_palavra_remoto_solta_na_descricao_nao_aprova():
    vaga = v("Analista de Dados", local="Curitiba, PR",
             descricao="O time remoto de outra area nao se aplica aqui")
    assert not filtro.avaliar(vaga)


def test_expressao_forte_de_remoto_aprova():
    vaga = v("Analista de Dados", local="Curitiba, PR", descricao="Vaga 100% remoto")
    assert filtro.avaliar(vaga)


def test_presencial_explicito_vence_mencao_a_remoto():
    vaga = v("Analista de Dados", local="Curitiba, PR",
             descricao="Trabalho remoto durante treinamento, depois presencial no escritorio")
    assert not filtro.avaliar(vaga)


# --------------------------------------------------- sem data
def test_sem_data_de_publicacao_bloqueia():
    vaga = Vaga("Analista de Dados", "X", "Remoto", "http://x/1", "t")
    assert not filtro.avaliar(vaga)
    assert "sem data" in vaga.motivo


# --------------------------------------------------- hibrido fora da regiao
def test_hibrido_em_outra_cidade_reprova():
    assert not filtro.avaliar(v("Analista de Dados - Hibrido", local="Sao Paulo, SP"))
    assert not filtro.avaliar(v("Analista de Dados", local="Hibrido - Sao Paulo"))


def test_hibrido_na_regiao_aprova():
    assert filtro.avaliar(v("Analista de Dados - Hibrido", local="Caxias do Sul, RS"))


# --------------------------------------------------- regiao: so Caxias e vizinhas
def test_hibrido_em_porto_alegre_reprova():
    """Porto Alegre saiu da regiao: hibrido la nao serve."""
    assert not filtro.avaliar(v("Analista de Dados Hibrido", local="Porto Alegre, RS"))
    # formato do campo de local da Gupy
    assert not filtro.avaliar(v("Analista de Dados",
                                local="Porto Alegre, Rio Grande do Sul (hybrid)"))


def test_presencial_em_porto_alegre_reprova():
    assert not filtro.avaliar(v("Analista de Dados", local="Porto Alegre, RS"))


def test_rs_fora_da_regiao_reprova():
    """Estar no RS nao basta: Novo Hamburgo e Sao Leopoldo tambem sairam."""
    assert not filtro.avaliar(v("Analista de Dados", local="Novo Hamburgo, RS"))
    assert not filtro.avaliar(v("Analista de Dados", local="Sao Leopoldo, Rio Grande do Sul"))


@pytest.mark.parametrize("local", [
    "Caxias do Sul, RS", "Farroupilha, RS", "Bento Goncalves, RS",
    "Flores da Cunha, RS", "Sao Marcos, RS", "Garibaldi, RS",
])
def test_qualquer_modalidade_na_regiao_aprova(local):
    assert filtro.avaliar(v("Analista de Dados", local=f"{local} (on-site)"))
    assert filtro.avaliar(v("Analista de Dados Hibrido", local=local))


def test_remoto_em_qualquer_lugar_do_brasil_aprova():
    assert filtro.avaliar(v("Analista de Dados, 100% remoto", local="Sao Paulo, SP"))


def test_hibrido_no_local_vence_home_office_na_descricao():
    """'Auxilio home office' na descricao nao torna remota uma vaga hibrida."""
    vaga = v("Analista de Dados", local="Sao Paulo, Sao Paulo (hybrid)",
             descricao="Beneficios: auxilio home office, VR")
    assert not filtro.avaliar(vaga)


def test_hibrido_na_descricao_vence_remoto_na_descricao():
    vaga = v("Analista de Dados", local="Curitiba, PR",
             descricao="Trabalho remoto 3x por semana, modelo hibrido")
    assert not filtro.avaliar(vaga)


# --------------------------------------------------- pleno
@pytest.mark.parametrize("titulo", [
    "Digital Analytics Pleno",
    "Analista de Dados Pl",
    "Data Analyst Mid-level",
    "Data Analyst Mid Level",
    "Analista de Dados Plena",
])
def test_pleno_sem_junior_bloqueia(titulo):
    vaga = v(titulo)
    assert not filtro.avaliar(vaga)
    assert "senioridade" in vaga.motivo


@pytest.mark.parametrize("titulo", [
    "Analista de Dados Junior/Pleno",
    "Analista de Dados Jr/Pl",
    "Analista de Dados Pleno ou Junior",
    "Analista de Dados Jr. / Pleno",
])
def test_pleno_junto_com_junior_passa(titulo):
    assert filtro.avaliar(v(titulo))


@pytest.mark.parametrize("titulo", [
    "Analista de Dados Especialista",
    "Data Analyst Specialist",
])
def test_especialista_em_dados_bloqueia(titulo):
    """Na trilha Jr > Pl > Sr > Especialista, especialista fica acima de senior."""
    vaga = v(titulo)
    assert not filtro.avaliar(vaga)
    assert "senioridade" in vaga.motivo


# --------------------------------------------------- senioridade por trilha
@pytest.mark.parametrize("titulo", [
    "Digital Analytics Pleno",
    "Engenheiro de Dados Pleno",
    "Analista de BI Pl",
    # titulo misto fica com a regra mais estrita
    "Analista de Dados e CRM Pleno",
    # aprovada por cargo ambiguo, sem trilha: regra de dados
    "Business Analyst de Dados Pleno",
])
def test_trilha_dados_descarta_pleno(titulo):
    assert not filtro.avaliar(v(titulo))


@pytest.mark.parametrize("titulo", [
    "Analista de CRM Pleno",
    "Marketing Operations Pleno",
    "Revenue Operations Analyst Mid-level",
    "Analista de Integracao de Sistemas Pl",
    "Especialista em CRM",
])
def test_trilha_operacoes_aceita_pleno(titulo):
    vaga = v(titulo)
    assert filtro.avaliar(vaga)
    assert vaga.trilha == "operacoes"


@pytest.mark.parametrize("titulo", [
    "Marketing Operations Senior",
    "Analista de CRM Sr",
    "Coordenador de Revenue Operations",
])
def test_trilha_operacoes_descarta_senior(titulo):
    assert not filtro.avaliar(v(titulo))


def test_junior_prevalece_nas_duas_trilhas():
    dados = v("Analista de Dados Junior/Pleno")
    ops = v("Analista de CRM Jr/Pl")
    assert filtro.avaliar(dados) and dados.trilha == "dados"
    assert filtro.avaliar(ops) and ops.trilha == "operacoes"


# --------------------------------------------------- machine learning fora do escopo
@pytest.mark.parametrize("titulo", [
    "Cientista de Dados Junior",
    "Data Scientist Jr",
    "Machine Learning Engineer",
    "ML Engineer Junior",
    "Engenheiro de Machine Learning",
    "Analista de Dados - Visao Computacional",
    "MLOps Engineer",
])
def test_cargo_de_ml_no_titulo_bloqueia(titulo):
    assert not filtro.avaliar(v(titulo))


def test_ml_na_descricao_de_analista_nao_bloqueia():
    """O corte e por cargo no titulo, nao por tema no corpo."""
    vaga = v("Analista de Dados Junior",
             descricao="Conhecimento em machine learning e diferencial. Deep learning e um plus.")
    assert filtro.avaliar(vaga)


def test_pl_sql_nao_e_pleno():
    assert filtro.avaliar(v("Analista de Dados PL/SQL"))


# --------------------------------------------------- vaga afirmativa exclusiva
@pytest.mark.parametrize("titulo,descricao", [
    ("Analista de Dados - Vaga exclusiva para pessoas negras", ""),
    ("Analista de Dados - Vaga afirmativa para Mulheres", ""),
    ("Analista de Dados - Exclusiva para PcD", ""),
    ("Analista de Dados - Vaga Exclusiva PcD", ""),
    ("Analista de Dados", "Esta vaga e somente para pessoas com deficiencia."),
    ("Analista de Dados", "Requisitos: exclusivo para pessoas com deficiencia e reabilitados INSS"),
    ("Analista de Dados", "Oportunidade destinada exclusivamente a pessoas trans e travestis"),
    ("Analista de Dados", "Vaga restrita a profissionais 50+"),
])
def test_afirmativa_exclusiva_bloqueia(titulo, descricao):
    vaga = v(titulo, descricao=descricao)
    assert not filtro.avaliar(vaga)
    assert "afirmativa" in vaga.motivo


@pytest.mark.parametrize("descricao", [
    "Vaga tambem aberta para PcD",
    "Esta vaga e elegivel para PcD",
    "Incentivamos candidaturas de pessoas negras",
    "Nossa empresa valoriza a diversidade",
    # texto padrao que aparece em muitos anuncios da Gupy
    "Todas as nossas vagas sao exclusivas ou nao para pessoas com deficiencia",
    # beneficio, nao restricao da vaga
    "Auxilio: exclusivos para colaboradores PcDs e reabilitados do INSS",
    "Subsidio apenas para aparelhos relacionados a deficiencia",
    "Afirmativa: para fomentar a diversidade, incentivamos a candidatura de mulheres",
    "Esta vaga nao e exclusiva para PcD",
    # preferencia nao e exclusividade: a vaga segue aberta a todos
    "Preferencialmente para pessoas negras ou pardas",
])
def test_mencao_a_grupo_sem_exclusividade_passa(descricao):
    assert filtro.avaliar(v("Analista de Dados", descricao=descricao))


# --------------------------------------------------- cargo por palavra-chave
@pytest.mark.parametrize("titulo,trilha", [
    # sem o "de", fora de ordem, com palavra no meio
    ("Analista CRM Jr", "operacoes"),
    ("Analista Marketing CRM Pl", "operacoes"),
    ("Analista de Marketing Pleno - CRM", "operacoes"),
    ("Sales / Revenue / CS Operations Expert", "operacoes"),
    # "(a)" nao quebra o cargo, "*" pega genero e variacao
    ("Engenheiro(a) de Dados", "dados"),
    ("Engenheira de Dados Jr", "dados"),
    ("Analista de Engenharia de Dados", "dados"),
    ("Engenharia de Dados (Databricks)", "dados"),
    ("Data & Analytics Analyst", "dados"),
])
def test_cargo_casa_por_palavra_chave(titulo, trilha):
    vaga = v(titulo)
    assert filtro.avaliar(vaga), vaga.motivo
    assert vaga.nivel_confianca == "alta"
    assert vaga.trilha == trilha


@pytest.mark.parametrize("titulo", [
    "Analista de Mobilidade",          # "bi" dentro de "mobilidade"
    "Analista Bilingue",
    "Consultor ABAP / Datasphere",     # "data" dentro de "datasphere"
    "Analista de ContentOps - UX Writer",
    "Analista DevOps",
])
def test_palavra_chave_nao_casa_dentro_de_outra_palavra(titulo):
    assert not filtro.avaliar(v(titulo))


def test_frase_entre_aspas_exige_ordem():
    """'"analytics engineer"' e frase exata: palavras soltas no titulo nao bastam."""
    assert not filtro.avaliar(v("Software Engineer (Lake Analytics Platform)"))
    assert filtro.avaliar(v("Analytics Engineer Jr"))


def test_cargo_mais_especifico_decide_a_trilha():
    """{analista, web, analytics} em operacoes vence {analista, analytics} em dados."""
    vaga = v("Analista de Web Analytics Pleno")
    assert filtro.avaliar(vaga)
    assert vaga.trilha == "operacoes"


def test_hibrida_no_feminino_tambem_e_hibrido():
    vaga = v("Engenheiro de Dados - hibrida em Joinville", local="Joinville, SC",
             descricao="Trabalho remoto parcial")
    assert not filtro.avaliar(vaga)


# --------------------------------------------------- registro do ciclo
def test_toda_vaga_coletada_aparece_uma_vez_no_registro(tmp_path, monkeypatch):
    """Nada some sem explicacao: cada vaga coletada tem uma etapa e um motivo."""
    import csv
    import auditoria
    import db as _db
    import main as _main

    monkeypatch.setattr(_db, "CAMINHO", tmp_path / "t.db")
    monkeypatch.setattr(auditoria, "PASTA", tmp_path / "saida")
    monkeypatch.setattr(_main.notificador, "vaga_urgente", lambda vaga: True)
    monkeypatch.setattr(_main.notificador, "alerta", lambda texto: True)
    monkeypatch.setattr("time.sleep", lambda s: None)

    def triar_falso(vagas):
        for x in vagas:
            if "Engenheiro" in x.titulo:
                x.motivo = "IA: exige AWS"
        return ([x for x in vagas if "Engenheiro" not in x.titulo],
                [x for x in vagas if "Engenheiro" in x.titulo], [])
    monkeypatch.setattr(_main.triagem, "triar", triar_falso)

    agora = datetime.now(timezone.utc)
    def falsa():
        return [
            Vaga("Analista de Dados Junior", "A", "Remoto", "http://a/1", "f", publicada_em=agora),
            Vaga("analista de dados junior", "a", "Remoto", "http://b/1", "f", publicada_em=agora),
            Vaga("Engenheiro de Dados", "B", "Remoto", "http://a/2", "f", publicada_em=agora),
            Vaga("Vendedor", "C", "Remoto", "http://a/3", "f", publicada_em=agora),
        ]
    monkeypatch.setattr(_main, "TODAS", {"falsa": falsa})

    con = _db.conectar()
    _main.rodar_ciclo(con)
    con.close()

    with open(tmp_path / "saida" / "vagas-do-ciclo.csv", encoding="utf-8-sig") as arq:
        linhas = list(csv.DictReader(arq, delimiter=";"))
    etapas = sorted(l["etapa"] for l in linhas)
    assert etapas == sorted([auditoria.ENVIADA_NA_HORA, auditoria.REPETIDA,
                             auditoria.CORTADA_IA, auditoria.DESCARTADA_REGRA])
    cortada = next(l for l in linhas if l["etapa"] == auditoria.CORTADA_IA)
    assert cortada["motivo"] == "IA: exige AWS"


# --------------------------------------------------- IA: cortada nao volta, falha adia
def _ciclo_com_ia(tmp_path, monkeypatch, triar, vagas, adiar=True):
    import auditoria
    import db as _db
    import main as _main

    monkeypatch.setattr(_db, "CAMINHO", tmp_path / "t.db")
    monkeypatch.setattr(auditoria, "PASTA", tmp_path / "saida")
    enviadas, alertas = [], []
    monkeypatch.setattr(_main.notificador, "vaga_urgente", lambda v: enviadas.append(v) or True)
    monkeypatch.setattr(_main.notificador, "alerta", lambda t: alertas.append(t) or True)
    monkeypatch.setattr(_main.triagem, "triar", triar)
    monkeypatch.setattr(_main.config, "ADIAR_SE_IA_FALHAR", adiar)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(_main, "TODAS", {"falsa": lambda: [Vaga(*a, publicada_em=datetime.now(timezone.utc)) for a in vagas]})
    con = _db.conectar()
    _main.rodar_ciclo(con)
    gravadas = {r["titulo"]: r["notificada"] for r in con.execute("SELECT titulo, notificada FROM vagas")}
    con.close()
    return gravadas, enviadas, alertas


def test_vaga_cortada_pela_ia_nao_volta_no_ciclo_seguinte(tmp_path, monkeypatch):
    """Foi o bug de 2026-09-28: a cortada nao era gravada e voltava quando a IA caia."""
    vagas = [("Engenheiro de Dados", "Banco", "Remoto", "http://a/1", "f")]
    cortar = lambda vs: ([], vs, [])
    gravadas, _, _ = _ciclo_com_ia(tmp_path, monkeypatch, cortar, vagas)
    assert gravadas == {"Engenheiro de Dados": -1}

    # segundo ciclo com a IA fora do ar: a vaga ja e conhecida e nao e enviada
    falhar = lambda vs: ([], [], vs)
    _, enviadas, _ = _ciclo_com_ia(tmp_path, monkeypatch, falhar, vagas)
    assert enviadas == []


def test_ia_fora_do_ar_adia_em_vez_de_enviar(tmp_path, monkeypatch):
    vagas = [("Analista de Dados Junior", "A", "Remoto", "http://a/1", "f")]
    falhar = lambda vs: ([], [], vs)
    gravadas, enviadas, alertas = _ciclo_com_ia(tmp_path, monkeypatch, falhar, vagas)
    assert enviadas == []
    assert gravadas == {}              # nao grava: o proximo ciclo tenta de novo
    assert any("IA indisponivel" in a for a in alertas)


# --------------------------------------------------- grupo no titulo
@pytest.mark.parametrize("titulo", [
    "Analista CRM JR - PcD",
    "Analista de Dados I - PcD",
    "Analista de Dados (PCD)",
    "Analista de BI | Vaga Afirmativa",
    "Analista de Dados Jr - Pessoas com Deficiencia",
])
def test_grupo_no_titulo_indica_vaga_exclusiva(titulo):
    vaga = v(titulo)
    assert not filtro.avaliar(vaga)
    assert "afirmativa" in vaga.motivo


@pytest.mark.parametrize("titulo", [
    "Analista de Dados Jr (vaga tambem para PcD)",
    "Analista de Dados - aberta a PcD",
])
def test_grupo_no_titulo_com_ressalva_passa(titulo):
    assert filtro.avaliar(v(titulo))


# --------------------------------------------------- senioridade que escapava
@pytest.mark.parametrize("titulo", [
    "Data Analytics Lead",
    "Lead Analyst - Process Analytics",
    "Digital Marketing Coordinator",
    "VP of Revenue Operations",
    "Data Architect",
    "Arquiteto de Dados",
    "Mid Data Engineer",
    "Analista de Dados II",
])
def test_senioridade_em_ingles_e_nivel_ii_bloqueiam(titulo):
    assert not filtro.avaliar(v(titulo))


# --------------------------------------------------- repescagem pela IA
def test_titulo_vago_sem_bloqueio_vira_repescagem():
    vaga = v("Operacoes de Marketing", local="Remoto")
    assert not filtro.avaliar(vaga)
    assert vaga.repescagem


@pytest.mark.parametrize("titulo,local", [
    ("Operacoes de Marketing Senior", "Remoto"),       # senioridade e rigida
    ("Operacoes de Marketing", "Sao Paulo, SP (hybrid)"),  # local e rigido
    ("Vendedor Interno", "Remoto"),                    # area e rigida
])
def test_bloqueio_rigido_nao_vai_para_repescagem(titulo, local):
    vaga = v(titulo, local=local)
    assert not filtro.avaliar(vaga)
    assert not vaga.repescagem


def test_repescagem_so_e_enviada_com_aval_da_ia(tmp_path, monkeypatch):
    import main as _main
    monkeypatch.setattr(_main.config, "USAR_IA", True)
    monkeypatch.setattr(_main.config, "REPESCAGEM", True)
    vagas = [("Operacoes de Marketing", "A", "Remoto", "http://a/1", "f")]

    vistas = []
    def aprovar(vs):
        vistas.extend(vs)
        for x in vs:
            x.score = 9
        return vs, [], []
    _, enviadas, _ = _ciclo_com_ia(tmp_path, monkeypatch, aprovar, vagas)
    assert [x.titulo for x in vistas] == ["Operacoes de Marketing"]
    assert [x.titulo for x in enviadas] == ["Operacoes de Marketing"]


def test_repescagem_sem_veredito_nunca_sai_pela_regra(tmp_path, monkeypatch):
    import main as _main
    monkeypatch.setattr(_main.config, "USAR_IA", True)
    monkeypatch.setattr(_main.config, "REPESCAGEM", True)
    vagas = [("Operacoes de Marketing", "A", "Remoto", "http://a/1", "f")]
    falhar = lambda vs: ([], [], vs)
    gravadas, enviadas, _ = _ciclo_com_ia(tmp_path, monkeypatch, falhar, vagas, adiar=False)
    assert enviadas == [] and gravadas == {}
