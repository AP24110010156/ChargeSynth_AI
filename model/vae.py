"""Small conditional variational autoencoder implemented in NumPy.

The encoder is needed for training only. The app loads the learned decoder.
No cloud call, GPU, pickle, or large neural-network runtime is needed.
"""
from pathlib import Path
import numpy as np

FEATURES = ["arrival_hour", "queue_minutes", "soc_in", "gain_fraction",
            "power_fraction", "post_charge_minutes", "exit_delay_minutes"]
DAY_TYPES = ["weekday", "weekend", "holiday", "festival"]
CHARGERS = ["ac7", "ac22", "dc60"]
LOG_COLUMNS = [1, 5, 6]
LOW = np.array([0, 0, 5, .05, .40, 0, 0], dtype=float)
HIGH = np.array([23.98, 120, 85, .95, .95, 90, 30], dtype=float)


def conditions(day_types, chargers):
    out = np.zeros((len(day_types), 7))
    for i, (day, charger) in enumerate(zip(day_types, chargers)):
        out[i, DAY_TYPES.index(day)] = 1
        out[i, 4 + CHARGERS.index(charger)] = 1
    return out


def transform(raw):
    out = np.array(raw, dtype=float, copy=True)
    out[:, LOG_COLUMNS] = np.log1p(out[:, LOG_COLUMNS])
    return out


def inverse_transform(values):
    out = np.array(values, dtype=float, copy=True)
    out[:, LOG_COLUMNS] = np.expm1(np.clip(out[:, LOG_COLUMNS], -5, 9))
    return out


class ConditionalVAE:
    """tanh encoder/decoder; Gaussian latent; MSE + beta-weighted KL loss."""

    def __init__(self, seed=41, hidden=40, latent=4):
        rng = np.random.default_rng(seed)
        self.latent = latent
        self.p = {}
        for name, shape in {"E": (14, hidden), "M": (hidden, latent),
                            "V": (hidden, latent), "D": (latent + 7, hidden),
                            "O": (hidden, 7)}.items():
            self.p[name] = rng.normal(0, np.sqrt(2 / sum(shape)), shape)
            self.p["b" + name] = np.zeros(shape[1])
        self.mean = np.zeros(7)
        self.scale = np.ones(7)

    def loss_and_grads(self, x, c, eps, beta=.06):
        p = self.p
        batch = len(x)
        xc = np.concatenate([x, c], axis=1)
        h = np.tanh(xc @ p["E"] + p["bE"])
        mu = h @ p["M"] + p["bM"]
        unbounded_lv = h @ p["V"] + p["bV"]
        lv = np.clip(unbounded_lv, -7, 3)
        std = np.exp(.5 * lv)
        z = mu + eps * std
        zc = np.concatenate([z, c], axis=1)
        hd = np.tanh(zc @ p["D"] + p["bD"])
        out = hd @ p["O"] + p["bO"]
        reconstruction = np.sum((out - x) ** 2) / batch
        kl = .5 * np.sum(mu ** 2 + np.exp(lv) - 1 - lv) / batch
        d_out = 2 * (out - x) / batch
        grads = {"O": hd.T @ d_out, "bO": d_out.sum(0)}
        d_hd = (d_out @ p["O"].T) * (1 - hd ** 2)
        grads.update(D=zc.T @ d_hd, bD=d_hd.sum(0))
        d_z = (d_hd @ p["D"].T)[:, :self.latent]
        d_mu = d_z + beta * mu / batch
        d_lv = .5 * d_z * eps * std + beta * .5 * (np.exp(lv) - 1) / batch
        d_lv *= (unbounded_lv > -7) & (unbounded_lv < 3)
        grads.update(M=h.T @ d_mu, bM=d_mu.sum(0), V=h.T @ d_lv, bV=d_lv.sum(0))
        d_h = (d_mu @ p["M"].T + d_lv @ p["V"].T) * (1 - h ** 2)
        grads.update(E=xc.T @ d_h, bE=d_h.sum(0))
        return float(reconstruction + beta * kl), float(reconstruction), float(kl), grads

    def fit(self, raw, c, epochs=260, batch_size=128, learning_rate=.0015, seed=42):
        rng = np.random.default_rng(seed)
        transformed = transform(raw)
        self.mean = transformed.mean(0)
        self.scale = np.maximum(transformed.std(0), .001)
        x = (transformed - self.mean) / self.scale
        first = {k: np.zeros_like(v) for k, v in self.p.items()}
        second = {k: np.zeros_like(v) for k, v in self.p.items()}
        step = 0
        history = []
        for epoch in range(epochs):
            idx = rng.permutation(len(x))
            losses = []
            beta = .12 * min(1., (epoch + 1) / 60)
            for start in range(0, len(x), batch_size):
                ix = idx[start:start + batch_size]
                eps = rng.normal(size=(len(ix), self.latent))
                total, rec, kl, gradients = self.loss_and_grads(x[ix], c[ix], eps, beta)
                step += 1
                for k, grad in gradients.items():
                    grad = np.clip(grad, -5, 5)
                    first[k] = .9 * first[k] + .1 * grad
                    second[k] = .999 * second[k] + .001 * grad * grad
                    self.p[k] -= learning_rate * (first[k] / (1 - .9 ** step)) / (
                        np.sqrt(second[k] / (1 - .999 ** step)) + 1e-8)
                losses.append([total, rec, kl])
            avg = np.mean(losses, axis=0)
            history.append({"epoch": epoch + 1, "loss": float(avg[0]),
                            "reconstruction": float(avg[1]), "kl": float(avg[2]), "beta": beta})
            if (epoch + 1) % 50 == 0:
                print(f"Epoch {epoch + 1}/{epochs} | loss {avg[0]:.4f}", flush=True)
        return history

    def sample(self, c, rng):
        z = rng.normal(size=(len(c), self.latent))
        hidden = np.tanh(np.concatenate([z, c], axis=1) @ self.p["D"] + self.p["bD"])
        normalized = hidden @ self.p["O"] + self.p["bO"]
        raw = inverse_transform(normalized * self.scale + self.mean)
        if not np.isfinite(raw).all():
            raise ValueError("The model produced non-finite values. Retrain the model.")
        changed = np.any((raw < LOW) | (raw > HIGH), axis=1)
        return np.clip(raw, LOW, HIGH), int(changed.sum())

    def save(self, path):
        np.savez_compressed(path, **self.p, mean=self.mean, scale=self.scale,
                            latent=np.array([self.latent]))

    @classmethod
    def load(cls, path):
        with np.load(Path(path), allow_pickle=False) as archive:
            model = cls(latent=int(archive["latent"][0]), hidden=archive["D"].shape[1])
            model.p = {key: archive[key].copy() for key in model.p}
            model.mean = archive["mean"].copy()
            model.scale = archive["scale"].copy()
        return model
