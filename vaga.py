"""Modelo de vaga e normalizacao de texto."""
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, espacos colapsados. Base de toda comparacao."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return re.sub(r"\s+", " ", texto).strip()


@dataclass
class Vaga:
    titulo: str
    empresa: str
    local: str
    link: str
    fonte: str
    descricao: str = ""
    publicada_em: datetime | None = None
    salario: str = ""
    score: int = 0
    motivo: str = ""
    nivel_confianca: str = ""
    trilha: str = ""           # "dados" ou "operacoes": decide a senioridade aceita
    repescagem: bool = False   # titulo nao reconhecido, mas passou nos bloqueios: a IA le
    extras: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Identidade por link; fallback em empresa+titulo para republicacao."""
        base = self.link.split("?")[0].rstrip("/") if self.link else ""
        if not base:
            base = f"{normalizar(self.empresa)}|{normalizar(self.titulo)}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    @property
    def id_conteudo(self) -> str:
        """Identidade por empresa+titulo: pega a mesma vaga em fontes diferentes."""
        chave = f"{normalizar(self.empresa)}|{normalizar(self.titulo)}"
        return hashlib.sha256(chave.encode()).hexdigest()[:16]

    @property
    def texto_busca(self) -> str:
        return normalizar(f"{self.titulo} {self.local} {self.descricao}")

    @property
    def titulo_norm(self) -> str:
        return normalizar(self.titulo)

    @property
    def dias_desde_publicacao(self) -> int | None:
        if not self.publicada_em:
            return None
        agora = datetime.now(timezone.utc)
        pub = self.publicada_em
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (agora - pub).days
