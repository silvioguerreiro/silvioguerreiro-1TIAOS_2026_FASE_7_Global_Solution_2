"""Gera figuras de demonstração dos resultados do SENTINELA (docs/figuras)."""
import os
os.environ.setdefault("SENTINELA_HOME", "/tmp/sentinela_fig")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from config import CLASSES, SCENE_GRID, IMG_SIZE
from data.synthetic import (generate_landuse_dataset, generate_scene,
                            generate_fire_timeseries)
from core.vision import VisionModel, detectar_cena
from core.forecast import ForecastModel
from core.genetic import otimizar_rota
from core.geo import cell_to_latlon

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "figuras")

# ---- 1) Cena + detecções ----
Xtr, ytr = generate_landuse_dataset(80, seed=42)
vm = VisionModel(force_light=True); vm.train(Xtr, ytr)
scene, cells, truth = generate_scene(grid=SCENE_GRID, seed=7)
dets = detectar_cena(vm, cells)
fig, ax = plt.subplots(figsize=(6, 6))
ax.imshow(scene)
cor = {"mineracao": "yellow", "queimada": "red"}
for d in dets:
    if d["classe"] in cor:
        y, x = d["row"] * IMG_SIZE, d["col"] * IMG_SIZE
        ax.add_patch(Rectangle((x, y), IMG_SIZE, IMG_SIZE, fill=False,
                     edgecolor=cor[d["classe"]], lw=2.5))
        ax.text(x + 1, y + 5, d["classe"][:4], color=cor[d["classe"]],
                fontsize=7, weight="bold")
ax.set_title("SENTINELA — Detecção de anomalias na cena orbital")
ax.axis("off")
plt.tight_layout(); plt.savefig(f"{OUT}/fig_cena_deteccoes.png", dpi=130); plt.close()

# ---- 2) Previsão de focos ----
serie = generate_fire_timeseries(180)
fm = ForecastModel(look_back=14, force_light=True); fm.fit(serie)
fc = fm.forecast(serie, horizon=14)
fig, ax = plt.subplots(figsize=(8, 3.5))
ax.plot(range(len(serie)), serie, label="histórico (NASA FIRMS proxy)", color="#1f77b4")
ax.plot(range(len(serie), len(serie) + len(fc)), fc, "--o", ms=3,
        label="previsão (RNN/LSTM)", color="#d62728")
ax.axvline(len(serie), color="gray", ls=":")
ax.set_title("Previsão de focos de calor"); ax.set_xlabel("dia"); ax.set_ylabel("focos")
ax.legend(); plt.tight_layout(); plt.savefig(f"{OUT}/fig_previsao.png", dpi=130); plt.close()

# ---- 3) Rota de patrulha (AG) ----
pts = []
for d in dets:
    if d["classe"] in ("mineracao", "queimada"):
        pts.append(cell_to_latlon(d["row"], d["col"], SCENE_GRID, SCENE_GRID))
rota, dist, hist = otimizar_rota(pts, geracoes=150, pop=60, seed=42)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
lons = [p[1] for p in pts]; lats = [p[0] for p in pts]
a1.scatter(lons, lats, c="red", zorder=3)
ordem = rota + [rota[0]]
a1.plot([pts[i][1] for i in ordem], [pts[i][0] for i in ordem], "-", color="#2ca02c")
a1.set_title(f"Rota ótima de patrulha (AG) — {dist} km")
a1.set_xlabel("longitude"); a1.set_ylabel("latitude")
a2.plot(hist, color="#9467bd"); a2.set_title("Convergência do Algoritmo Genético")
a2.set_xlabel("geração"); a2.set_ylabel("distância (km)")
plt.tight_layout(); plt.savefig(f"{OUT}/fig_rota_ga.png", dpi=130); plt.close()
print("figuras geradas:", os.listdir(OUT))
