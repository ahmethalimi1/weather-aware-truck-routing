"""Route ranking by priority order."""
from .analysis import RouteAnalysis
from .risk import Level


AVG_RISK_PRECISION = 1


def sort_key(route: RouteAnalysis) -> tuple:
    # Lower is better, compared in order. Miles and average risk are rounded to one decimal.
    return (
        round(route.miles_by_level[Level.NO_TRAVEL], 1),
        round(route.miles_by_level[Level.SEVERE], 1),
        round(route.miles_by_level[Level.HIGH], 1),
        round(route.unknown_miles, 1),
        round(route.avg_risk, AVG_RISK_PRECISION),
        route.duration_seconds,
    )


def rank_routes(routes: list[RouteAnalysis]) -> list[RouteAnalysis]:
    return sorted(routes, key=sort_key)


def explain(best: RouteAnalysis, ranked: list[RouteAnalysis]) -> list[str]:
    """Human-readable reasons for the recommendation, in priority order."""
    others = [r for r in ranked if r.route_id != best.route_id]
    if not others:
        return ["There is no alternative route to compare against."]

    best_key = sort_key(best)
    criteria = (
        ("No Travel miles", 0, "mi"),
        ("Severe miles", 1, "mi"),
        ("High miles", 2, "mi"),
        ("miles without a forecast", 3, "mi"),
        ("average risk", 4, ""),
    )
    # Find the first criterion where the best route beats the runner-up.
    runner_up = others[0]
    runner_key = sort_key(runner_up)
    reasons = []
    for label, i, unit in criteria:
        if best_key[i] < runner_key[i]:
            if unit:
                reasons.append(
                    f"{best.name} has {best_key[i]:g} {label} versus {runner_key[i]:g} on {runner_up.name}."
                )
            else:
                reasons.append(
                    f"{best.name} has lower average risk ({best_key[i]:.1f} vs {runner_key[i]:.1f} on {runner_up.name})."
                )
            break
    else:
        diff_min = (runner_up.duration_seconds - best.duration_seconds) / 60
        if diff_min > 0.5:
            reasons.append(
                f"Weather risk is comparable across routes; {best.name} is the fastest ({diff_min:.0f} min quicker than {runner_up.name})."
            )
        else:
            reasons.append(f"Routes are equivalent in weather risk and travel time; {best.name} listed first.")

    fastest = min(ranked, key=lambda r: r.duration_seconds)
    if fastest.route_id != best.route_id:
        extra = (best.duration_seconds - fastest.duration_seconds) / 60
        reasons.append(f"Trade-off: it is {extra:.0f} min slower than the fastest route ({fastest.name}).")
    if best.miles_by_level[Level.NO_TRAVEL] > 0:
        reasons.append("Warning: every route contains No Travel conditions for this load; consider delaying departure.")
    return reasons
