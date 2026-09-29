"""Telegram: notificacao imediata e resumo ranqueado.

Regra: so retorna True se a mensagem saiu. Quem chama so marca como
notificada depois disso, para nunca perder uma vaga por falha de envio.
"""
import os
import time

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 15


def _enviar(texto: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notificador] credenciais ausentes, imprimindo:\n" + texto)
        return False
    try:
        r = requests.post(
            API.format(token=token),
            json={"chat_id": chat_id, "text": texto,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=TIMEOUT,
        )
        return r.ok
    except requests.RequestException as e:
        print(f"[notificador] falha no envio: {e}")
        return False


def _escapar(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vaga_urgente(vaga) -> bool:
    texto = (
        f"🔥 <b>{_escapar(vaga.titulo)}</b>\n"
        f"{_escapar(vaga.empresa)} | {_escapar(vaga.local)}\n"
        f"score {vaga.score}/10 | confianca {vaga.nivel_confianca} | {vaga.fonte}\n"
        f"<i>{_escapar(vaga.motivo)}</i>\n"
        f"{vaga.link}"
    )
    return _enviar(texto)


LIMITE_MENSAGEM = 3800     # o Telegram corta em 4096; margem para o cabecalho
PAUSA_ENTRE_MENSAGENS = 0.5


def resumo(linhas) -> list:
    """Envia o resumo em quantas mensagens forem necessarias.

    Devolve as linhas EFETIVAMENTE enviadas. Quem chama so marca essas como
    notificadas: vaga que nao coube na mensagem nao pode ser dada como vista.
    """
    if not linhas:
        return []

    blocos, atual, tamanho = [], [], 0
    for v in linhas:
        texto = (f"[{v['score']}] <b>{_escapar(v['titulo'])}</b>\n"
                 f"{_escapar(v['empresa'])} | {_escapar(v['local'])} | {v['fonte']}\n"
                 f"{v['link']}\n")
        if tamanho + len(texto) > LIMITE_MENSAGEM and atual:
            blocos.append(atual)
            atual, tamanho = [], 0
        atual.append((v, texto))
        tamanho += len(texto)
    if atual:
        blocos.append(atual)

    enviadas = []
    total = len(blocos)
    for i, bloco in enumerate(blocos, start=1):
        cabecalho = (f"📋 <b>Resumo: {len(linhas)} vagas</b>\n" if total == 1
                     else f"📋 <b>Resumo {i}/{total}</b>\n")
        if _enviar(cabecalho + "\n" + "\n".join(t for _, t in bloco)):
            enviadas.extend(v for v, _ in bloco)
        else:
            break                      # falhou o envio: para e nao marca o resto
        if i < total:
            time.sleep(PAUSA_ENTRE_MENSAGENS)
    return enviadas


def alerta(texto: str) -> bool:
    return _enviar(f"⚠️ <b>JobRadar</b>\n{_escapar(texto)}")
