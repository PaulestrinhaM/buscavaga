"""Onde a pagina publica do LinkedIn diz Presencial/Hibrido/Remoto? Nao grava nada."""
import re, json, html, requests
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
for jid in ["4401831058", "4388869393"]:
    for nome, url in [("detalhe", f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"),
                      ("pagina", f"https://www.linkedin.com/jobs/view/{jid}")]:
        r = requests.get(url, headers=NAV, timeout=25)
        t = r.text
        print(f"== {jid} {nome}: {r.status_code} {len(t)}b")
        for p in ["Presencial", "On-site", "Híbrido", "Hybrid", "Remoto", "Remote", "TELECOMMUTE",
                  "jobLocationType", "workplaceType", "workplace", "WorkplaceType"]:
            for m in list(re.finditer(re.escape(p), t))[:2]:
                ctx = re.sub(r"\s+", " ", t[max(0, m.start()-150):m.end()+80])
                print(f"   [{p}] ...{ctx}...")
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
            try:
                d = json.loads(m.group(1)); print("   LD:", {k: d.get(k) for k in ("@type", "jobLocationType", "applicantLocationRequirements", "jobLocation")})
            except Exception as e:
                print("   LD err", e)
