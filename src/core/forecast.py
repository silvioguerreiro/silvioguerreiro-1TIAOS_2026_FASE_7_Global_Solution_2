"""
Previsão de série temporal de focos de calor (F7·C2 RNN/LSTM, F4·C5 séries
temporais e dados espaciais).
PRIMÁRIO: LSTM (Keras). FALLBACK: regressão autoregressiva linear (numpy lstsq),
mesma interface, para rodar sem TensorFlow.
"""
import numpy as np

try:
    import tensorflow as tf  # noqa
    _HAS_TF = True
except Exception:
    _HAS_TF = False


def make_windows(series, look_back=14):
    X, y = [], []
    for i in range(len(series) - look_back):
        X.append(series[i:i + look_back])
        y.append(series[i + look_back])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


class ForecastModel:
    def __init__(self, look_back=14, force_light=False):
        self.look_back = look_back
        self.light = force_light or not _HAS_TF
        self.model = None
        self._mu = 0.0
        self._sd = 1.0
        self._coef = None  # fallback AR

    def fit(self, series, epochs=20, verbose=0):
        series = np.asarray(series, dtype=np.float32)
        self._mu, self._sd = series.mean(), series.std() + 1e-8
        s = (series - self._mu) / self._sd
        X, y = make_windows(s, self.look_back)
        if self.light:
            # AR linear por mínimos quadrados (com intercepto)
            A = np.concatenate([X, np.ones((len(X), 1), dtype=np.float32)], axis=1)
            self._coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            return {"backend": "numpy-ar"}
        from tensorflow.keras import layers, models
        self.model = models.Sequential([
            layers.Input((self.look_back, 1)),
            layers.LSTM(32),
            layers.Dense(1),
        ])
        self.model.compile(optimizer="adam", loss="mse")
        self.model.fit(X[..., None], y, epochs=epochs, verbose=verbose)
        return {"backend": "keras-lstm"}

    def forecast(self, series, horizon=7):
        """Previsão recursiva dos próximos `horizon` dias."""
        s = (np.asarray(series, dtype=np.float32) - self._mu) / self._sd
        window = list(s[-self.look_back:])
        out = []
        for _ in range(horizon):
            x = np.array(window[-self.look_back:], dtype=np.float32)
            if self.light:
                feat = np.concatenate([x, [1.0]])
                yhat = float(feat @ self._coef)
            else:
                yhat = float(self.model.predict(x[None, :, None], verbose=0)[0, 0])
            window.append(yhat)
            out.append(yhat)
        return (np.array(out) * self._sd + self._mu).clip(0, None)

    @property
    def backend(self):
        return "numpy-ar" if self.light else "keras-lstm"


def tendencia(forecast_vals):
    """Slope normalizado da previsão (>0 = piora prevista)."""
    x = np.arange(len(forecast_vals))
    if forecast_vals.std() == 0:
        return 0.0
    slope = np.polyfit(x, forecast_vals, 1)[0]
    return float(slope / (abs(forecast_vals.mean()) + 1e-8))
