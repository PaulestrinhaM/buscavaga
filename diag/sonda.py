"""Sonda de fontes: roda no Actions e grava respostas cruas em diag/saida/. Descartavel."""
import json
import pathlib
import re
import time

import requests

OUT = pathlib.Path(__file__).parent / "saida"
OUT.mkdir(exist_ok=True)
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
             "Accept-Language": "pt-BR,pt;q=0.9"}
log = []


def get(nome, url, params=None):
    try:
        r = requests.get(url, params=params, headers=NAVEGADOR, timeout=25)
        log.append(f"{nome}: {r.status_code} {len(r.content)}b {r.url}")
        return r
    except Exception as e:
        log.append(f"{nome}: ERRO {e}")
        return None


def salvar(nome, texto):
    (OUT / nome).write_text(texto, encoding="utf-8")


# ---------- GUPY
G = "https://portal.gupy.io/api/job-search/jobs"
res = {}
for nome, p in {
    "termo": {"jobName": "analista de dados", "limit": 100, "offset": 0},
    "termo_off100": {"jobName": "analista de dados", "limit": 100, "offset": 100},
    "termo_lim10": {"jobName": "analista de dados", "limit": 10, "offset": 0},
    "cidade": {"city": "Caxias do Sul", "limit": 100, "offset": 0},
    "cidade_estado": {"city": "Caxias do Sul", "state": "Rio Grande do Sul", "limit": 100},
    "estado": {"state": "Rio Grande do Sul", "limit": 100},
    "remoto": {"jobName": "dados", "workplaceType": "remote", "limit": 100},
    "vazio": {"limit": 100},
}.items():
    r = get(f"gupy_{nome}", G, p)
    if r is None or r.status_code != 200:
        res[nome] = {"status": getattr(r, "status_code", None), "corpo": getattr(r, "text", "")[:300]}
        continue
    j = r.json()
    d = j.get("data", [])
    res[nome] = {
        "n": len(d), "pagination": j.get("pagination"),
        "chaves": sorted(d[0].keys()) if d else [],
        "datas": [x.get("publishedDate") for x in d[:8]],
        "cidades": [f"{x.get('city')}/{x.get('state')}/{x.get('workplaceType')}" for x in d[:15]],
        "titulos": [x.get("name") for x in d[:25]],
    }
    if nome == "termo" and d:
        salvar("gupy_item.json", json.dumps(d[0], ensure_ascii=False, indent=1)[:6000])
    time.sleep(1)
salvar("gupy.json", json.dumps(res, ensure_ascii=False, indent=1))
r = get("gupy_html", "https://portal.gupy.io/job-search/term=dados")
if r is not None:
    params = sorted(set(re.findall(r"[?&]([a-zA-Z]+)=", r.text)))
    apis = sorted(set(re.findall(r"/api/[a-zA-Z0-9/_-]+", r.text)))
    salvar("gupy_html.txt", f"params={params}\napis={apis}\n\n" + r.text[:3000])

# ---------- BOARDS
SLUGS = """stone nubank quintoandar creditas ebanx loft wildlifestudios vtex picpay olist cloudwalk
hotmart contabilizei wellhub gympass dock pagbank xpinc btgpactual mercadolibre cora neon zup
inter c6bank willbank meliuz petlove zenvia rdstation totvs blip hurb madeiramadeira sympla buser
loggi 99app kovi descomplica alura vivo ambev itau bradesco santander ifood nuvemshop tray
pismo unico idwall caju flash swile alice sami conta-azul contaazul omie asaas pipefy
gupy kenoby solides vindi pagarme magalu americanas stoneco cielo getnet
tractian neoway serasa serasaexperian boavista quinto-andar""".split()
achados = []
for slug in SLUGS:
    for plat, url in {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
    }.items():
        try:
            r = requests.get(url, timeout=15)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        j = r.json()
        jobs = j if isinstance(j, list) else j.get("jobs", [])
        if not jobs:
            continue

        def tit(x):
            return x.get("title") or x.get("text") or ""

        def loc(x):
            lo = x.get("location")
            if isinstance(lo, dict):
                return lo.get("name", "")
            if lo:
                return str(lo)
            return (x.get("categories") or {}).get("location", "")

        dados = [f"{tit(x)} | {loc(x)}" for x in jobs
                 if re.search(r"dad|data|\bbi\b|analytic|analista|crm", tit(x), re.I)]
        locs = {}
        for x in jobs:
            locs[loc(x)[:25]] = locs.get(loc(x)[:25], 0) + 1
        achados.append({"plat": plat, "slug": slug, "n": len(jobs), "dados": dados[:12],
                        "locais": sorted(locs.items(), key=lambda t: -t[1])[:6]})
    time.sleep(0.2)
salvar("boards.json", json.dumps(achados, ensure_ascii=False, indent=1))

# ---------- LINKEDIN (visitante)
L = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
for nome, p in {
    "remoto": {"keywords": "analista de dados", "location": "Brasil", "f_WT": "2",
               "f_TPR": "r604800", "start": 0},
    "caxias": {"keywords": "dados", "location": "Caxias do Sul, Rio Grande do Sul, Brasil",
               "f_TPR": "r604800", "start": 0},
}.items():
    r = get(f"linkedin_{nome}", L, p)
    if r is not None:
        n = r.text.count("base-search-card")
        salvar(f"linkedin_{nome}.html", f"<!-- status {r.status_code} cards {n} -->\n" + r.text[:15000])
    time.sleep(3)

# ---------- VAGAS.COM.BR
for nome, url in {
    "vagascom": "https://www.vagas.com.br/vagas-de-analista-de-dados?ordenar_por=mais_recentes",
    "vagascom_caxias": "https://www.vagas.com.br/vagas-em-caxias-do-sul-rs",
}.items():
    r = get(nome, url)
    if r is not None:
        salvar(f"{nome}.html", r.text[:40000])

# ---------- SOLIDES
r = get("solides_home", "https://vagas.solides.com.br/")
if r is not None:
    apis = sorted(set(re.findall(r"https?://[a-zA-Z0-9.-]*solides[a-zA-Z0-9./_-]*", r.text)))
    salvar("solides_home.txt", "apis=" + "\n".join(apis) + "\n\n" + r.text[:8000])

salvar("log.txt", "\n".join(log))
