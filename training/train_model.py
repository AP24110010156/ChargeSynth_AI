"""Reproduce the bundled simulation-trained CVAE: python training/train_model.py.

This deliberately uses an openly described simulation, NOT observed EV records.
The fixed split is created before fitting any scaling or model weights.
"""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.vae import ConditionalVAE, FEATURES, DAY_TYPES, CHARGERS, conditions, LOW, HIGH


def simulated_reference(n=3000, seed=2026):
    rng = np.random.default_rng(seed)
    days = np.array(DAY_TYPES)[rng.integers(0, 4, n)]
    chargers = np.array(CHARGERS)[rng.integers(0, 3, n)]
    values = []
    for day, charger in zip(days, chargers):
        busy = {"weekday": 1., "weekend": 1.25, "holiday": 1.5, "festival": 1.9}[day]
        center = {"weekday": 8.8, "weekend": 12.2, "holiday": 12.8, "festival": 16.0}[day]
        hour = rng.normal(center if rng.random() < .73 else 18, 1.8)
        peak = np.exp(-((hour - center) / 3) ** 2)
        queue = rng.gamma(1.5, 3.5 * busy) * (.7 + .5 * peak)
        soc = rng.normal(38 if charger == "dc60" else 45, 13)
        gain = rng.beta(5, 3) if charger == "dc60" else rng.beta(7, 2)
        power = rng.normal(.78 if charger == "dc60" else .88, .04)
        idle = rng.gamma(2, 2 if charger == "dc60" else 6)
        exit_delay = rng.gamma(2, 1.2)
        values.append([hour, queue, soc, gain, power, idle, exit_delay])
    return np.clip(np.array(values), LOW, HIGH), days, chargers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=260)
    args = parser.parse_args()
    (ROOT / "model").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    raw, days, chargers = simulated_reference()
    permutation = np.random.default_rng(17).permutation(len(raw))
    train, heldout = permutation[:2400], permutation[2400:]
    with (ROOT / "data/reference_features.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["reference_id", "split", "day_type", "charger_type", *FEATURES, "provenance"])
        train_set = set(train.tolist())
        for i, row in enumerate(raw):
            writer.writerow([f"REF-{i+1:04d}", "train" if i in train_set else "heldout",
                             days[i], chargers[i], *row, "rule_based_simulation"])
    c = conditions(days, chargers)
    model = ConditionalVAE()
    started = time.perf_counter()
    history = model.fit(raw[train], c[train], epochs=args.epochs)
    train_seconds = time.perf_counter() - started
    model.save(ROOT / "model/chargesynth_cvae.npz")
    generated, adjusted = model.sample(c[heldout], np.random.default_rng(99))
    comparison = []
    for i, feature in enumerate(FEATURES):
        reference = raw[heldout, i]
        synth = generated[:, i]
        comparison.append({"feature": feature, "reference_mean": round(float(reference.mean()), 3),
                           "generated_mean": round(float(synth.mean()), 3),
                           "reference_std": round(float(reference.std()), 3),
                           "generated_std": round(float(synth.std()), 3)})
    corr_diff = float(np.mean(np.abs(np.corrcoef(raw[heldout].T) - np.corrcoef(generated.T))))
    checksum = hashlib.sha256((ROOT / "data/reference_features.csv").read_bytes()).hexdigest()
    info = {"name": "ChargeSynth Conditional VAE", "version": "1.0", "engine": "NumPy CVAE",
            "training_source": "Simulated reference data; not real station observations",
            "reference_rows": len(raw), "training_rows": len(train), "heldout_rows": len(heldout),
            "epochs": args.epochs, "latent_dimensions": model.latent, "hidden_units": 40,
            "parameters": sum(v.size for v in model.p.values()), "features": FEATURES,
            "conditions": {"day_type": DAY_TYPES, "charger_type": CHARGERS},
            "training_seconds": round(train_seconds, 2), "reference_sha256": checksum,
            "initial_training_loss": round(history[0]["loss"], 4),
            "final_training_loss": round(history[-1]["loss"], 4),
            "evaluation": {"basis": "600 held-out simulated reference feature records",
                           "feature_comparison": comparison,
                           "mean_absolute_correlation_difference": round(corr_diff, 4),
                           "clipped_sample_count": adjusted, "sample_count": len(heldout)},
            "limitations": ["Trained on a documented simulation, not observed charging behaviour.",
                            "Holiday and festival labels describe hypothetical scenarios, not a verified calendar.",
                            "The decoder samples independent features; the app separately calculates finite-port queues and ignores the legacy queue feature.",
                            "Vehicle capacity, efficiency and charging-power assumptions are assigned by rules.",
                            "No claim of demand-forecasting accuracy or real-world deployment validity."]}
    (ROOT / "model/model_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    (ROOT / "model/training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(json.dumps({"training_seconds": info["training_seconds"], "initial_loss": info["initial_training_loss"],
                      "final_loss": info["final_training_loss"], "evaluation": info["evaluation"]}, indent=2))


if __name__ == "__main__":
    main()
