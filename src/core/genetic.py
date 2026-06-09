"""
Algoritmo Genético (F7·C4) para otimização da ROTA DE PATRULHA de fiscalização:
dado um conjunto de focos (lat/lon), encontra a ordem de visita que minimiza a
distância total (problema do caixeiro viajante). Implementação pura em Python
(sem dependências) com seleção por torneio, crossover ordenado (OX), mutação
por troca e elitismo. Equivale ao DEAP, citado no material.
"""
import random
from core.geo import haversine


def comprimento_rota(ordem, pontos):
    total = 0.0
    for i in range(len(ordem)):
        a = pontos[ordem[i]]
        b = pontos[ordem[(i + 1) % len(ordem)]]
        total += haversine(a[0], a[1], b[0], b[1])
    return total


def _ox(p1, p2, rng):
    """Order Crossover (OX)."""
    n = len(p1)
    a, b = sorted(rng.sample(range(n), 2))
    filho = [None] * n
    filho[a:b] = p1[a:b]
    resto = [g for g in p2 if g not in filho]
    j = 0
    for i in range(n):
        if filho[i] is None:
            filho[i] = resto[j]
            j += 1
    return filho


def _mutacao_swap(ordem, taxa, rng):
    o = ordem[:]
    for i in range(len(o)):
        if rng.random() < taxa:
            j = rng.randrange(len(o))
            o[i], o[j] = o[j], o[i]
    return o


def otimizar_rota(pontos, geracoes=120, pop=60, taxa_mut=0.15,
                  elite=4, seed=42):
    """
    pontos: lista de (lat, lon). Retorna (melhor_ordem, melhor_dist, historico).
    """
    n = len(pontos)
    if n <= 2:
        ordem = list(range(n))
        return ordem, comprimento_rota(ordem, pontos) if n else 0.0, []
    rng = random.Random(seed)
    populacao = [rng.sample(range(n), n) for _ in range(pop)]
    historico = []
    melhor, melhor_d = None, float("inf")
    for _ in range(geracoes):
        scores = [(comprimento_rota(ind, pontos), ind) for ind in populacao]
        scores.sort(key=lambda t: t[0])
        if scores[0][0] < melhor_d:
            melhor_d, melhor = scores[0][0], scores[0][1][:]
        historico.append(round(scores[0][0], 3))
        nova = [s[1] for s in scores[:elite]]            # elitismo
        while len(nova) < pop:
            # seleção por torneio
            t1 = min(rng.sample(scores, 3), key=lambda t: t[0])[1]
            t2 = min(rng.sample(scores, 3), key=lambda t: t[0])[1]
            filho = _ox(t1, t2, rng)
            filho = _mutacao_swap(filho, taxa_mut, rng)
            nova.append(filho)
        populacao = nova
    return melhor, round(melhor_d, 3), historico
