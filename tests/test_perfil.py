"""Perfil da IA em perfil.md e o lembrete de revisao."""
from datetime import date, datetime, timezone

import main
import triagem


def test_perfil_le_data_e_tira_comentario():
    texto, revisado = triagem._ler_perfil()
    assert isinstance(revisado, date)
    assert "<!--" not in texto and "revisado_em" not in texto
    assert texto.startswith("CANDIDATO:")


def test_perfil_tem_o_que_a_instrucao_usa():
    assert "R$ 4.000" in triagem.PERFIL
    assert "Power BI" in triagem.PERFIL
    assert "PLENO" in triagem.PERFIL


def _rodar_lembrete(monkeypatch, quando, dias):
    avisos = []
    monkeypatch.setattr(triagem, "dias_sem_revisar_perfil", lambda hoje=None: dias)
    monkeypatch.setattr(main.notificador, "alerta", avisos.append)
    main.lembrar_perfil(quando)
    return avisos


def test_lembrete_na_segunda_cedo_com_perfil_velho(monkeypatch):
    segunda_7h = datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc)   # 07h30 em Brasilia
    assert _rodar_lembrete(monkeypatch, segunda_7h, 60)


def test_sem_lembrete_com_perfil_novo_ou_fora_de_hora(monkeypatch):
    segunda_7h = datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc)
    terca_7h = datetime(2026, 11, 17, 10, 30, tzinfo=timezone.utc)
    segunda_18h = datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc)
    assert not _rodar_lembrete(monkeypatch, segunda_7h, 10)
    assert not _rodar_lembrete(monkeypatch, terca_7h, 60)
    assert not _rodar_lembrete(monkeypatch, segunda_18h, 60)


# ------------------------------------------------ veredito: regras aplicadas em codigo
from vaga import Vaga  # noqa: E402


def _vaga(local="Remoto"):
    return Vaga(titulo="x", empresa="", local=local, link="", fonte="t", score=4)


def test_crm_com_nota_10_vira_6():
    v = _vaga()
    vale, _ = triagem.aplicar_veredito(v, {"vale": True, "area": "operacoes_tecnicas", "nota": 10})
    assert vale and v.score == 6


def test_dados_mantem_a_nota():
    v = _vaga()
    triagem.aplicar_veredito(v, {"vale": True, "area": "dados", "nota": 9})
    assert v.score == 9


def test_marketing_e_outra_caem_mesmo_com_vale_true():
    for area in ("marketing", "outra"):
        vale, motivo = triagem.aplicar_veredito(_vaga(), {"vale": True, "area": area, "nota": 10})
        assert not vale and area in motivo


def test_hibrido_cai_fora_da_regiao_e_passa_na_regiao():
    hib = {"vale": True, "area": "dados", "modalidade": "hibrido", "nota": 8}
    assert not triagem.aplicar_veredito(_vaga("São Paulo, SP"), hib)[0]
    assert triagem.aplicar_veredito(_vaga("Caxias do Sul, RS"), hib)[0]


def test_destaques_traz_modalidade_e_salario_do_fim_do_anuncio():
    desc = "Sobre nos. " * 400 + "Modelo de trabalho: hibrido, 3x na semana. Salario: R$ 5.000."
    d = triagem.destaques(desc)
    assert "hibrido" in d and "R$ 5.000" in d
