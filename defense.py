from statistics import mean, pstdev


class CostDetector:
    """Content-agnostic detector: learn normal cost from benign runs, flag any
    run that spends far more than that. Works regardless of how the extra cost
    was induced, since it watches behavior, not the text of the data."""

    def __init__(self, k=3.0, metric="total_tokens"):
        self.k = k
        self.metric = metric
        self.threshold = None

    def calibrate(self, benign_runs):
        vals = [r[self.metric] for r in benign_runs]
        m = mean(vals)
        s = pstdev(vals) if len(vals) > 1 else 0.0
        self.threshold = m + max(self.k * s, 0.25 * m)

    def flag(self, run):
        return self.threshold is not None and run[self.metric] > self.threshold
