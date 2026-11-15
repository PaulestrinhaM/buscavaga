"""Em qual filtro de modalidade (f_WT) a vaga aparece? Nao grava nada."""
import re, time, requests
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
alvo = {"4401831058": "EY RJ (presencial no app)", "4388869393": "EY SP"}
achados = {}
for wt, nome in [("1", "presencial"), ("2", "remoto"), ("3", "hibrido")]:
    for kw in ["engenheiro de dados", "Banco de Talentos Engenheiro de Dados"]:
        for start in (0, 10, 20):
            r = requests.get(URL, headers=NAV, timeout=25, params={
                "keywords": kw, "geoId": "106057199", "f_WT": wt, "f_TPR": "r604800", "start": start})
            ids = re.findall(r"urn:li:jobPosting:(\d+)", r.text)
            locs = re.findall(r'job-search-card__location">\s*(.*?)\s*</span>', r.text, re.S)
            print(f"f_WT={wt} {nome:10} '{kw[:20]}' start={start}: {r.status_code} {len(ids)} vagas; locais: {sorted(set(l.strip()[:20] for l in locs))[:6]}")
            for i in ids:
                achados.setdefault(i, set()).add(nome)
            time.sleep(6)
for jid, desc in alvo.items():
    print(jid, desc, "->", achados.get(jid, "nao apareceu"))
multi = {k: v for k, v in achados.items() if len(v) > 1}
print(f"vagas que aparecem em mais de um filtro: {len(multi)} de {len(achados)}")
