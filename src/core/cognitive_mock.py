"""
[SIMULADO] Serviço cognitivo estilo AWS Rekognition (F7·C7 IA como serviço).
Em produção: boto3.client('rekognition').detect_labels(...). Aqui retornamos
rótulos derivados das estatísticas da imagem, de forma determinística, para
demonstrar a INTEGRAÇÃO do serviço cognitivo no pipeline sem custo/conta AWS.
"""
import numpy as np


def detect_labels(patch, classe_sugerida=None):
    r, g, b = patch.mean(axis=(0, 1))
    escuro = patch.mean() < 0.25
    labels = []
    if g > r and g > b:
        labels.append(("Vegetation", round(float(g) * 100, 1)))
    if b > r and b > g:
        labels.append(("Water", round(float(b) * 100, 1)))
    if escuro:
        labels.append(("BurnScar", 82.0))
    if r > 0.55 and g > 0.45 and b < 0.6:
        labels.append(("BareSoil", 76.0))
    if classe_sugerida:
        labels.append((f"ML::{classe_sugerida}", 90.0))
    return {"source": "MOCK-Rekognition", "labels": labels or [("Unknown", 50.0)]}
