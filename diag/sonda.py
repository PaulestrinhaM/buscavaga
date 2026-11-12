"""Sonda de fontes, rodada 2. Descartavel."""
import json, pathlib, re, time
import requests

OUT = pathlib.Path(__file__).parent / "saida2"
OUT.mkdir(exist_ok=True)
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
       "Accept-Language": "pt-BR,pt;q=0.9"}
log = []


def get(nome, url, params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers or NAV, timeout=25)
        log.append(f"{nome}: {r.status_code} {len(r.content)}b {r.url}")
        return r
    except Exception as e:
        log.append(f"{nome}: ERRO {e}")
        return None


def salvar(nome, texto):
    (OUT / nome).write_text(texto, encoding="utf-8")


# LinkedIn: Brasil por geoId, remoto, paginado, e o detalhe de uma vaga
L = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
ids = []
for nome, p in {
    "br_remoto_p0": {"keywords": "analista de dados", "geoId": "106057199", "f_WT": "2", "f_TPR": "r604800", "start": 0},
    "br_remoto_p1": {"keywords": "analista de dados", "geoId": "106057199", "f_WT": "2", "f_TPR": "r604800", "start": 25},
    "br_remoto_eng": {"keywords": "engenheiro de dados", "geoId": "106057199", "f_WT": "2", "f_TPR": "r86400", "start": 0},
    "caxias_25km": {"keywords": "dados", "location": "Caxias do Sul, Rio Grande do Sul, Brasil", "distance": "25", "f_TPR": "r604800", "start": 0},
    "caxias_bi": {"keywords": "BI", "location": "Caxias do Sul, Rio Grande do Sul, Brasil", "distance": "25", "f_TPR": "r604800", "start": 0},
}.items():
    r = get(f"li_{nome}", L, p)
    if r is not None:
        ids += re.findall(r"urn:li:jobPosting:(\d+)", r.text)[:2]
        salvar(f"li_{nome}.html", r.text)
    time.sleep(3)
for i in ids[:2]:
    r = get(f"li_detalhe_{i}", f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{i}")
    if r is not None:
        salvar(f"li_detalhe_{i}.html", r.text)
    time.sleep(3)

# Vagas.com: HTML inteiro
for nome, url in {"vagascom": "https://www.vagas.com.br/vagas-de-analista-de-dados?ordenar_por=mais_recentes",
                  "vagascom_caxias": "https://www.vagas.com.br/vagas-de-dados-em-caxias-do-sul-rs?ordenar_por=mais_recentes"}.items():
    r = get(nome, url)
    if r is not None:
        salvar(f"{nome}.html", r.text)

# Solides: pagina de busca e chaves de API nos scripts
r = get("sol_busca", "https://vagas.solides.com.br/vagas/todas/analista-de-dados")
if r is not None:
    salvar("sol_busca.html", r.text)
    chunks = sorted(set(re.findall(r'/_next/static/chunks/[^"\s]+\.js', r.text)))
    achados = set()
    for c in chunks[:40]:
        rc = get("chunk", "https://vagas.solides.com.br" + c)
        if rc is None:
            continue
        for m in re.findall(r'https?://[a-zA-Z0-9.-]+\.solides[a-zA-Z0-9.-]*\.[a-z.]+[a-zA-Z0-9/_.{}$-]*', rc.text):
            achados.add(m)
        for m in re.findall(r'"(/[a-zA-Z0-9_/-]*vacanc[a-zA-Z0-9_/-]*)"', rc.text):
            achados.add(m)
    salvar("sol_apis.txt", "\n".join(sorted(achados)))

salvar("log.txt", "\n".join(log))
