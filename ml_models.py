"""
Sandi Bot - ML components: K-Means persona clustering, conversion probability.
Feature scaling, cluster labeling, prediction for new prospects.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from typing import List, Optional, Tuple

COMPARTMENTS_ORDER = [
    "Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment",
]
PERSONA_LABELS = ["Quiet Decider", "Overthinker", "Burning Bridge", "Strategic"]


def _compartment_to_ord(compartment: str) -> int:
    try:
        return COMPARTMENTS_ORDER.index(compartment) + 1
    except ValueError:
        return 1


def _build_feature_matrix(prospects: List[dict]) -> np.ndarray:
    rows = []
    for p in prospects:
        rows.append([
            p.get("identity_score", 3), p.get("commitment_score", 3),
            p.get("financial_score", 3), p.get("execution_score", 3),
            _compartment_to_ord(p.get("compartment", "Discovery")),
            p.get("compartment_days", 0),
        ])
    return np.array(rows, dtype=float)


class SandiML:
    def __init__(self, n_clusters: int = 4):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.kmeans: Optional[KMeans] = None
        self.cluster_to_persona: dict = {}
        self._fitted = False

    def fit(self, prospects: List[dict]) -> "SandiML":
        if not prospects:
            return self
        X = _build_feature_matrix(prospects)
        X_scaled = self.scaler.fit_transform(X)
        self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        self.kmeans.fit(X_scaled)
        df = pd.DataFrame(prospects)
        if "persona" in df.columns:
            df["cluster"] = self.kmeans.labels_
            mapping = df.groupby("cluster")["persona"].agg(
                lambda s: s.mode().iloc[0] if len(s) else PERSONA_LABELS[0]
            ).to_dict()
            self.cluster_to_persona = mapping
        else:
            self.cluster_to_persona = {i: PERSONA_LABELS[i % len(PERSONA_LABELS)] for i in range(self.n_clusters)}
        self._fitted = True
        return self

    def predict_persona(self, prospect: dict) -> str:
        if not self._fitted or self.kmeans is None:
            return prospect.get("persona", "Strategic")
        X = _build_feature_matrix([prospect])
        X_scaled = self.scaler.transform(X)
        label = self.kmeans.predict(X_scaled)[0]
        return self.cluster_to_persona.get(label, PERSONA_LABELS[label % len(PERSONA_LABELS)])

    def predict_personas_batch(self, prospects: List[dict]) -> List[str]:
        if not prospects:
            return []
        if not self._fitted or self.kmeans is None:
            return [p.get("persona", "Strategic") for p in prospects]
        X = _build_feature_matrix(prospects)
        X_scaled = self.scaler.transform(X)
        labels = self.kmeans.predict(X_scaled)
        return [self.cluster_to_persona.get(l, PERSONA_LABELS[l % len(PERSONA_LABELS)]) for l in labels]

    def conversion_probability(self, prospect: dict) -> float:
        i, c, f, e = (
            prospect.get("identity_score", 3), prospect.get("commitment_score", 3),
            prospect.get("financial_score", 3), prospect.get("execution_score", 3),
        )
        comp = prospect.get("compartment", "Discovery")
        days = prospect.get("compartment_days", 0)
        persona = prospect.get("persona", "Strategic")
        avg = (i + c + f + e) / 4.0
        stage_bonus = {"Discovery": 0.1, "Exploration": 0.2, "Serious Consideration": 0.4, "Decision Prep": 0.7, "Commitment": 0.9}.get(comp, 0.2)
        stall_penalty = 0.15 if (persona == "Overthinker" and days > 30) else 0.0
        p = (avg / 5.0) * 0.5 + stage_bonus * 0.5 - stall_penalty
        return round(max(0.0, min(1.0, p)), 3)

    def get_similar_prospects(self, prospects: List[dict], reference: dict, top_n: int = 10) -> List[dict]:
        if not prospects or not self._fitted:
            return prospects[:top_n]
        X = _build_feature_matrix(prospects)
        ref = _build_feature_matrix([reference])
        X_scaled = self.scaler.transform(X)
        ref_scaled = self.scaler.transform(ref)
        dists = np.linalg.norm(X_scaled - ref_scaled[0], axis=1)
        idx = np.argsort(dists)
        out = []
        for i in idx:
            if prospects[i].get("prospect_id") != reference.get("prospect_id"):
                out.append(prospects[i])
                if len(out) >= top_n:
                    break
        return out


def build_and_fit_ml(prospects: List[dict]) -> SandiML:
    model = SandiML(n_clusters=4)
    model.fit(prospects)
    return model
