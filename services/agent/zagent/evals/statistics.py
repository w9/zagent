import math
from collections.abc import Mapping
from statistics import NormalDist


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials < 0 or not 0 <= successes <= trials:
        raise ValueError("Successes must be between zero and the number of trials")
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be between zero and one")
    if trials == 0:
        return 0.0, 1.0
    quantile = NormalDist().inv_cdf(0.5 + confidence / 2)
    proportion = successes / trials
    denominator = 1 + quantile**2 / trials
    center = (proportion + quantile**2 / (2 * trials)) / denominator
    radius = (
        quantile
        * math.sqrt(proportion * (1 - proportion) / trials + quantile**2 / (4 * trials**2))
        / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def pass_power(successes: int, trials: int, streak: int) -> float | None:
    if trials < 0 or not 0 <= successes <= trials or streak < 1:
        raise ValueError("Invalid trial counts or pass^k streak")
    if trials < streak:
        return None
    if successes < streak:
        return 0.0
    return math.prod((successes - offset) / (trials - offset) for offset in range(streak))


def paired_comparison(
    current: Mapping[tuple, bool], baseline: Mapping[tuple, bool]
) -> dict[str, int | float | None]:
    matched = current.keys() & baseline.keys()
    improved = sum(current[key] and not baseline[key] for key in matched)
    regressed = sum(not current[key] and baseline[key] for key in matched)
    discordant = improved + regressed
    probability = 1.0
    if discordant:
        lower = min(improved, regressed)
        probability = min(
            1.0, 2 * sum(math.comb(discordant, count) for count in range(lower + 1)) / 2**discordant
        )
    return {
        "matched": len(matched),
        "improved": improved,
        "regressed": regressed,
        "unchanged": len(matched) - discordant,
        "unmatched_current": len(current.keys() - baseline.keys()),
        "unmatched_baseline": len(baseline.keys() - current.keys()),
        "difference": (improved - regressed) / len(matched) if matched else None,
        "exact_p_value": probability if matched else None,
    }
