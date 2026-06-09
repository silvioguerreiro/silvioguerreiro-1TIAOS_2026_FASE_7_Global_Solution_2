from core.geo import haversine, cell_to_latlon, em_area_protegida
from config import AOI

def test_haversine_conhecido():
    # São Paulo -> Rio de Janeiro ~ 360 km
    d = haversine(-23.55, -46.63, -22.91, -43.17)
    assert 330 < d < 380

def test_cell_dentro_da_aoi():
    lat, lon = cell_to_latlon(0, 0, 8, 8)
    assert AOI["lat_min"] <= lat <= AOI["lat_max"]
    assert AOI["lon_min"] <= lon <= AOI["lon_max"]

def test_area_protegida():
    assert em_area_protegida(-7.5, -63.0) is True
    assert em_area_protegida(-1.0, -50.0) is False
