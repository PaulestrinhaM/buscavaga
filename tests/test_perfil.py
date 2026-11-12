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
