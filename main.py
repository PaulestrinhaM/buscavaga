"""JobRadar: um ciclo de coleta, filtro, dedup e notificacao."""
import argparse
import os
import sys
import traceback
from pathlib import Path


def carregar_env() -> None:
    """Le o .env local, se existir. No GitHub Actions as variaveis ja vem dos secrets."""
    caminho = Path(__file__).parent / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


carregar_env()

import auditoria
import config
import db
import filtro
import notificador
import triagem
from fontes import TODAS


def rodar_ciclo(con, apenas=None) -> dict:
    fontes = {k: v for k, v in TODAS.items() if not apenas or k in apenas}
    coletadas, aprovadas, novas, falhas = 0, 0, [], []
    # dedup dentro do proprio ciclo: a mesma vaga pode vir de duas fontes antes
    # de qualquer uma ser gravada no banco
    vistas_no_ciclo: set[str] = set()
    registros: list[tuple[str, object]] = []   # (etapa, vaga): tudo que o ciclo viu

    for nome, coletor in fontes.items():
        try:
            resultado = coletor()
        except Exception as e:
            falhas.append(nome)
            db.registrar_ciclo(con, nome, 0, 0, erro=str(e)[:200])
            print(f"[{nome}] FALHOU: {e}")
            continue

        aprovadas_fonte = 0
        for vaga in resultado:
            coletadas += 1
            if not filtro.avaliar(vaga):
                registros.append((auditoria.DESCARTADA_REGRA, vaga))
                continue
            aprovadas_fonte += 1
            if vaga.id in vistas_no_ciclo or vaga.id_conteudo in vistas_no_ciclo:
                registros.append((auditoria.REPETIDA, vaga))
                continue
            if db.ja_vista(con, vaga):
                registros.append((auditoria.JA_VISTA, vaga))
                continue
            vistas_no_ciclo.update({vaga.id, vaga.id_conteudo})
            novas.append(vaga)

        aprovadas += aprovadas_fonte
        db.registrar_ciclo(con, nome, len(resultado), aprovadas_fonte)
        print(f"[{nome}] {len(resultado)} coletadas, {aprovadas_fonte} aprovadas")

    # metade ou mais das fontes quebrou: e problema de arquitetura, nao de mercado
    if fontes and len(falhas) >= len(fontes) / 2:
        notificador.alerta(f"{len(falhas)} de {len(fontes)} fontes falharam: {', '.join(falhas)}")

    antes_da_ia = novas
    novas = triagem.triar(novas)
    mantidas = {id(v) for v in novas}
    registros += [(auditoria.CORTADA_IA, v) for v in antes_da_ia if id(v) not in mantidas]
    novas.sort(key=lambda v: v.score, reverse=True)
    import time
    urgentes = 0
    for vaga in novas:
        if vaga.score >= config.SCORE_ALTA_RELEVANCIA:
            enviou = notificador.vaga_urgente(vaga)
            db.registrar(con, vaga, notificada=enviou)
            urgentes += 1 if enviou else 0
            registros.append((auditoria.ENVIADA_NA_HORA if enviou else auditoria.RESUMO, vaga))
            time.sleep(0.5)          # o Telegram limita rajada por chat
        else:
            db.registrar(con, vaga, notificada=False)
            baixo = vaga.score < config.SCORE_MINIMO_NOTIFICAR
            registros.append((auditoria.SCORE_BAIXO if baixo else auditoria.RESUMO, vaga))

    planilha = auditoria.gravar(registros)
    print(f"registro do ciclo em {planilha}")

    return {"coletadas": coletadas, "aprovadas": aprovadas,
            "novas": len(novas), "urgentes": urgentes, "falhas": falhas}


def enviar_resumo(con) -> None:
    pendentes = db.pendentes_resumo(con)
    pendentes = [p for p in pendentes if p["score"] >= config.SCORE_MINIMO_NOTIFICAR]
    if not pendentes:
        print("nada pendente para o resumo")
        return
    enviadas = notificador.resumo(pendentes)
    for p in enviadas:
        db.marcar_notificada(con, p["id"])
    if len(enviadas) < len(pendentes):
        print(f"resumo: {len(enviadas)} de {len(pendentes)} enviadas; "
              f"o restante continua pendente para a proxima rodada")
    else:
        print(f"resumo enviado com {len(enviadas)} vagas")


def testar_fontes(apenas=None) -> None:
    """Chama cada fonte isolada, sem gravar nada. Diagnostico de primeira execucao."""
    fontes = {k: v for k, v in TODAS.items() if not apenas or k in apenas}
    for nome, coletor in fontes.items():
        print(f"\n=== {nome} ===")
        try:
            resultado = coletor()
        except Exception as e:
            print(f"  ERRO: {type(e).__name__}: {e}")
            continue
        if not resultado:
            print("  0 vagas (fonte sem credencial ou sem resultado)")
            continue
        aprovadas, rejeitadas = [], []
        for v in resultado:
            (aprovadas if filtro.avaliar(v) else rejeitadas).append(v)
        print(f"  {len(resultado)} coletadas, {len(aprovadas)} aprovadas pelo filtro")

        motivos: dict[str, int] = {}
        for v in rejeitadas:
            chave = v.motivo.split("(")[0].strip()
            if chave.startswith("bloqueada: anuncio com"):
                chave = "bloqueada: anuncio antigo"
            if chave.startswith("local fora do alvo"):
                chave = "local fora do alvo"
            motivos[chave] = motivos.get(chave, 0) + 1
        if motivos:
            print("  --- por que as rejeitadas cairam:")
            for chave, n in sorted(motivos.items(), key=lambda x: -x[1]):
                print(f"    {n:>4}  {chave}")

        if aprovadas:
            print("  --- melhores aprovadas:")
            for v in sorted(aprovadas, key=lambda x: x.score, reverse=True)[:5]:
                print(f"    [{v.score}] {v.titulo} | {v.empresa} | {v.local}")
        else:
            print("  --- exemplos de titulo que vieram (para calibrar o filtro):")
            for v in resultado[:5]:
                print(f"    {v.titulo[:60]} | {v.local[:30]}")


def listar(con, dias: int, score_min: int) -> None:
    linhas = db.listar(con, dias=dias, score_min=score_min)
    if not linhas:
        print("nada na janela")
        return
    print(f"{len(linhas)} vagas nos ultimos {dias} dias (score >= {score_min})\n")
    for l in linhas:
        marca = "*" if l["notificada"] else " "
        print(f"{marca} [{l['score']:>2}] {l['titulo'][:52]:<52} | {(l['empresa'] or '')[:22]:<22} "
              f"| {(l['local'] or '')[:22]:<22} | {l['fonte']}")
        print(f"        {l['link']}")
    print("\n* = ja notificada no Telegram")


def exportar(con, caminho: str, dias: int) -> None:
    import csv
    linhas = db.listar(con, dias=dias)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arq:
        w = csv.writer(arq, delimiter=";")
        w.writerow(["score", "titulo", "empresa", "local", "fonte", "publicada_em", "link"])
        for l in linhas:
            w.writerow([l["score"], l["titulo"], l["empresa"], l["local"],
                        l["fonte"], l["publicada_em"], l["link"]])
    print(f"{len(linhas)} vagas exportadas para {caminho}")


def relatorio(con) -> None:
    print(f"{'fonte':<22}{'vistas':>8}{'notif.':>8}{'score':>8}")
    for linha in db.precisao_por_fonte(con):
        print(f"{linha['fonte']:<22}{linha['vistas']:>8}"
              f"{linha['notificadas'] or 0:>8}{linha['score_medio'] or 0:>8}")


def main() -> int:
    p = argparse.ArgumentParser(description="JobRadar")
    p.add_argument("--fontes", nargs="*", help="limita a estas fontes")
    p.add_argument("--resumo", action="store_true", help="envia o resumo e sai")
    p.add_argument("--relatorio", action="store_true", help="precisao por fonte e sai")
    p.add_argument("--testar-fontes", action="store_true",
                   help="testa cada fonte sem gravar nada e mostra exemplos")
    p.add_argument("--listar", action="store_true", help="lista tudo que o radar aprovou")
    p.add_argument("--exportar", metavar="ARQUIVO.csv", help="exporta a lista para CSV")
    p.add_argument("--dias", type=int, default=7, help="janela de --listar e --exportar")
    p.add_argument("--score-min", type=int, default=0, help="score minimo em --listar")
    args = p.parse_args()

    if args.testar_fontes:
        testar_fontes(apenas=args.fontes)
        return 0

    con = db.conectar()
    try:
        if args.relatorio:
            relatorio(con)
            return 0
        if args.listar:
            listar(con, dias=args.dias, score_min=args.score_min)
            return 0
        if args.exportar:
            exportar(con, args.exportar, dias=args.dias)
            return 0
        if args.resumo:
            enviar_resumo(con)
            return 0
        r = rodar_ciclo(con, apenas=args.fontes)
        print(f"\nciclo: {r['coletadas']} coletadas | {r['aprovadas']} aprovadas | "
              f"{r['novas']} novas | {r['urgentes']} notificadas na hora")
        return 0
    except Exception:
        traceback.print_exc()
        notificador.alerta("ciclo abortado por erro inesperado")
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
