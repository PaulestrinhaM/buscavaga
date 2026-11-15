"""Salva paginas de detalhe da Adzuna (pelo redirect_url da API) como amostra."""
import os, gzip, requests
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36", "Accept-Language": "pt-BR"}
r = requests.get("https://api.adzuna.com/v1/api/jobs/br/search/1", params={
    "app_id": os.environ["ADZUNA_APP_ID"], "app_key": os.environ["ADZUNA_APP_KEY"],
    "what": "engenheiro de dados", "results_per_page": 4, "content-type": "application/json"}, timeout=30)
os.makedirs("diag/saida", exist_ok=True)
for i, item in enumerate(r.json().get("results", [])[:4]):
    p = requests.get(item["redirect_url"], headers=NAV, timeout=25)
    print(i, p.status_code, len(p.text), item["title"], "|", item["description"][:80])
    with gzip.open(f"diag/saida/adzuna_{i}.html.gz", "wt", encoding="utf-8") as f:
        f.write(p.text)
    with open(f"diag/saida/adzuna_{i}.api.txt", "w", encoding="utf-8") as f:
        f.write(item["description"])
