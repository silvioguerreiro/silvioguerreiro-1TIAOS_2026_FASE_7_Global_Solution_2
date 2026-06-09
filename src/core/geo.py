"""
Georreferenciamento: converte posição (linha, coluna) de uma célula da cena
em coordenadas lat/long dentro da AOI, calcula distâncias (Haversine) e
verifica se um ponto está em área protegida. Base: F3·C6 (estatística de
coordenadas e geolocalização).
"""
import math
from config import AOI, AREA_PROTEGIDA


def cell_to_latlon(row, col, n_rows, n_cols, aoi=AOI):
    """Mapeia o centro da célula (row,col) para (lat, lon) na AOI."""
    frac_y = (row + 0.5) / n_rows
    frac_x = (col + 0.5) / n_cols
    lat = aoi["lat_max"] - frac_y * (aoi["lat_max"] - aoi["lat_min"])
    lon = aoi["lon_min"] + frac_x * (aoi["lon_max"] - aoi["lon_min"])
    return round(lat, 5), round(lon, 5)


def haversine(lat1, lon1, lat2, lon2):
    """Distância em km entre dois pontos geográficos."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def em_area_protegida(lat, lon, poly=AREA_PROTEGIDA):
    return (poly["lat_min"] <= lat <= poly["lat_max"]
            and poly["lon_min"] <= lon <= poly["lon_max"])


def to_geojson(deteccoes):
    """Converte lista de detecções em FeatureCollection GeoJSON."""
    feats = []
    for d in deteccoes:
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]},
            "properties": {k: v for k, v in d.items() if k not in ("lat", "lon")},
        })
    return {"type": "FeatureCollection", "features": feats}
