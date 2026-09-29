"""RemoteOK: feed JSON publico."""
from datetime import datetime, timezone

import requests

from vaga import Vaga

URL = "https://remoteok.com/api"
TIMEOUT = 20


def coletar() -> list[Vaga]:
    r = requests.get(URL, headers={"User-Agent": "jobradar/1.0"}, timeout=TIMEOUT)
    r.raise_for_status()
    dados = r.json()
    vagas: list[Vaga] = []
    for item in dados[1:]:   # o primeiro elemento e um aviso legal, nao uma vaga
        publicada = None
        if item.get("epoch"):
            publicada = datetime.fromtimestamp(int(item["epoch"]), tz=timezone.utc)
        vagas.append(Vaga(
            titulo=item.get("position", ""),
            empresa=item.get("company", ""),
            local=item.get("location") or "remoto",
            link=item.get("url", ""),
            fonte="remoteok",
            descricao=(item.get("description") or "")[:2000],
            publicada_em=publicada,
        ))
    return vagas
