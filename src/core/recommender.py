"""
Priorização inteligente de alertas (F6·C13 sistemas de recomendação).
Combina severidade da classe, confiança do modelo, área afetada, presença em
área protegida e tendência prevista (RNN) em um score 0-1, e ranqueia os focos
que a fiscalização deve atender primeiro.
"""
from config import CLASS_SEVERITY


def score_alerta(classe, confianca, area_ha, em_area_protegida,
                 fator_tendencia=0.0, area_ref=500.0):
    sev = CLASS_SEVERITY.get(classe, 0.1)
    area_norm = min(area_ha / area_ref, 1.0)
    bonus_zona = 0.15 if em_area_protegida else 0.0
    bonus_trend = max(0.0, min(fator_tendencia, 1.0)) * 0.15
    base = 0.45 * sev + 0.20 * confianca + 0.20 * area_norm
    return round(min(base + bonus_zona + bonus_trend, 1.0), 4)


def priorizar(deteccoes, fator_tendencia=0.0):
    """Adiciona 'prioridade' a cada detecção e ordena desc."""
    out = []
    for d in deteccoes:
        p = score_alerta(d["classe"], d["confianca"], d["area_ha"],
                         d["em_area_protegida"], fator_tendencia)
        out.append({**d, "prioridade": p})
    out.sort(key=lambda x: x["prioridade"], reverse=True)
    return out
