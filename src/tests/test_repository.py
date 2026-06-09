"""
Testes do repositório local / data lake (data/repository.py).
Todos OFFLINE: redirecionam as paths do lake para um tmp e exercitam
acúmulo + deduplicação de focos FIRMS e cenas Sentinel-2 (sem tocar a rede).
"""
import pandas as pd
import pytest

from data import repository as repo
from data import ingest


FIRMS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-7.5,-63.2,330.1,0.4,0.36,2026-06-01,1715,N,VIIRS,h,2.0NRT,295.0,12.5,D\n"
    "-8.1,-61.7,310.0,0.4,0.36,2026-06-01,1716,N,VIIRS,n,2.0NRT,290.0,5.1,D\n"
    "-6.9,-64.0,300.0,0.4,0.36,2026-06-02,1700,N,VIIRS,l,2.0NRT,288.0,1.0,D\n"
)


@pytest.fixture(autouse=True)
def lake_tmp(tmp_path, monkeypatch):
    """Redireciona o lake para um diretório temporário isolado por teste."""
    monkeypatch.setattr(repo, "FIRMS_STORE", tmp_path / "firms.parquet")
    monkeypatch.setattr(repo, "SCENES_STORE", tmp_path / "scenes.json")
    monkeypatch.setattr(repo, "MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(repo, "LAKE_DIR", tmp_path)
    return tmp_path


def test_load_vazio():
    assert repo.load_fire_foci().empty
    assert repo.load_scenes() == []
    s = repo.stats()
    assert s["firms_foci"] == 0 and s["s2_scenes"] == 0


def test_append_firms_acumula_e_persiste():
    df = ingest._parse_firms_csv(FIRMS_CSV)
    novos = repo.append_fire_foci(df)
    assert novos == 3
    assert len(repo.load_fire_foci()) == 3
    assert repo.FIRMS_STORE.exists()


def test_append_firms_dedup():
    df = ingest._parse_firms_csv(FIRMS_CSV)
    repo.append_fire_foci(df)
    # reaplicar os mesmos focos não deve duplicar
    novos = repo.append_fire_foci(df)
    assert novos == 0
    assert len(repo.load_fire_foci()) == 3


def test_append_firms_incremental():
    df = ingest._parse_firms_csv(FIRMS_CSV)
    repo.append_fire_foci(df.iloc[:2])
    novos = repo.append_fire_foci(df)        # 2 já existem, 1 novo
    assert novos == 1
    assert len(repo.load_fire_foci()) == 3


def test_timeseries_do_lake():
    repo.append_fire_foci(ingest._parse_firms_csv(FIRMS_CSV))
    serie = repo.fire_foci_timeseries()
    assert serie.tolist() == [2.0, 1.0]      # 2 focos em 01/06, 1 em 02/06


def test_append_scenes_dedup_por_id():
    cenas = [{"id": "A", "datetime": "2026-01-01", "cloud": 1},
             {"id": "B", "datetime": "2026-02-01", "cloud": 2}]
    assert repo.append_scenes(cenas) == 2
    # B repetida + C nova -> +1
    novas = repo.append_scenes([{"id": "B", "datetime": "2026-02-01", "cloud": 2},
                                {"id": "C", "datetime": "2026-03-01", "cloud": 3}])
    assert novas == 1
    cat = repo.load_scenes()
    assert {c["id"] for c in cat} == {"A", "B", "C"}
    # ordenadas por datetime desc
    assert cat[0]["id"] == "C"


def test_stats_reflete_periodo_e_contagens():
    repo.append_fire_foci(ingest._parse_firms_csv(FIRMS_CSV))
    repo.append_scenes([{"id": "A", "datetime": "2026-01-01"}])
    s = repo.stats()
    assert s["firms_foci"] == 3
    assert s["s2_scenes"] == 1
    assert s["firms_periodo"] == ["2026-06-01", "2026-06-02"]
    assert s["last_sync"] is not None       # manifesto gravado no append
