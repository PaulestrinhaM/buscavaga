"""Filtro em tres niveis de confianca e score de relevancia.

Principio: nada aprova por palavra-chave solta.
"""
import re

import config
from vaga import Vaga, normalizar


def _contem(texto: str, termos: list[str]) -> str | None:
    for termo in termos:
        if normalizar(termo) in texto:
            return termo
    return None


def _contem_palavra(texto: str, termos: list[str]) -> str | None:
    """Casa termo como palavra inteira: 'head' nao pode casar em 'headless'."""
    for termo in termos:
        alvo = normalizar(termo)
        if not alvo:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alvo)}(?![a-z0-9])", texto):
            return termo
    return None


def _chave(termo: str) -> list[str]:
    """Palavras-chave de um termo de config, sem as ignoradas. Preserva o '*'."""
    ignoradas = set(config.PALAVRAS_IGNORADAS)
    return [p for p in re.findall(r"[a-z0-9*]+", normalizar(termo)) if p not in ignoradas]


def _casa_chave(palavras: set[str], chave: list[str]) -> bool:
    def presente(k: str) -> bool:
        if k.endswith("*"):
            return any(p.startswith(k[:-1]) for p in palavras)
        return k in palavras
    return bool(chave) and all(presente(k) for k in chave)


def _cargo(texto: str, termos: list[str]) -> str | None:
    """Termo cujas palavras-chave aparecem todas no texto, em qualquer ordem.

    Se varios casam, devolve o mais especifico (mais palavras-chave).
    """
    palavras = set(re.findall(r"[a-z0-9]+", texto))
    casados = [
        t for t in termos
        if (_contem_palavra(texto, [t.strip('"')]) if t.startswith('"')
            else _casa_chave(palavras, _chave(t)))
    ]
    return max(casados, key=lambda t: len(_chave(t)), default=None)


def _alternativa(termos: list[str]) -> str:
    return "|".join(re.escape(normalizar(t)) for t in sorted(termos, key=len, reverse=True))


def _exclusiva_afirmativa(texto: str) -> str | None:
    """Trecho que restringe a vaga a um grupo, ou None.

    O grupo tem que vir logo depois da palavra de exclusividade, separado so por
    conectivos ("exclusiva para pessoas com deficiencia"). Janela solta de
    caracteres pegaria "exclusivas ou nao para PcD", texto padrao de muito anuncio.
    """
    padrao = (
        rf"(?<![a-z0-9])(?:{_alternativa(config.TERMOS_EXCLUSIVIDADE)})"
        rf"(?:[\s:,-]+(?:{_alternativa(config.CONECTIVOS_AFIRMATIVA)}))*"
        rf"[\s:,-]+(?:{_alternativa(config.GRUPOS_AFIRMATIVOS)})(?![a-z0-9])"
    )
    negacao = rf"(?<![a-z0-9])(?:{_alternativa(config.NEGACOES_AFIRMATIVA)})(?:\s+e)?\s+$"
    for m in re.finditer(padrao, texto):
        if re.search(negacao, texto[max(0, m.start() - 12):m.start()]):
            continue
        return m.group(0)
    return None


def trilha(titulo: str) -> str:
    """'operacoes' quando o cargo de operacoes casado e mais especifico que o de dados.

    "Analista de Web Analytics" casa {analista, web, analytics} em operacoes e
    {analista, analytics} em dados: fica em operacoes. Empate ("Analista de Dados e
    CRM"), cargo ambiguo ou ferramenta ficam com a regra mais estrita, a de dados.
    """
    ops = _cargo(titulo, config.CARGOS_OPERACOES)
    if not ops:
        return "dados"
    dados = _cargo(titulo, config.CARGOS_DADOS)
    if dados and len(_chave(dados)) >= len(_chave(ops)):
        return "dados"
    return "operacoes"


def _pleno_sem_junior(titulo: str) -> str | None:
    for excecao in config.EXCECOES_PLENO:
        titulo = titulo.replace(normalizar(excecao), " ")
    pleno = _contem_palavra(titulo, config.BLOQUEIO_PLENO)
    if pleno and not _contem_palavra(titulo, config.TERMOS_JUNIOR):
        return pleno
    return None


def bloqueada(vaga: Vaga) -> str | None:
    """Motivo do bloqueio, ou None se passa."""
    titulo = vaga.titulo_norm
    senioridade = _contem_palavra(titulo, config.BLOQUEIO_SENIORIDADE)
    if senioridade:
        return f"senioridade acima do alvo ({senioridade.strip()})"
    if trilha(titulo) == "dados":
        pleno = _pleno_sem_junior(titulo)
        if pleno:
            return f"senioridade acima do alvo em dados ({pleno})"
    ruido = _contem_palavra(titulo, config.BLOQUEIO_RUIDO)
    if ruido:
        return f"fora da area ({ruido})"

    corpo = normalizar(vaga.descricao)
    afirmativa = _exclusiva_afirmativa(titulo) or _exclusiva_afirmativa(corpo)
    grupo_no_titulo = _contem_palavra(titulo, config.GRUPOS_NO_TITULO)
    if grupo_no_titulo and not _contem_palavra(titulo, config.RESSALVAS_TITULO):
        afirmativa = afirmativa or f"{grupo_no_titulo} no titulo"
    if afirmativa:
        return f"vaga afirmativa exclusiva ({afirmativa})"
    senioridade_corpo = _contem(corpo, config.SENIORIDADE_DESCRICAO)
    if senioridade_corpo:
        return f"senioridade no anuncio ({senioridade_corpo})"

    dias = vaga.dias_desde_publicacao
    if dias is not None and dias > config.DIAS_MAX_ANUNCIO:
        return f"anuncio com {dias} dias"
    if dias is None and config.EXIGIR_DATA:
        return "sem data de publicacao"
    return None


def local_aceito(vaga: Vaga) -> bool:
    """Remoto em qualquer lugar do Brasil, ou qualquer modalidade na regiao de Caxias."""
    alvo = normalizar(f"{vaga.local} {vaga.titulo}")
    if _contem(alvo, config.CIDADES_REGIAO):
        return True
    # fora da regiao, hibrido ou presencial declarado no local/titulo encerra:
    # "auxilio home office" na descricao nao transforma vaga hibrida em remota
    if _contem_palavra(alvo, config.TERMOS_HIBRIDO + config.SINAIS_PRESENCIAL):
        return False
    # vaga remota costuma vir com a cidade da sede no campo de local e o
    # regime so na descricao. Exige expressao inequivoca, e o anuncio nao
    # pode se declarar presencial ou hibrido em outro ponto.
    corpo = normalizar(vaga.descricao)
    if _contem(corpo, config.SINAIS_REMOTO_DESCRICAO):
        if not _contem_palavra(corpo, config.SINAIS_PRESENCIAL + config.TERMOS_HIBRIDO):
            return True
    # regiao internacional que alcanca o Brasil
    if _contem(alvo, config.REGIOES_ACEITAS):
        return True
    # "remoto" sozinho so vale se nenhum pais estrangeiro estiver restringindo
    if _contem(alvo, config.TERMOS_REMOTO):
        estrangeiro = _contem(alvo, ["usa only", "us only", "united states", "europe only",
                                     "uk only", "canada only", "emea", "apac", "india only"])
        return not estrangeiro
    return False


def classificar(vaga: Vaga) -> tuple[bool, str, str]:
    """(aprovada, nivel_confianca, motivo). Tres niveis, nessa ordem."""
    titulo = vaga.titulo_norm

    forte = _cargo(titulo, config.CARGOS_FORTES)
    if forte:
        return True, "alta", f"cargo forte: {forte}"

    ambiguo = _cargo(titulo, config.CARGOS_AMBIGUOS)
    if ambiguo:
        qualificador = _cargo(titulo, config.QUALIFICADORES)
        if qualificador:
            return True, "media", f"cargo ambiguo ({ambiguo}) + qualificador ({qualificador})"

    ferramenta = _contem(titulo, config.FERRAMENTAS)
    if ferramenta:
        palavra_cargo = _contem(titulo, config.PALAVRAS_CARGO)
        if palavra_cargo:
            return True, "media", f"ferramenta ({ferramenta}) + cargo ({palavra_cargo})"

    return False, "", "nenhum criterio de cargo atendido no titulo"


def pontuar(vaga: Vaga, nivel: str) -> int:
    """Score 0-10 por soma de sinais conhecidos. Sem ML, pesos em config."""
    p = config.PESOS
    score = 0

    if nivel == "alta":
        score += p["cargo_forte"]
    elif nivel == "media":
        score += p["cargo_ambiguo_qualificado"]

    texto = vaga.texto_busca
    achadas = {f for f in config.FERRAMENTAS if normalizar(f) in texto}
    score += min(len(achadas), 3) * p["ferramenta_no_texto"]

    titulo = vaga.titulo_norm
    if _contem_palavra(titulo, config.TERMOS_JUNIOR):
        score += p["junior"]

    alvo = normalizar(f"{vaga.local} {vaga.titulo}")
    if _contem(alvo, config.TERMOS_REMOTO):
        score += p["remoto"]
    elif _contem(alvo, config.CIDADES_REGIAO):
        score += p["cidade_alvo"]

    return min(score, 10)


def avaliar(vaga: Vaga) -> bool:
    """Aplica tudo e preenche score/motivo/nivel na propria vaga."""
    motivo_bloqueio = bloqueada(vaga)
    if motivo_bloqueio:
        vaga.motivo = f"bloqueada: {motivo_bloqueio}"
        return False

    aprovada, nivel, motivo = classificar(vaga)
    if not aprovada:
        vaga.motivo = motivo
        # passou em todos os bloqueios rigidos, so o titulo nao foi reconhecido:
        # candidata a repescagem, onde a IA le a descricao
        vaga.trilha = trilha(vaga.titulo_norm)
        vaga.repescagem = local_aceito(vaga)
        return False

    if not local_aceito(vaga):
        vaga.motivo = f"local fora do alvo: {vaga.local}"
        return False

    vaga.nivel_confianca = nivel
    vaga.trilha = trilha(vaga.titulo_norm)
    vaga.motivo = motivo
    vaga.score = pontuar(vaga, nivel)
    return True
