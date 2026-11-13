"""Uma busca so, para conferir a chave da SerpApi. Nao grava nem notifica."""
import importlib, sys
sys.path.insert(0, ".")
import config, filtro
google = importlib.import_module("fontes.google")
config.TERMOS_GOOGLE = config.TERMOS_GOOGLE[:1]
vagas = google.coletar(forcar=True)
print(f"total: {len(vagas)}")
for v in vagas:
    print(f"{'OK ' if filtro.avaliar(v) else '-- '} {v.titulo[:50]} | {v.empresa[:20]} | {v.local[:30]} | {v.extras.get('via')} | {v.publicada_em}")
