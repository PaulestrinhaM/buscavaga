"""Amostra real: coleta, enriquece, filtra e tria. Nao grava nem notifica."""
import importlib, sys
sys.path.insert(0, ".")
import config, filtro, triagem, main
google = importlib.import_module("fontes.google")
linkedin = importlib.import_module("fontes.linkedin")
adz = importlib.import_module("fontes.adzuna")
config.TERMOS_LINKEDIN = ["analista de dados", "engenheiro de dados"]
config.TERMOS_LINKEDIN_REGIAO = []
config.PAGINAS_LINKEDIN = 1
config.TERMOS_GOOGLE = [("analista de BI remoto", "Brazil"), ("engenheiro de dados remoto", "Brazil")]
config.TERMOS_BUSCA = ["analista de dados", "engenheiro de dados"]
coletadas = linkedin.coletar() + google.coletar(forcar=True) + adz.coletar()
coletadas = list({v.id: v for v in coletadas}.values())
novas, rep = [], []
for v in coletadas:
    if filtro.avaliar(v):
        novas.append(v)
    elif v.repescagem:
        rep.append(v)
print(f"regra: {len(novas)} aprovadas, {len(rep)} repescagem")
main.db.registrar = lambda con, v, notificada: print(f"DESCRICAO DERRUBOU | {v.fonte[:8]} | {v.titulo[:55]} | {v.motivo[:60]}")
novas, rep = main.enriquecer_linkedin(None, novas, rep, [])
novas, rep = main.enriquecer_adzuna(None, novas, rep, [])
amostra = novas[:45]
print(f"descricao media enviada: {sum(len(v.descricao) for v in amostra)//max(len(amostra),1)} caracteres")
mantidas, cortadas, _ = triagem.triar(amostra)
print(f"\nIA: {len(mantidas)} mantidas, {len(cortadas)} cortadas\n")
for v in sorted(mantidas, key=lambda v: -v.score):
    print(f"MANTIDA s={v.score} | {v.fonte[:8]} | {v.titulo[:50]}\n    {v.local[:140]}")
for v in cortadas:
    print(f"IA CORTOU | {v.fonte[:8]} | {v.titulo[:50]} | {v.motivo[:110]}")
