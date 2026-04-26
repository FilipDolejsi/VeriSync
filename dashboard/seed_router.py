"""
router/seed_router.py
─────────────────────
Generates synthetic code-review episodes spanning every model tier in
registry.yaml so the personalised router has a warm-start dataset.

Run:
    python -m router.seed_router --episodes 600 --out router/seed_data.jsonl

What it generates per episode:
    - a synthetic PR chunk (language, lines_changed, classifier_tag)
    - the model that "won" the routing decision
    - the resulting finding (severity, category, accepted)
    - the cost in sats

After generating the JSONL it (re)trains the personalised router and
saves the joblib artifact next to router_model.joblib.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib  # type: ignore
from sklearn.feature_extraction import DictVectorizer  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn.pipeline import Pipeline  # type: ignore

from registry.loader import load_registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("seed_router")

# ───────────────────── synthetic distribution ──────────────────────
LANGUAGES = ["python", "typescript", "go", "rust", "java", "sql", "yaml"]

# Capability tag → realistic line-change distribution & severity prior
TAG_PROFILE: dict[str, dict[str, Any]] = {
    "style":         {"lines": (1, 30),   "sev_weights": [0.05, 0.15, 0.80]},  # crit/warn/info
    "classify":      {"lines": (1, 10),   "sev_weights": [0.02, 0.10, 0.88]},
    "logic":         {"lines": (5, 120),  "sev_weights": [0.20, 0.45, 0.35]},
    "test-coverage": {"lines": (10, 80),  "sev_weights": [0.05, 0.55, 0.40]},
    "architecture":  {"lines": (40, 400), "sev_weights": [0.30, 0.50, 0.20]},
    "security":      {"lines": (5, 200),  "sev_weights": [0.55, 0.35, 0.10]},
}

CATEGORY_BY_TAG = {
    "style":         "style",
    "classify":      "style",
    "logic":         "logic",
    "test-coverage": "test-coverage",
    "architecture":  "logic",
    "security":      "security",
}

SEVERITIES = ["critical", "warning", "info"]


@dataclass
class Episode:
    language: str
    lines_changed: int
    classifier_tag: str
    chosen_model_id: str
    cost_sats: int
    severity: str
    category: str
    accepted: bool


# ───────────────────── routing simulator ───────────────────────────
def pick_model(tag: str, lines_changed: int, registry: list[Any]) -> Any:
    """
    Mimic the real router's "cheapest qualified model" rule, with size-based
    escalation: the more lines changed, the more likely we escalate to a
    pricier model that also covers the tag.
    """
    qualified = [m for m in registry if tag in m.capability_tags]
    if not qualified:
        qualified = list(registry)
    qualified.sort(key=lambda m: m.cost_sats)

    # escalation probability grows with chunk size (capped at 80%)
    escalate_p = min(0.8, lines_changed / 250.0)
    if random.random() < escalate_p and len(qualified) > 1:
        # weighted toward more capable (more expensive) models
        weights = [i + 1 for i in range(len(qualified))]
        return random.choices(qualified, weights=weights, k=1)[0]
    return qualified[0]


def synth_episode(registry: list[Any]) -> Episode:
    tag = random.choices(
        list(TAG_PROFILE.keys()),
        weights=[3, 4, 5, 3, 2, 3],  # rough real-world frequency
        k=1,
    )[0]
    profile = TAG_PROFILE[tag]
    lines = random.randint(*profile["lines"])
    language = random.choice(LANGUAGES)

    model = pick_model(tag, lines, registry)
    severity = random.choices(SEVERITIES, weights=profile["sev_weights"], k=1)[0]
    accepted = random.random() < {"critical": 0.85, "warning": 0.55, "info": 0.25}[severity]

    return Episode(
        language=language,
        lines_changed=lines,
        classifier_tag=tag,
        chosen_model_id=model.id,
        cost_sats=model.cost_sats,
        severity=severity,
        category=CATEGORY_BY_TAG[tag],
        accepted=accepted,
    )


# ───────────────────── training ────────────────────────────────────
def train_personalised_router(episodes: list[Episode], out_path: Path) -> None:
    """
    Train a small classifier that maps (language, tag, lines bucket) → model_id.
    Mirrors the shape of router/router.py so the artifact is drop-in compatible.
    """
    def featurize(ep: Episode) -> dict[str, Any]:
        return {
            "language": ep.language,
            "tag": ep.classifier_tag,
            "lines_bucket": _bucket(ep.lines_changed),
        }

    X = [featurize(e) for e in episodes]
    y = [e.chosen_model_id for e in episodes]

    pipe = Pipeline([
        ("vec", DictVectorizer(sparse=False)),
        ("clf", LogisticRegression(max_iter=1000, multi_class="auto")),
    ])
    pipe.fit(X, y)
    joblib.dump(pipe, out_path)
    log.info("Saved personalised router → %s", out_path)


def _bucket(lines: int) -> str:
    if lines < 10:   return "xs"
    if lines < 50:   return "s"
    if lines < 150:  return "m"
    if lines < 400:  return "l"
    return "xl"


# ───────────────────── entrypoint ──────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic router training data.")
    ap.add_argument("--episodes", type=int, default=600,
                    help="Number of synthetic review episodes to generate (default: 600).")
    ap.add_argument("--out", type=Path, default=Path("router/seed_data.jsonl"),
                    help="JSONL file to write the raw episodes to.")
    ap.add_argument("--model-out", type=Path, default=Path("router_model.joblib"),
                    help="Where to save the trained joblib router.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    registry = load_registry()
    log.info("Loaded %d models from registry", len(registry))

    episodes = [synth_episode(registry) for _ in range(args.episodes)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for ep in episodes:
            f.write(json.dumps(asdict(ep)) + "\n")
    log.info("Wrote %d episodes → %s", len(episodes), args.out)

    # Quick distribution sanity log
    by_model = Counter(e.chosen_model_id for e in episodes)
    by_tag = Counter(e.classifier_tag for e in episodes)
    log.info("Model distribution: %s", dict(by_model))
    log.info("Tag distribution:   %s", dict(by_tag))

    train_personalised_router(episodes, args.model_out)


if __name__ == "__main__":
    main()
