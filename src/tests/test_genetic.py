from core.genetic import otimizar_rota, comprimento_rota

def test_rota_valida_e_melhora():
    pts = [(-7.0, -63.0), (-8.0, -61.0), (-5.5, -64.0),
           (-9.0, -62.0), (-6.0, -60.5), (-7.5, -62.5)]
    naive = comprimento_rota(list(range(len(pts))), pts)
    rota, dist, hist = otimizar_rota(pts, geracoes=80, pop=40, seed=42)
    assert sorted(rota) == list(range(len(pts)))   # é permutação válida
    assert dist <= naive                            # não piora a rota
    assert hist[-1] <= hist[0]                       # convergiu
