from data.synthetic import generate_fire_timeseries
from core.forecast import ForecastModel

def test_forecast_shape_e_nao_negativo():
    serie = generate_fire_timeseries(120)
    fm = ForecastModel(look_back=14, force_light=True)
    fm.fit(serie)
    fc = fm.forecast(serie, horizon=7)
    assert len(fc) == 7
    assert (fc >= 0).all()
