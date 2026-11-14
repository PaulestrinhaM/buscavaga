"""Amostra real: coleta, enriquece, filtra e tria. Nao grava nem notifica."""
import importlib, sys
sys.path.insert(0, ".")
import config, filtro, triagem, main
from fontes import adzuna
google = importlib.import_module("fontes.google")
linkedin = importlib.import_module("fontes.linkedin")
config.TERMOS_LINKEDIN = ["analista de BI", "analista de dados"]
config.TERMOS_LINKEDIN_REGIAO = ["dados"]
config.PAGINAS_LINKEDIN = 1
config.TERMOS_GOOGLE = [("analista de BI remoto", "Brazil"), ("analista de dados remoto", "Brazil")]
config.LINKEDIN_DETALHES = 25
coletadas = list({v.id: v for v in google.coletar(forcar=True)}.values())
novas, rep = [], []
for v in coletadas:
    if filtro.avaliar(v):
        novas.append(v)
    elif v.repescagem:
        rep.append(v)
    else:
        print(f"REGRA CORTOU | {v.fonte[:8]} | {v.titulo[:55]} | {v.motivo[:60]}")
main.db.registrar = lambda con, v, notificada: print(f"DESCRICAO CORTOU | {v.titulo[:55]} | {v.motivo[:60]}")
novas, rep = main.enriquecer_linkedin(None, novas, rep, [])
mantidas, cortadas, _ = triagem.triar(novas[:40] + rep[:10])
print(f"\nIA: {len(mantidas)} mantidas, {len(cortadas)} cortadas\n")
for v in sorted(mantidas, key=lambda v: -v.score):
    print(f"MANTIDA s={v.score} | {v.fonte[:8]} | {v.titulo[:55]} | {v.motivo.split('IA:')[-1][:80]}")
    print(f"    trechos: {triagem.destaques(v.descricao)[:600]}")
for v in cortadas:
    print(f"IA CORTOU | {v.fonte[:8]} | {v.titulo[:55]} | {v.motivo[:80]}")
