"""Cada fonte expoe coletar() -> list[Vaga] e nunca derruba o ciclo sozinha."""
from fontes.adzuna import coletar as adzuna
from fontes.gupy import coletar as gupy
from fontes.remotive import coletar as remotive
from fontes.remoteok import coletar as remoteok
from fontes.boards import coletar as boards

TODAS = {
    "gupy": gupy,
    "adzuna": adzuna,
    "remotive": remotive,
    "remoteok": remoteok,
    "boards": boards,
}
