"""A Adzuna da a descricao inteira em alguma pagina publica? Nao grava nada."""
import os, re, requests, html
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36", "Accept-Language": "pt-BR"}
r = requests.get("https://api.adzuna.com/v1/api/jobs/br/search/1", params={
    "app_id": os.environ["ADZUNA_APP_ID"], "app_key": os.environ["ADZUNA_APP_KEY"],
    "what": "analista de dados", "results_per_page": 3, "content-type": "application/json"}, timeout=30)
for item in r.json().get("results", [])[:3]:
    print("== id", item.get("id"), "| api desc:", len(item.get("description", "")), "chars")
    print("   redirect:", item.get("redirect_url", "")[:120])
    for url in [f"https://www.adzuna.com.br/details/{item['id']}", item.get("redirect_url", "")]:
        try:
            p = requests.get(url, headers=NAV, timeout=25, allow_redirects=True)
            texto = html.unescape(re.sub(r"<[^>]+>", " ", p.text))
            texto = re.sub(r"\s+", " ", texto)
            i = texto.find((item.get("description") or "")[:40].strip()[:30])
            print(f"   {p.status_code} {len(p.text)}b final={p.url[:90]}")
            print(f"   achou trecho da api na pagina: {i >= 0}; contexto: {texto[max(i,0):max(i,0)+700] if i >= 0 else texto[:300]}")
        except Exception as e:
            print("   ERRO", url[:60], e)
