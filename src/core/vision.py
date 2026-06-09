"""
Visão Computacional - classificação de uso do solo (F6·C9 CNN, F6·C10 detecção).
Modelo PRIMÁRIO: CNN em TensorFlow/Keras (transfer-learning-ready).
FALLBACK: classificador puro-numpy (nearest-centroid sobre features de cor/textura),
com a MESMA interface, para rodar em ambientes sem TensorFlow.
Detecção na cena = janela deslizante classificando cada célula.
"""
import numpy as np
from config import CLASSES, IMG_SIZE

try:
    import tensorflow as tf  # noqa
    _HAS_TF = True
except Exception:
    _HAS_TF = False


# ---------------- Fallback numpy ----------------
def _features(X):
    """Extrai features simples: média e desvio por canal + pooling 4x4."""
    n = X.shape[0]
    mean = X.mean(axis=(1, 2))                      # (n,3)
    std = X.std(axis=(1, 2))                        # (n,3)
    s = X.shape[1] // 4
    pooled = X[:, :4 * s, :4 * s, :].reshape(n, 4, s, 4, s, 3).mean(axis=(2, 4))
    pooled = pooled.reshape(n, -1)                  # (n,48)
    return np.concatenate([mean, std, pooled], axis=1)


class _CentroidModel:
    """Nearest-centroid: rápido, determinístico, sem dependências externas."""
    def __init__(self):
        self.centroids = None

    def fit(self, X, y, **_):
        F = _features(X)
        self.centroids = np.stack([F[y == k].mean(axis=0)
                                   for k in range(len(CLASSES))])
        return self

    def _logits(self, X):
        F = _features(X)
        d = np.linalg.norm(F[:, None, :] - self.centroids[None, :, :], axis=2)
        return -d

    def predict_proba(self, X):
        z = self._logits(X)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)


# ---------------- Modelo Keras (primário) ----------------
def build_cnn(num_classes=len(CLASSES), img_size=IMG_SIZE):
    """CNN compacta. Em produção, troque por MobileNetV2 + transfer learning."""
    from tensorflow.keras import layers, models
    m = models.Sequential([
        layers.Input((img_size, img_size, 3)),
        layers.Conv2D(16, 3, activation="relu", padding="same"),
        layers.MaxPooling2D(),
        layers.Conv2D(32, 3, activation="relu", padding="same"),
        layers.MaxPooling2D(),
        layers.Flatten(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(num_classes, activation="softmax"),
    ])
    m.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
              metrics=["accuracy"])
    return m


class VisionModel:
    """Wrapper unificado: usa Keras se disponível, senão fallback numpy."""
    def __init__(self, force_light=False):
        self.light = force_light or not _HAS_TF
        self.model = _CentroidModel() if self.light else build_cnn()

    def train(self, X, y, epochs=8, verbose=0):
        if self.light:
            self.model.fit(X, y)
            return {"backend": "numpy-centroid"}
        h = self.model.fit(X, y, epochs=epochs, batch_size=32,
                           validation_split=0.2, verbose=verbose)
        return {"backend": "keras-cnn", "history": h.history}

    def predict_proba(self, X):
        if self.light:
            return self.model.predict_proba(X)
        return self.model.predict(X, verbose=0)

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)

    @property
    def backend(self):
        return "numpy-centroid" if self.light else "keras-cnn"


def detectar_cena(model, cells):
    """
    Janela deslizante: classifica cada célula da cena (grid,grid,h,w,3).
    Retorna lista de detecções {row,col,classe,confianca}.
    """
    g = cells.shape[0]
    flat = cells.reshape(g * g, *cells.shape[2:])
    proba = model.predict_proba(flat)
    idx = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    dets = []
    for i in range(g * g):
        dets.append({"row": i // g, "col": i % g,
                     "classe": CLASSES[idx[i]],
                     "confianca": round(float(conf[i]), 4)})
    return dets


def avaliar(model, X, y):
    return float((model.predict(X) == y).mean())
