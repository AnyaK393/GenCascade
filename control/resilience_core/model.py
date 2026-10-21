"""Model bundle shared by training and the live predictor.

A bundle is the uncalibrated base classifier (used for SHAP), an isotonic calibrator fitted on
out-of-fold predictions grouped by episode, an optional time-to-failure regressor, and metadata
(feature order, threshold, training episodes, metrics).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


class FeatureMismatch(RuntimeError):
    """Live feature columns differ from the ones the model was trained on."""


@dataclass
class ModelBundle:
    base: object  # fitted sklearn-style classifier with predict_proba
    calibrator: IsotonicRegression | None
    feature_columns: list[str]
    threshold: float
    name: str = "model"
    ttf: object | None = None  # regressor: seconds to onset, trained on rows with y = 1
    metadata: dict = field(default_factory=dict)

    def raw_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.base.predict_proba(X[self.feature_columns])[:, 1]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Calibrated failure probability within the label horizon."""
        p = self.raw_proba(X)
        return self.calibrator.predict(p) if self.calibrator is not None else p

    def predict_ttf(self, X: pd.DataFrame) -> np.ndarray | None:
        return self.ttf.predict(X[self.feature_columns]) if self.ttf is not None else None

    def check_columns(self, columns: list[str]) -> None:
        if list(columns) != self.feature_columns:
            missing = sorted(set(self.feature_columns) - set(columns))
            extra = sorted(set(columns) - set(self.feature_columns))
            raise FeatureMismatch(f"feature columns differ from the model's: missing {missing}, extra {extra}"
                                  + ("" if missing or extra else ", order differs"))

    def save(self, models_dir: Path = MODELS_DIR) -> Path:
        models_dir.mkdir(parents=True, exist_ok=True)
        path = models_dir / f"{self.name}.joblib"
        joblib.dump(self, path)
        meta = {**self.metadata, "name": self.name, "file": path.name,
                "feature_columns": self.feature_columns, "threshold": self.threshold}
        (models_dir / f"{self.name}.json").write_text(json.dumps(meta, indent=2, default=str))
        return path


def load_bundle(path: Path) -> ModelBundle:
    bundle = joblib.load(path)
    meta_path = path.with_suffix(".json")
    if meta_path.exists():  # the metadata file is the contract; the pickle must agree with it
        meta = json.loads(meta_path.read_text())
        bundle.check_columns(meta["feature_columns"])
        bundle.threshold = float(meta["threshold"])
    return bundle


def activate(bundle: ModelBundle, models_dir: Path = MODELS_DIR) -> None:
    """Make `bundle` the model the live predictor loads (models/metadata.json)."""
    meta = json.loads((models_dir / f"{bundle.name}.json").read_text())
    (models_dir / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))


def load_active(models_dir: Path = MODELS_DIR) -> ModelBundle | None:
    """The model named in models/metadata.json, or None if no model has been trained yet."""
    meta_path = models_dir / "metadata.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    bundle = load_bundle(models_dir / meta["file"])
    bundle.check_columns(meta["feature_columns"])
    return bundle
