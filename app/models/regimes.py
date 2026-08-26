from __future__ import annotations

import numpy as np


class HMMRegimeFilter:
    """GaussianHMM regime filter: fit trên returns, predict P(state|obs).

    n_init > 1 chống local optima; chọn best log-likelihood.
    """

    def __init__(self, n_states: int = 3, n_init: int = 10):
        self.n_states = n_states
        self.n_init = n_init
        self.model = None

    def fit_predict_probs(self, closes: list[float]) -> np.ndarray:
        from hmmlearn.hmm import GaussianHMM

        if len(closes) < 40:
            raise ValueError("not enough data for HMM")
        returns = np.diff(np.log(np.asarray(closes, dtype=float))).reshape(-1, 1)
        if len(returns) < 20:
            raise ValueError("not enough returns for HMM")

        best = None
        best_ll = -np.inf
        for _ in range(self.n_init):
            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="diag",
                n_iter=100,
                random_state=42,
            )
            model.fit(returns)
            ll = model.score(returns)
            if ll > best_ll:
                best_ll = ll
                best = model
        self.model = best
        # probs mỗi observation (trả n-1 vì returns) — pad đầu bằng state đầu
        probs = best.predict_proba(returns)
        # thêm 1 row đầu (state trước return đầu tiên = probs đầu)
        probs = np.vstack([probs[:1], probs])
        return probs
