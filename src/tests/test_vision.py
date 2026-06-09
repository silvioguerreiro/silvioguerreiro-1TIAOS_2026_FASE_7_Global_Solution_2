from data.synthetic import generate_landuse_dataset, generate_scene
from core.vision import VisionModel, detectar_cena, avaliar
from config import SCENE_GRID

def test_classificador_aprende():
    Xtr, ytr = generate_landuse_dataset(60, seed=1)
    Xte, yte = generate_landuse_dataset(20, seed=2)
    vm = VisionModel(force_light=True)
    vm.train(Xtr, ytr)
    assert avaliar(vm, Xte, yte) > 0.7   # bem acima do acaso (0.2)

def test_deteccao_cena():
    vm = VisionModel(force_light=True)
    Xtr, ytr = generate_landuse_dataset(60, seed=1); vm.train(Xtr, ytr)
    _, cells, _ = generate_scene(grid=SCENE_GRID, seed=7)
    dets = detectar_cena(vm, cells)
    assert len(dets) == SCENE_GRID * SCENE_GRID
    assert all(0 <= d["confianca"] <= 1 for d in dets)
