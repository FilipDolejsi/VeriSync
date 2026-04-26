"""
Multi-class contextual bandit router with per-user / per-repo personalisation.

Architecture
------------
* Feature vector per episode:
    [384-dim sentence embedding]
  + [5-dim one-hot classifier tag]
  + [10-dim one-hot language]
  + [1-dim log1p(lines_changed)]
  + [N-dim log1p(model costs)]   N = len(registry)
  + [16-dim user embedding]      (PCA of user's past diff embeddings, zeros for cold start)
  + [16-dim repo embedding]      (PCA of repo's past diff embeddings, zeros for cold start)

* Classifier: OneVsRestClassifier(LogisticRegression) — predicts tier_index
* All artefacts saved together via joblib: classifier, user/repo embedding dicts,
  feature_dim, trained_at, episode_count.

Fallback contract
-----------------
predict_model() NEVER raises.  If no model file exists, or confidence < threshold,
or the user/repo is new (< 5 episodes), it returns tier 0 gracefully.
"""

import logging
import os
import threading
import time
from collections import defaultdict
from typing import List, Optional

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sentence_transformers import SentenceTransformer

from models import ModelEntry

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

ROUTER_MODEL_PATH     = os.environ.get("ROUTER_MODEL_PATH",            "./router_model.joblib")
RETRAIN_EVERY         = int(os.environ.get("ROUTER_RETRAIN_EVERY",     "10"))
CONFIDENCE_THRESHOLD  = float(os.environ.get("ROUTER_CONFIDENCE_THRESHOLD", "0.5"))
RETRAIN_POLL_SECS     = 30
MIN_EPISODES_PERSONAL = 5   # cold-start threshold: episodes needed before personalising
USER_REPO_EMBED_DIM   = 16  # size of each user/repo embedding

VALID_TAGS = ["style", "logic", "security", "performance", "tests"]
LANGUAGES  = ["python", "javascript", "typescript", "java", "go",
              "rust", "cpp", "c", "ruby", "unknown"]

# ── Embedding model (singleton — loaded once at import, pre-warmed) ────────────

logger.info("Loading sentence-transformer embedding model …")
try:
    EMBEDDING_MODEL: Optional[SentenceTransformer] = SentenceTransformer("all-MiniLM-L6-v2")
    EMBEDDING_MODEL.encode("warmup", show_progress_bar=False)
    _EMBED_DIM = 384
    logger.info("Embedding model ready.")
except Exception as _embed_err:
    logger.warning(
        "Could not load sentence-transformer: %s. Router will use zero embeddings.",
        _embed_err,
    )
    EMBEDDING_MODEL = None
    _EMBED_DIM = 384

# ── Module-level state ─────────────────────────────────────────────────────────

_sats_saved_vs_naive: int = 0
_latest_accuracy:    dict = {}
_retrain_lock = threading.Lock()


# ── PCA-based user / repo embedding computation ────────────────────────────────

def _compute_user_repo_embeddings(
    episodes: list[dict],
    n_components: int = USER_REPO_EMBED_DIM,
    min_episodes: int = MIN_EPISODES_PERSONAL,
) -> tuple[dict, dict]:
    """
    Compute n_components-dim embeddings for every user and repo that has at
    least min_episodes episodes in the supplied list.

    Steps:
    1. Group diff texts by user_id and repo_full_name.
    2. For each entity with >= min_episodes texts, compute the mean sentence
       embedding (384-dim).
    3. Fit a shared PCA on all mean embeddings (user + repo) and project to
       n_components dimensions.  Falls back to slicing the first n_components
       raw dims when there are not enough data points for PCA.

    Returns (user_embeddings, repo_embeddings) — dicts mapping id → np.array(n_components,).
    """
    if EMBEDDING_MODEL is None:
        return {}, {}

    user_texts: dict[str, list[str]] = defaultdict(list)
    repo_texts: dict[str, list[str]] = defaultdict(list)

    for ep in episodes:
        text = (ep.get("diff_text") or "")[:500]   # cap per-episode for encoding speed
        uid  = ep.get("user_id") or ""
        repo = ep.get("repo_full_name") or ""
        if text and uid:
            user_texts[uid].append(text)
        if text and repo:
            repo_texts[repo].append(text)

    def _mean_embeddings(text_groups: dict) -> dict:
        result: dict[str, np.ndarray] = {}
        for key, texts in text_groups.items():
            if len(texts) >= min_episodes:
                vecs = EMBEDDING_MODEL.encode(
                    texts, convert_to_numpy=True, show_progress_bar=False
                )
                result[key] = vecs.mean(axis=0).astype(np.float32)
        return result

    user_means = _mean_embeddings(user_texts)
    repo_means = _mean_embeddings(repo_texts)

    all_means = list(user_means.values()) + list(repo_means.values())
    if not all_means:
        return {}, {}

    pca: Optional[PCA] = None
    if len(all_means) >= n_components + 1:
        pca = PCA(n_components=n_components)
        pca.fit(np.array(all_means, dtype=np.float32))

    def _reduce(mean_dict: dict) -> dict:
        out: dict[str, np.ndarray] = {}
        for key, emb in mean_dict.items():
            if pca is not None:
                vec = pca.transform(emb.reshape(1, -1))[0].astype(np.float32)
            else:
                vec = emb[:n_components].astype(np.float32)
            # Guarantee exactly n_components dims
            if len(vec) < n_components:
                vec = np.pad(vec, (0, n_components - len(vec))).astype(np.float32)
            out[key] = vec[:n_components]
        return out

    return _reduce(user_means), _reduce(repo_means)


# ── Feature engineering ────────────────────────────────────────────────────────

def _build_features(
    text:           str,
    tag:            str,
    registry:       List[ModelEntry],
    language:       str = "unknown",
    lines_changed:  int = 0,
    file_path:      str = "",
    user_embedding: Optional[np.ndarray] = None,
    repo_embedding: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Build the full feature vector for one diff chunk:

        [384 text embedding]
      + [5  one-hot tag]
      + [10 one-hot language]
      + [1  log1p(lines_changed)]
      + [N  log1p(model costs)]
      + [16 user embedding]   (zeros for cold-start / unknown user)
      + [16 repo embedding]   (zeros for cold-start / unknown repo)
    """
    # 1. Dense text embedding
    if EMBEDDING_MODEL is not None:
        emb = EMBEDDING_MODEL.encode(
            text or "", convert_to_numpy=True, show_progress_bar=False
        ).astype(np.float32)
    else:
        emb = np.zeros(_EMBED_DIM, dtype=np.float32)

    # 2. One-hot classifier tag
    tag_vec = np.zeros(len(VALID_TAGS), dtype=np.float32)
    if tag in VALID_TAGS:
        tag_vec[VALID_TAGS.index(tag)] = 1.0

    # 3. One-hot language
    lang = (language or "unknown").lower()
    lang_vec = np.zeros(len(LANGUAGES), dtype=np.float32)
    lang_vec[LANGUAGES.index(lang if lang in LANGUAGES else "unknown")] = 1.0

    # 4. Log-scaled lines changed
    lines_feat = np.array([np.log1p(max(0, lines_changed))], dtype=np.float32)

    # 5. Log-scaled model costs (cheapest → most expensive)
    costs = np.log1p([m.cost_sats for m in registry]).astype(np.float32)

    # 6–7. User / repo embeddings (zeros if none supplied)
    u_emb = (user_embedding if user_embedding is not None
             else np.zeros(USER_REPO_EMBED_DIM, dtype=np.float32))
    r_emb = (repo_embedding if repo_embedding is not None
             else np.zeros(USER_REPO_EMBED_DIM, dtype=np.float32))

    return np.concatenate([emb, tag_vec, lang_vec, lines_feat, costs, u_emb, r_emb])


# ── Model persistence ──────────────────────────────────────────────────────────

def _load_model() -> Optional[dict]:
    """
    Load the persisted router artefact dict from ROUTER_MODEL_PATH.
    Returns None if the file does not exist or cannot be read.
    Expected keys: classifier, user_embeddings, repo_embeddings,
                   feature_dim, trained_at, episode_count.
    """
    if not os.path.exists(ROUTER_MODEL_PATH):
        return None
    try:
        return joblib.load(ROUTER_MODEL_PATH)
    except Exception as e:
        logger.warning("Could not load router model from %s: %s", ROUTER_MODEL_PATH, e)
        return None


# ── Training ──────────────────────────────────────────────────────────────────

def train_router(registry: List[ModelEntry]) -> dict:
    """
    Fetch all successful episodes from SQLite, build the personalised feature
    matrix, fit OneVsRestClassifier(LogisticRegression), persist artefacts.

    Returns a dict with keys:
        accuracy   — {tier_index: float} per-class accuracy
        users      — number of users with personalised embeddings
        repos      — number of repos with personalised embeddings
    Returns {} on failure or insufficient data.
    """
    global _latest_accuracy

    from db.store import get_all_episodes_sync

    try:
        episodes = get_all_episodes_sync()
        if len(episodes) < 2:
            logger.info("train_router: not enough episodes (%d) — skipping", len(episodes))
            return {}

        # Compute user / repo embeddings from history
        user_embs, repo_embs = _compute_user_repo_embeddings(episodes)
        n_users = len(user_embs)
        n_repos = len(repo_embs)
        logger.info(
            "train_router: personalised embeddings for %d users, %d repos",
            n_users, n_repos,
        )

        _zero_u = np.zeros(USER_REPO_EMBED_DIM, dtype=np.float32)
        _zero_r = np.zeros(USER_REPO_EMBED_DIM, dtype=np.float32)

        X, y = [], []
        for ep in episodes:
            text  = ep.get("diff_text") or ""
            tag   = ep.get("classifier_tag") or "logic"
            tier  = ep.get("tier_index", 0)
            lang  = ep.get("language") or "unknown"
            lines = ep.get("lines_changed") or 0
            fpath = ep.get("file_path") or ""
            u_emb = user_embs.get(ep.get("user_id", ""), _zero_u)
            r_emb = repo_embs.get(ep.get("repo_full_name", ""), _zero_r)
            X.append(_build_features(text, tag, registry, lang, lines, fpath, u_emb, r_emb))
            y.append(int(tier))

        X_arr = np.array(X, dtype=np.float32)
        y_arr = np.array(y, dtype=int)

        if len(set(y_arr)) < 2:
            logger.info("train_router: only one class in data — skipping")
            return {}

        clf = OneVsRestClassifier(LogisticRegression(max_iter=500, C=1.0))
        clf.fit(X_arr, y_arr)

        accuracy: dict = {}
        for cls in sorted(set(y_arr)):
            mask  = y_arr == cls
            preds = clf.predict(X_arr[mask])
            accuracy[int(cls)] = float((preds == cls).mean())

        model_data = {
            "classifier":      clf,
            "user_embeddings": user_embs,
            "repo_embeddings": repo_embs,
            "feature_dim":     X_arr.shape[1],
            "trained_at":      __import__("datetime").datetime.now().isoformat(),
            "episode_count":   len(episodes),
            "n_users_personalised": n_users,
            "n_repos_tracked":      n_repos,
        }
        joblib.dump(model_data, ROUTER_MODEL_PATH)

        _latest_accuracy = accuracy
        logger.info(
            "Router retrained on %d episodes. Accuracy: %s  users=%d repos=%d",
            len(X), accuracy, n_users, n_repos,
        )
        return {"accuracy": accuracy, "users": n_users, "repos": n_repos}

    except Exception as e:
        logger.error("train_router failed: %s", e)
        return {}


# ── Prediction ─────────────────────────────────────────────────────────────────

def predict_model(
    task:           str,
    classifier_tag: str,
    registry:       List[ModelEntry],
    user_id:        str = "",
    repo_full_name: str = "",
    language:       str = "unknown",
    lines_changed:  int = 0,
    file_path:      str = "",
) -> dict:
    """
    Predict the cheapest tier likely to pass verification for this diff chunk.

    user_id and repo_full_name are used to look up personalised embeddings; unknown
    users/repos fall back to zero vectors (cold-start, neutral prediction).

    Returns {model_id, tier_index, confidence, used_router}.
    Never raises — falls back to tier 0 on any error.
    Also increments _sats_saved_vs_naive (naive = always use most expensive tier).
    """
    global _sats_saved_vs_naive

    naive_cost = registry[-1].cost_sats if registry else 0
    fallback = {
        "model_id":    registry[0].id if registry else "default",
        "tier_index":  0,
        "confidence":  0.0,
        "used_router": False,
    }

    if not registry:
        return fallback

    model_data = _load_model()
    if model_data is None:
        _sats_saved_vs_naive += max(0, naive_cost - registry[0].cost_sats)
        return fallback

    try:
        _zero = np.zeros(USER_REPO_EMBED_DIM, dtype=np.float32)
        u_emb = model_data["user_embeddings"].get(user_id, _zero)
        r_emb = model_data["repo_embeddings"].get(repo_full_name, _zero)

        features = _build_features(
            task, classifier_tag, registry, language, lines_changed, file_path,
            u_emb, r_emb,
        ).reshape(1, -1)

        clf            = model_data["classifier"]
        probas         = clf.predict_proba(features)[0]
        classes        = clf.classes_
        best_idx       = int(np.argmax(probas))
        confidence     = float(probas[best_idx])
        predicted_tier = int(classes[best_idx])

        if confidence < CONFIDENCE_THRESHOLD or predicted_tier >= len(registry):
            _sats_saved_vs_naive += max(0, naive_cost - registry[0].cost_sats)
            return {**fallback, "confidence": confidence}

        chosen = registry[predicted_tier]
        _sats_saved_vs_naive += max(0, naive_cost - chosen.cost_sats)

        return {
            "model_id":    chosen.id,
            "tier_index":  predicted_tier,
            "confidence":  confidence,
            "used_router": True,
        }

    except Exception as e:
        logger.error("predict_model failed: %s", e)
        _sats_saved_vs_naive += max(0, naive_cost - registry[0].cost_sats)
        return fallback


# ── Background retrain thread ──────────────────────────────────────────────────

def start_retrain_loop(registry: List[ModelEntry], event_loop=None) -> None:
    """
    Spawn a daemon thread that polls episode count every RETRAIN_POLL_SECS.
    Retrains when RETRAIN_EVERY new episodes have arrived, then broadcasts
    the result (accuracy + personalisation stats) to all open SSE connections
    if event_loop is provided.
    """

    def _loop() -> None:
        import asyncio
        from db.store import get_episode_count_sync

        last_count = get_episode_count_sync()
        logger.info("Retrain loop started. Episode count at launch: %d", last_count)

        while True:
            time.sleep(RETRAIN_POLL_SECS)
            try:
                current = get_episode_count_sync()
                new_eps = current - last_count

                if new_eps >= RETRAIN_EVERY:
                    logger.info("Retraining router (%d new episodes) …", new_eps)
                    with _retrain_lock:
                        result = train_router(registry)
                    last_count = current

                    if event_loop and result:
                        acc = result.get("accuracy", {})
                        payload = {
                            "type":                "router_retrained",
                            "per_class_accuracy":  acc,
                            "sats_saved_vs_naive": _sats_saved_vs_naive,
                            "episode_count":       current,
                            "users_personalised":  result.get("users", 0),
                            "repos_tracked":       result.get("repos", 0),
                        }
                        try:
                            from dashboard.events import broker
                            for uid in list(broker._subs.keys()):
                                asyncio.run_coroutine_threadsafe(
                                    broker.publish(uid, "router_retrained", payload), event_loop
                                )
                        except Exception as pub_err:
                            logger.warning("SSE broadcast failed: %s", pub_err)

            except Exception as e:
                logger.error("Retrain loop error: %s", e)

    t = threading.Thread(target=_loop, daemon=True, name="router-retrain")
    t.start()
    logger.info("Router retrain background thread started.")


# ── Public stats ───────────────────────────────────────────────────────────────

def get_router_stats() -> dict:
    """Snapshot of router performance for the dashboard and /api/analytics."""
    model_data = _load_model()
    n_users = model_data.get("n_users_personalised", 0) if model_data else 0
    n_repos = model_data.get("n_repos_tracked",      0) if model_data else 0
    return {
        "sats_saved_vs_naive":      _sats_saved_vs_naive,
        "latest_accuracy":          _latest_accuracy,
        "model_exists":             os.path.exists(ROUTER_MODEL_PATH),
        "total_users_personalised": n_users,
        "total_repos_tracked":      n_repos,
    }


# ── Router class — thin wrapper kept for graph.py / nodes.py compatibility ─────

class Router:
    """
    Stateless wrapper around the module-level predict_model() function.
    graph.py instantiates Router() per chunk; the real model lives at module scope.
    """

    def predict_model(
        self,
        diff_text:     str,
        tag:           str,
        registry,
        user_id:       str = "",
        repo_full_name: str = "",
        language:      str = "unknown",
        lines_changed: int = 0,
        file_path:     str = "",
    ) -> dict:
        """
        Accepts both a Registry wrapper (with .models_list) and a plain
        List[ModelEntry].  Delegates to the module-level predict_model().
        """
        if hasattr(registry, "models_list"):
            models = registry.models_list
        elif isinstance(registry, list):
            models = registry
        else:
            models = []

        return predict_model(
            diff_text, tag, models,
            user_id=user_id,
            repo_full_name=repo_full_name,
            language=language,
            lines_changed=lines_changed,
            file_path=file_path,
        )
