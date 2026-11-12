"""Cada fonte expoe coletar() -> list[Vaga] e nunca derruba o ciclo sozinha."""
from fontes.adzuna import coletar as adzuna
from fontes.boards import coletar as boards
from fontes.google import coletar as google
from fontes.gupy import coletar as gupy
from fontes.himalayas import coletar as himalayas
from fontes.linkedin import coletar as linkedin
from fontes.solides import coletar as solides

# RemoteOK, Jobicy e Remotive sairam em nov/2026: zero vagas aprovadas em 14 dias e
# muito ruido. Vagas.com ficou pronto mas desligado: a busca por termo responde 403
# para o IP do Actions e as paginas de cidade trouxeram 11 vagas, nenhuma de dados.
# Os modulos continuam na pasta; para religar, e so listar aqui.
TODAS = {
    "gupy": gupy,
    "linkedin": linkedin,
    "adzuna": adzuna,
    "solides": solides,
    "google": google,
    "boards": boards,
    "himalayas": himalayas,
}
