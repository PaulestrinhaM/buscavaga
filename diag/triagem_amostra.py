"""Amostra: coleta, enriquece, filtra e tria com o Gemini real. Nao grava nem notifica."""
import importlib, sqlite3, sys
sys.path.insert(0, ".")
import config, filtro, triagem
import main
gupy = importlib.import_module("fontes.gupy")
linkedin = importlib.import_module("fontes.linkedin")

config.TERMOS_LINKEDIN = ["analista de dados", "engenheiro de dados", "analista de CRM"]
config.TERMOS_LINKEDIN_REGIAO = []
config.PAGINAS_LINKEDIN = 1
config.TERMOS_GUPY = ["dados", "CRM"]
config.CIDADES_GUPY = ["Caxias do Sul"]
config.PAGINAS_GUPY_CIDADE = 2
config.LINKEDIN_DETALHES = 20

novas, rep = [], []
for v in linkedin.coletar() + gupy.coletar():
    if filtro.avaliar(v):
        novas.append(v)
    elif v.repescagem:
        rep.append(v)
print(f"regra: {len(novas)} aprovadas, {len(rep)} repescagem")

class Con:  # db de mentira: nada e gravado
    pass
main.db.registrar = lambda con, v, notificada: print(f"  DERRUBADA PELA DESCRICAO: {v.titulo[:60]} | {v.motivo[:60]}")
novas, rep = main.enriquecer_linkedin(Con(), novas, rep, [])
amostra = novas[:30] + rep[:15]
mantidas, cortadas, nao = triagem.triar(amostra)
print(f"\nIA: {len(mantidas)} mantidas, {len(cortadas)} cortadas, {len(nao)} sem avaliacao\n")
for v in sorted(mantidas, key=lambda v: -v.score):
    print(f"MANTIDA s={v.score} | {v.fonte[:8]} | {v.titulo[:50]} | {v.local[:30]} | {v.motivo.split('IA:')[-1][:90]}")
for v in cortadas:
    print(f"CORTADA      | {v.fonte[:8]} | {v.titulo[:50]} | {v.local[:30]} | {v.motivo[:90]}")
