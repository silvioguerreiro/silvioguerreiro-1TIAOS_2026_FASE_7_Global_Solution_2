from run_demo import executar_pipeline

def test_pipeline_ponta_a_ponta():
    r = executar_pipeline(treinar_keras=False)
    for k in ["vision_acc", "n_alertas", "previsao_7d", "rota_dist_km"]:
        assert k in r
    assert r["n_deteccoes"] >= 1
    assert r["n_alertas"] >= 1
    assert len(r["previsao_7d"]) == 7
