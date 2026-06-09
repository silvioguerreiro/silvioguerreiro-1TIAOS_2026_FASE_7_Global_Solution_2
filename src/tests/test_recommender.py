from core.recommender import score_alerta

def test_mineracao_mais_critica_que_floresta():
    s_min = score_alerta("mineracao", 0.9, 300, True, 0.3)
    s_flo = score_alerta("floresta", 0.9, 300, False, 0.0)
    assert s_min > s_flo
    assert 0 <= s_min <= 1
