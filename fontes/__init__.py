"""Cada fonte expoe coletar() -> list[Vaga] e nunca derruba o ciclo sozinha."""
from fontes.adzuna import coletar as adzuna
from fontes.boards import coletar as boards
from fontes.google import coletar as google
from fontes.gupy import coletar as gupy
from fontes.himalayas import coletar as himalayas
from fontes.linkedin import coletar as linkedin
from fontes.solides import coletar as solides
from fontes.vagascom import coletar as vagascom

# RemoteOK, Jobicy e Remotive sairam em nov/2026: zero vagas aprovadas em 14 dias e
# muito ruido. Os modulos continuam na pasta; para religar, e so importar e listar.
TODAS = {
    "gupy": gupy,
    "linkedin": linkedin,
    "adzuna": adzuna,
    "vagascom": vagascom,
    "solides": solides,
    "google": google,
    "boards": boards,
    "himalayas": himalayas,
}
