"""JobRadar: um ciclo de coleta, filtro, dedup e notificacao."""
import argparse
from datetime import datetime, timedelta, timezone
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
    repescagem: list = []
    repescar = config.USAR_IA and config.REPESCAGEM

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
            aprovada = filtro.avaliar(vaga)
            if not aprovada and not (repescar and vaga.repescagem):
                registros.append((auditoria.DESCARTADA_REGRA, vaga))
                continue
            aprovadas_fonte += 1 if aprovada else 0
            if vaga.id in vistas_no_ciclo or vaga.id_conteudo in vistas_no_ciclo:
                registros.append((auditoria.REPETIDA, vaga))
                continue
            if db.ja_vista(con, vaga):
                registros.append((auditoria.JA_VISTA, vaga))
                continue
            vistas_no_ciclo.update({vaga.id, vaga.id_conteudo})
            (novas if aprovada else repescagem).append(vaga)

        aprovadas += aprovadas_fonte
        db.registrar_ciclo(con, nome, len(resultado), aprovadas_fonte)
        print(f"[{nome}] {len(resultado)} coletadas, {aprovadas_fonte} aprovadas")

    # metade ou mais das fontes quebrou: e problema de arquitetura, nao de mercado
    if fontes and len(falhas) >= len(fontes) / 2:
        notificador.alerta(f"{len(falhas)} de {len(fontes)} fontes falharam: {', '.join(falhas)}")

    # repescagem acima do teto nao vai para a IA agora: espera no stand-by
    for vaga in repescagem[config.MAX_REPESCAGEM:]:
        db.standby_guardar(con, vaga)
        registros.append((auditoria.STANDBY, vaga))
    mantidas, cortadas, nao_avaliadas = triagem.triar(novas + repescagem[:config.MAX_REPESCAGEM])
    registros += _aplicar_vereditos(con, mantidas, cortadas, nao_avaliadas)
    novas = [v for etapa, v in registros
             if etapa in (auditoria.ENVIADA_NA_HORA, auditoria.RESUMO, auditoria.SCORE_BAIXO)]
    urgentes = sum(1 for etapa, _ in registros if etapa == auditoria.ENVIADA_NA_HORA)

    planilha = auditoria.gravar(registros)
    print(f"registro do ciclo em {planilha}")

    return {"coletadas": coletadas, "aprovadas": aprovadas,
            "novas": len(novas), "urgentes": urgentes, "falhas": falhas}


def _aplicar_vereditos(con, mantidas, cortadas, nao_avaliadas) -> list[tuple[str, object]]:
    """Grava e notifica conforme o veredito da IA. Devolve (etapa, vaga) de cada uma."""
    import time
    registros = []
    # cortada fica gravada para nao voltar no proximo ciclo, mas nunca e enviada
    for vaga in cortadas:
        db.registrar(con, vaga, notificada=db.CORTADA_IA)
        registros.append((auditoria.CORTADA_IA, vaga))
    # sem veredito: stand-by, nem enviada nem descartada. Repescagem sempre, porque so
    # existe com aval da IA; vaga da regra so se ADIAR_SE_IA_FALHAR.
    for vaga in nao_avaliadas:
        if vaga.repescagem or config.ADIAR_SE_IA_FALHAR:
            db.standby_guardar(con, vaga)
            registros.append((auditoria.STANDBY, vaga))
        else:
            mantidas.append(vaga)
    for vaga in sorted(mantidas, key=lambda v: v.score, reverse=True):
        if vaga.score >= config.SCORE_ALTA_RELEVANCIA:
            enviou = notificador.vaga_urgente(vaga)
            db.registrar(con, vaga, notificada=enviou)
            registros.append((auditoria.ENVIADA_NA_HORA if enviou else auditoria.RESUMO, vaga))
            time.sleep(0.5)          # o Telegram limita rajada por chat
        else:
            db.registrar(con, vaga, notificada=False)
            baixo = vaga.score < config.SCORE_MINIMO_NOTIFICAR
            registros.append((auditoria.SCORE_BAIXO if baixo else auditoria.RESUMO, vaga))
    return registros


def processar_standby(con) -> dict:
    """Nova tentativa da IA sobre o stand-by. Roda de hora em hora, entre os ciclos."""
    vagas = db.standby_listar(con, config.STANDBY_POR_RODADA)
    if not vagas:
        print("stand-by vazio")
        return {"tentadas": 0, "aprovadas": 0, "cortadas": 0, "expiradas": 0, "restantes": 0}

    # esperou demais (ou o anuncio envelheceu): sai do stand-by e vai para o usuario
    # olhar na mao, sem o aval da IA
    agora = datetime.now(timezone.utc)
    expiradas = [
        v for v in vagas
        if agora - v.extras["standby_desde"] > timedelta(days=config.STANDBY_DIAS_MAX)
        or (v.dias_desde_publicacao or 0) > config.DIAS_MAX_ANUNCIO
    ]
    for vaga in expiradas:
        db.standby_remover(con, vaga)
    if expiradas:
        linhas = "\n".join(f"- {v.titulo} | {v.empresa}\n  {v.link}" for v in expiradas[:15])
        resto = f"\n(e mais {len(expiradas) - 15})" if len(expiradas) > 15 else ""
        notificador.alerta(f"{len(expiradas)} vagas ficaram {config.STANDBY_DIAS_MAX} dias em "
                           f"stand-by sem a IA conseguir avaliar. Vale olhar na mao:\n"
                           f"{linhas}{resto}")

    pendentes = [v for v in vagas if v not in expiradas]
    if config.USAR_IA:
        mantidas, cortadas, falhas = triagem.triar(pendentes, config.STANDBY_LOTE)
    else:
        # IA desligada: vaga da regra segue, repescagem (que so existe com IA) sai
        mantidas, cortadas, falhas = [v for v in pendentes if not v.repescagem], [], []
    avaliadas = pendentes if not config.USAR_IA else mantidas + cortadas
    for vaga in avaliadas:
        db.standby_remover(con, vaga)
    for vaga in falhas:
        db.standby_falhou(con, vaga)       # continua esperando a proxima hora
    # falhas ja estao no stand-by: nao passam de novo por _aplicar_vereditos
    _aplicar_vereditos(con, mantidas, cortadas, [])
    restantes = db.standby_total(con)
    print(f"stand-by: {len(pendentes)} tentadas, {len(mantidas)} aprovadas, "
          f"{len(cortadas)} cortadas, {len(expiradas)} expiradas, {restantes} seguem esperando")
    return {"tentadas": len(pendentes), "aprovadas": len(mantidas), "cortadas": len(cortadas),
            "expiradas": len(expiradas), "restantes": restantes}


def inicio_do_turno(agora: datetime) -> datetime:
    """Inicio, em UTC, do turno de coleta em que 'agora' cai."""
    fuso = timedelta(hours=config.FUSO_BRASILIA)
    local = agora.astimezone(timezone.utc) + fuso
    horas = sorted(config.HORARIOS_CICLO)
    anteriores = [h for h in horas if h <= local.hour]
    if anteriores:
        inicio = local.replace(hour=anteriores[-1], minute=0, second=0, microsecond=0)
    else:
        # madrugada: o turno vigente e o ultimo de ontem
        inicio = (local - timedelta(days=1)).replace(hour=horas[-1], minute=0, second=0,
                                                     microsecond=0)
    return inicio - fuso


def ciclo_pendente(con, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now(timezone.utc)
    ultimo = db.ultimo_ciclo(con)
    return ultimo is None or ultimo < inicio_do_turno(agora)


def rodar_agendado(con) -> None:
    """O que o disparo de hora em hora faz: coleta do turno, se faltar; senao, stand-by."""
    if ciclo_pendente(con):
        r = rodar_ciclo(con)
        print(f"\nciclo: {r['coletadas']} coletadas | {r['aprovadas']} aprovadas | "
              f"{r['novas']} novas | {r['urgentes']} notificadas na hora")
        enviar_resumo(con)
    else:
        print("coleta deste turno ja rodou: so o stand-by")
        r = processar_standby(con)
        auditoria.anotar(
            f"**So stand-by.** A coleta deste turno ja rodou "
            f"(ultima: {db.ultimo_ciclo(con):%d/%m %H:%M} UTC); a planilha esta naquela "
            f"execucao. Stand-by: {r['tentadas']} tentadas, {r['aprovadas']} aprovadas, "
            f"{r['cortadas']} cortadas, {r['restantes']} seguem esperando.")


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
    p.add_argument("--agendado", action="store_true",
                   help="coleta do turno se ainda nao rodou; senao, stand-by (usado pelo Actions)")
    p.add_argument("--standby", action="store_true",
                   help="tenta de novo a IA sobre as vagas em stand-by")
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
        if args.standby:
            processar_standby(con)
            return 0
        if args.agendado:
            rodar_agendado(con)
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
