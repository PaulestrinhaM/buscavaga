"""SQLite: deduplicacao, historico e fila do resumo diario."""
import sqlite3
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
    notificada      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conteudo ON vagas(id_conteudo);
CREATE INDEX IF NOT EXISTS idx_notificada ON vagas(notificada);

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
    """Dedup em duas chaves: link e empresa+titulo (mesma vaga republicada)."""
    cur = con.execute(
        "SELECT 1 FROM vagas WHERE id = ? OR id_conteudo = ? LIMIT 1",
        (vaga.id, vaga.id_conteudo),
    )
    return cur.fetchone() is not None


def registrar(con, vaga, notificada: bool = False) -> None:
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
            1 if notificada else 0,
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
                  SUM(notificada)               AS notificadas,
                  ROUND(AVG(score), 1)          AS score_medio
           FROM vagas GROUP BY fonte ORDER BY notificadas DESC"""
    )
    return cur.fetchall()


def listar(con, dias: int = 7, score_min: int = 0) -> list[sqlite3.Row]:
    """Tudo que o radar aprovou na janela, do melhor para o pior."""
    cur = con.execute(
        """SELECT * FROM vagas
           WHERE score >= ?
             AND vista_em >= datetime('now', ?)
           ORDER BY score DESC, vista_em DESC""",
        (score_min, f"-{dias} days"),
    )
    return cur.fetchall()
