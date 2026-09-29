"""SQLite: deduplicacao, historico e fila do resumo diario."""
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

CAMINHO = Path(__file__).parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id              TEXT PRIMARY KEY,
    id_conteudo     TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    empresa         TEXT,
    local           TEXT,
    link            TEXT,
    fonte           TEXT,
    score           INTEGER,
    nivel_confianca TEXT,
    motivo          TEXT,
    publicada_em    TEXT,
    vista_em        TEXT NOT NULL,
    notificada      INTEGER DEFAULT 0   -- 1 enviada, 0 na fila do resumo, -1 cortada pela IA
);
CREATE INDEX IF NOT EXISTS idx_conteudo ON vagas(id_conteudo);
CREATE INDEX IF NOT EXISTS idx_notificada ON vagas(notificada);

-- Vaga que a IA nao conseguiu avaliar: nem enviada, nem descartada. Guardada
-- inteira (com a descricao) para nova tentativa, sem depender da fonte trazer de novo.
CREATE TABLE IF NOT EXISTS standby (
    id               TEXT PRIMARY KEY,
    id_conteudo      TEXT NOT NULL,
    dados            TEXT NOT NULL,
    entrou_em        TEXT NOT NULL,
    tentativas       INTEGER DEFAULT 0,
    ultima_tentativa TEXT
);
CREATE INDEX IF NOT EXISTS idx_standby_conteudo ON standby(id_conteudo);

CREATE TABLE IF NOT EXISTS ciclos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rodado_em   TEXT NOT NULL,
    fonte       TEXT NOT NULL,
    coletadas   INTEGER,
    aprovadas   INTEGER,
    erro        TEXT
);
"""


def conectar() -> sqlite3.Connection:
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CAMINHO)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def ja_vista(con, vaga) -> bool:
    """Dedup em duas chaves: link e empresa+titulo (mesma vaga republicada).

    Vaga em stand-by tambem conta: ja esta na fila da IA.
    """
    for tabela in ("vagas", "standby"):
        cur = con.execute(
            f"SELECT 1 FROM {tabela} WHERE id = ? OR id_conteudo = ? LIMIT 1",
            (vaga.id, vaga.id_conteudo),
        )
        if cur.fetchone() is not None:
            return True
    return False


# ---------------------------------------------------------------- stand-by
def standby_guardar(con, vaga) -> None:
    dados = asdict(vaga)
    dados["publicada_em"] = vaga.publicada_em.isoformat() if vaga.publicada_em else None
    con.execute(
        "INSERT OR IGNORE INTO standby (id, id_conteudo, dados, entrou_em) VALUES (?,?,?,?)",
        (vaga.id, vaga.id_conteudo, json.dumps(dados, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat()),
    )
    con.commit()


def standby_listar(con, limite: int) -> list:
    """Vagas em stand-by, da que esta ha mais tempo esperando para a mais recente."""
    from vaga import Vaga
    vagas = []
    for linha in con.execute(
            "SELECT dados, tentativas, entrou_em FROM standby ORDER BY entrou_em LIMIT ?",
            (limite,)):
        dados = json.loads(linha["dados"])
        if dados.get("publicada_em"):
            dados["publicada_em"] = datetime.fromisoformat(dados["publicada_em"])
        vaga = Vaga(**dados)
        vaga.extras["tentativas_ia"] = linha["tentativas"]
        vaga.extras["standby_desde"] = datetime.fromisoformat(linha["entrou_em"])
        vagas.append(vaga)
    return vagas


def standby_remover(con, vaga) -> None:
    con.execute("DELETE FROM standby WHERE id = ?", (vaga.id,))
    con.commit()


def standby_falhou(con, vaga) -> None:
    con.execute(
        "UPDATE standby SET tentativas = tentativas + 1, ultima_tentativa = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), vaga.id),
    )
    con.commit()


def standby_total(con) -> int:
    return con.execute("SELECT COUNT(*) FROM standby").fetchone()[0]


CORTADA_IA = -1   # gravada so para nao voltar a cada ciclo; nunca e enviada


def registrar(con, vaga, notificada: bool | int = False) -> None:
    con.execute(
        """INSERT OR IGNORE INTO vagas
           (id, id_conteudo, titulo, empresa, local, link, fonte, score,
            nivel_confianca, motivo, publicada_em, vista_em, notificada)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            vaga.id, vaga.id_conteudo, vaga.titulo, vaga.empresa, vaga.local,
            vaga.link, vaga.fonte, vaga.score, vaga.nivel_confianca, vaga.motivo,
            vaga.publicada_em.isoformat() if vaga.publicada_em else None,
            datetime.now(timezone.utc).isoformat(),
            notificada if notificada == CORTADA_IA else (1 if notificada else 0),
        ),
    )
    con.commit()


def marcar_notificada(con, vaga_id: str) -> None:
    """So chamado DEPOIS que a notificacao confirmou envio."""
    con.execute("UPDATE vagas SET notificada = 1 WHERE id = ?", (vaga_id,))
    con.commit()


def pendentes_resumo(con, limite: int = 60) -> list[sqlite3.Row]:
    cur = con.execute(
        """SELECT * FROM vagas WHERE notificada = 0
           ORDER BY score DESC, vista_em DESC LIMIT ?""",
        (limite,),
    )
    return cur.fetchall()


def registrar_ciclo(con, fonte: str, coletadas: int, aprovadas: int, erro: str = "") -> None:
    con.execute(
        "INSERT INTO ciclos (rodado_em, fonte, coletadas, aprovadas, erro) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), fonte, coletadas, aprovadas, erro),
    )
    con.commit()


def precisao_por_fonte(con) -> list[sqlite3.Row]:
    cur = con.execute(
        """SELECT fonte,
                  COUNT(*)                      AS vistas,
                  SUM(notificada = 1)           AS notificadas,
                  ROUND(AVG(score), 1)          AS score_medio
           FROM vagas GROUP BY fonte ORDER BY notificadas DESC"""
    )
    return cur.fetchall()


def listar(con, dias: int = 7, score_min: int = 0) -> list[sqlite3.Row]:
    """Tudo que o radar aprovou na janela, do melhor para o pior."""
    cur = con.execute(
        """SELECT * FROM vagas
           WHERE score >= ?
             AND notificada >= 0
             AND vista_em >= datetime('now', ?)
           ORDER BY score DESC, vista_em DESC""",
        (score_min, f"-{dias} days"),
    )
    return cur.fetchall()
