"""Confere se os links montados pelos coletores abrem."""
import requests
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36"}
for url in ["https://gestamp.vagas.solides.com.br/vaga/952431",
            "https://vagas.solides.com.br/vagas/todas/caxias-do-sul-rs",
            "https://vagas.solides.com.br/vagas/todas/caxias-do-sul-rs?page=2",
            "https://www.vagas.com.br/vagas-em-caxias-do-sul-rs?ordenar_por=mais_recentes",
            "https://www.vagas.com.br/vagas-de-dados?m%5B%5D=100%25+Home+Office&ordenar_por=mais_recentes"]:
    try:
        r = requests.get(url, headers=NAV, timeout=25, allow_redirects=True)
        print(r.status_code, len(r.content), url, "->", r.url)
    except Exception as e:
        print("ERRO", url, e)
