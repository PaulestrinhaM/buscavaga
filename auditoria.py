"""Registro de tudo que o ciclo viu, inclusive o que foi descartado e por que.

Nao vai para o banco: sao ~1.500 vagas por dia, e o banco e versionado no Git.
Vira um CSV em saida/ (no GitHub Actions, anexado a execucao por 30 dias) e um
resumo em Markdown que aparece na pagina da execucao, na aba Actions.
"""
import csv
import os
from collections import Counter
from pathlib import Path

PASTA = Path(__file__).parent / "saida"

# Etapa em que a vaga parou, na ordem do fluxo.
ENVIADA_NA_HORA = "enviada na hora"
RESUMO = "vai para o resumo"
SCORE_BAIXO = "gravada, score baixo demais para enviar"
CORTADA_IA = "cortada pela IA"
ADIADA = "adiada: IA indisponivel, tenta de novo no proximo ciclo"
JA_VISTA = "ja vista em ciclo anterior"
REPETIDA = "repetida neste ciclo (outra fonte)"
DESCARTADA_REGRA = "descartada pelo filtro por regra"

ORDEM = [ENVIADA_NA_HORA, RESUMO, SCORE_BAIXO, CORTADA_IA, ADIADA, JA_VISTA, REPETIDA, DESCARTADA_REGRA]


def _motivo_agrupado(motivo: str) -> str:
    """'anuncio com 12 dias' e 'anuncio com 40 dias' contam como o mesmo motivo."""
    base = motivo.removeprefix("bloqueada: ").split("(")[0].split(":")[0].strip()
    if base.startswith("anuncio com"):
        return "anuncio antigo"
    return base or motivo[:40]


def gravar(registros: list[tuple[str, object]]) -> Path:
    """registros: (etapa, vaga). Escreve o CSV e, no Actions, o resumo da execucao."""
    PASTA.mkdir(exist_ok=True)
    caminho = PASTA / "vagas-do-ciclo.csv"
    ordenados = sorted(registros, key=lambda r: (ORDEM.index(r[0]), -r[1].score))
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arq:
        w = csv.writer(arq, delimiter=";")
        w.writerow(["etapa", "motivo", "score", "trilha", "titulo", "empresa", "local",
                    "fonte", "publicada_em", "link"])
        for etapa, v in ordenados:
            w.writerow([etapa, v.motivo, v.score, v.trilha, v.titulo, v.empresa, v.local,
                        v.fonte, v.publicada_em.date() if v.publicada_em else "", v.link])

    destino = os.getenv("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as arq:
            arq.write(_markdown(registros))
    return caminho


def _markdown(registros) -> str:
    por_etapa = Counter(etapa for etapa, _ in registros)
    linhas = ["## Vagas deste ciclo", "",
              f"{len(registros)} vagas coletadas. Planilha completa, com o motivo de cada "
              "descarte, em **Artifacts** no fim desta pagina.", "",
              "| Etapa | Vagas |", "|---|---:|"]
    linhas += [f"| {e} | {por_etapa[e]} |" for e in ORDEM if por_etapa[e]]

    cortadas = [v for e, v in registros if e == CORTADA_IA]
    if cortadas:
        linhas += ["", "### Cortadas pela IA", "", "| Vaga | Empresa | Motivo |", "|---|---|---|"]
        linhas += [f"| [{_md(v.titulo)}]({v.link}) | {_md(v.empresa)} | "
                   f"{_md(v.motivo.removeprefix('IA: '))} |" for v in cortadas]

    motivos = Counter(_motivo_agrupado(v.motivo) for e, v in registros if e == DESCARTADA_REGRA)
    if motivos:
        linhas += ["", "### Por que o filtro por regra descartou", "",
                   "| Motivo | Vagas |", "|---|---:|"]
        linhas += [f"| {_md(m)} | {n} |" for m, n in motivos.most_common()]
    return "\n".join(linhas) + "\n\n"


def _md(texto: str) -> str:
    return (texto or "").replace("|", "/").replace("\n", " ").strip()
