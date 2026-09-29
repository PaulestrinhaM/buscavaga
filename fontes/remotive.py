"""Remotive: feed JSON publico de vagas remotas."""
from datetime import datetime

import requests

from vaga import Vaga

URL = "https://remotive.com/api/remote-jobs"
TIMEOUT = 20
CATEGORIAS = ["data", "software-dev"]


def coletar() -> list[Vaga]:
    vagas: list[Vaga] = []
    for categoria in CATEGORIAS:
        r = requests.get(URL, params={"category": categoria, "limit": 100}, timeout=TIMEOUT)
        r.raise_for_status()
        for item in r.json().get("jobs", []):
            publicada = None
            if item.get("publication_date"):
                try:
                    publicada = datetime.fromisoformat(item["publication_date"])
                except ValueError:
                    pass
            vagas.append(Vaga(
                titulo=item.get("title", ""),
                empresa=item.get("company_name", ""),
                local=item.get("candidate_required_location", "remoto"),
                link=item.get("url", ""),
                fonte="remotive",
                descricao=(item.get("description") or "")[:2000],
                publicada_em=publicada,
            ))
    return vagas
