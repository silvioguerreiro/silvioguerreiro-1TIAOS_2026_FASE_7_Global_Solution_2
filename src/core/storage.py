"""
Persistência. SQL (SQLite, stdlib) guarda detecções e alertas geolocalizados;
NoSQL (mongomock, em memória) guarda telemetria dos sensores de campo (ESP32).
Base: F3·C7 (SQL), F5·C3-5 e F6·C4-5 (SQL/NoSQL/agregação).
"""
import sqlite3
import json
import datetime as dt
from config import DB_PATH


def _utcnow_iso():
    """Timestamp UTC em ISO (segundos), sem offset — substitui utcnow() depreciado."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

# ---------- NoSQL (telemetria) ----------
try:
    import mongomock
    _mongo = mongomock.MongoClient()
    _telemetry = _mongo["sentinela"]["telemetria"]
    _NOSQL = "mongomock"
except Exception:  # fallback se mongomock ausente
    _telemetry = None
    _NOSQL = "memoria"
    _mem_telemetry = []


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = conectar()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS deteccoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, classe TEXT, confianca REAL,
            lat REAL, lon REAL, area_ha REAL,
            severidade REAL, em_area_protegida INTEGER
        );
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, deteccao_id INTEGER, prioridade REAL,
            mensagem TEXT, status TEXT DEFAULT 'ABERTO'
        );
        """
    )
    con.commit()
    con.close()


def limpar():
    con = conectar()
    con.executescript("DELETE FROM deteccoes; DELETE FROM alertas;")
    con.commit()
    con.close()
    if _telemetry is not None:
        _telemetry.delete_many({})
    else:
        _mem_telemetry.clear()


def inserir_deteccao(d):
    con = conectar()
    cur = con.execute(
        """INSERT INTO deteccoes
           (ts,classe,confianca,lat,lon,area_ha,severidade,em_area_protegida)
           VALUES (?,?,?,?,?,?,?,?)""",
        (_utcnow_iso(), d["classe"],
         d["confianca"], d["lat"], d["lon"], d["area_ha"],
         d["severidade"], int(d["em_area_protegida"])),
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def inserir_alerta(deteccao_id, prioridade, mensagem):
    con = conectar()
    cur = con.execute(
        "INSERT INTO alertas (ts,deteccao_id,prioridade,mensagem) VALUES (?,?,?,?)",
        (_utcnow_iso(), deteccao_id,
         prioridade, mensagem),
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def listar_deteccoes():
    con = conectar()
    rows = [dict(r) for r in con.execute("SELECT * FROM deteccoes ORDER BY id")]
    con.close()
    return rows


def listar_alertas():
    con = conectar()
    rows = [dict(r) for r in
            con.execute("SELECT * FROM alertas ORDER BY prioridade DESC")]
    con.close()
    return rows


def registrar_telemetria(doc):
    """Grava leitura de sensor de campo (NoSQL)."""
    doc = dict(doc)
    doc["ts"] = _utcnow_iso()
    if _telemetry is not None:
        _telemetry.insert_one(doc)
    else:
        _mem_telemetry.append(doc)
    return doc


def listar_telemetria():
    if _telemetry is not None:
        return [{k: v for k, v in d.items() if k != "_id"}
                for d in _telemetry.find()]
    return list(_mem_telemetry)


def backend_nosql():
    return _NOSQL
