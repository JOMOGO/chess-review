"""Training recommendations: rank a player's weaknesses and propose actions.

The goal is *prescriptive* analytics. Other modules surface raw numbers (CPL
per phase, win-rate per opening, etc.); this one synthesises them into a short
ranked list of "things to work on" with concrete training links.

Heuristic, not ML — every recommendation is auditable: each item carries the
raw numbers that produced it.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import chess
from sqlalchemy import Integer, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.analytics.accuracy import compute_game_accuracy
from chess_review.analytics.endgames import get_endgame_summary
from chess_review.analytics.openings_winrate import get_opening_stats
from chess_review.analytics.phase_split import get_phase_performance
from chess_review.analytics.rating_performance import get_rating_performance
from chess_review.analytics.time_pressure import get_time_pressure
from chess_review.models import Game, GameMove, MoveTactic, Position

logger = logging.getLogger(__name__)

# --- Tunables ---------------------------------------------------------------
# All thresholds are relative to the player's own baseline (so a 2000 player
# isn't told "you blunder a lot" because their CPL is higher than a GM's).

MIN_GAMES_FOR_OPENING_LEAK = 5
OPENING_LEAK_CPL_RATIO = 1.4   # leak if cpl_opening >= 1.4 * baseline_cpl
OPENING_LEAK_WIN_FLOOR = 0.40  # OR win_rate < 40%

PHASE_WEAK_CPL_RATIO = 1.25
TIME_CLIFF_CPL_RATIO = 1.5     # worst bucket CPL >= 1.5 * best bucket
RATING_WIN_FLOOR = 0.30        # win_rate < 30% in a bucket is "they own you"
COLOR_GAP_PCT = 15             # win rate gap >= 15% between colors

# Missed wins / conversion
MISSED_WINS_EVAL_CP = 300      # eval >= +300 cp from user POV counts as "winning"
MISSED_WINS_FLOOR = 0.60       # conversion < 60% triggers
MISSED_WINS_MIN_GAMES = 5

# Anti-repertoire: lines you face with only 3-4 games but bad results
ANTI_REP_MIN_GAMES = 3
ANTI_REP_CPL_RATIO = 1.3
ANTI_REP_WIN_FLOOR = 0.40

# Hung-piece blunder detection
BLUNDER_PATTERN_MIN_BLUNDERS = 20
BLUNDER_PATTERN_HUNG_FLOOR = 0.40

# Time-of-day cliff
TIME_OF_DAY_BUCKET_HOURS = 3
TIME_OF_DAY_MIN_GAMES_IN_BUCKET = 10
TIME_OF_DAY_CPL_RATIO = 1.3

# Tilt detection (post-loss vs post-win accuracy)
TILT_MIN_SAMPLES_EACH = 10     # min comparisons in each side (post-loss / post-win)
TILT_ACCURACY_GAP = 5.0        # post-loss accuracy >= 5 points lower than post-win
SESSION_GAP_SECONDS = 60 * 60  # 60 minutes between games = new session

# Tactic blindspot — flag a motif if you miss it noticeably more often than its
# share of tactical opportunities in chess generally (rough Lichess-puzzle-
# derived priors). Lift ≥ 1.5 means "1.5× your fair share of misses on this
# motif" — clear signal. ≥ 10 misses required so a single bad game doesn't
# crown smothered mate as your nemesis.
BLINDSPOT_LIFT_RATIO = 1.5
BLINDSPOT_MIN_MISSES = 10
# Raw shares are rough; normalised at module load so they sum to 1 over the
# motifs the detector recognises. If a new motif kind is added to the
# detector, give it a baseline share here too — otherwise it'll appear as
# 100% "over-representation" the first time you miss one.
_MOTIF_BASELINE_RAW = {
    "fork": 0.25,
    "pin": 0.15,
    "removal_of_defender": 0.06,
    "trapped_piece": 0.06,
    "skewer": 0.05,
    "discovered_attack": 0.04,
    "deflection": 0.04,
    "back_rank_mate": 0.03,
    "pawn_promotion": 0.02,
    "smothered_mate": 0.005,
}
_MOTIF_BASELINE = {
    k: v / sum(_MOTIF_BASELINE_RAW.values())
    for k, v in _MOTIF_BASELINE_RAW.items()
}
_MOTIF_HUMAN_LABEL = {
    "fork": "forks",
    "pin": "pins",
    "skewer": "skewers",
    "discovered_attack": "discovered attacks",
    "removal_of_defender": "defender-removal tactics",
    "back_rank_mate": "back-rank mates",
    "smothered_mate": "smothered mates",
    "trapped_piece": "trapped-piece tactics",
    "deflection": "deflections",
    "pawn_promotion": "promotion tactics",
}
# Lichess puzzle theme slugs (camelCase as Lichess serves them). Motifs
# without a clean Lichess theme fall back to the mixed trainer via
# _lichess_puzzle_url.
_MOTIF_PUZZLE_THEME = {
    "fork": "fork",
    "pin": "pin",
    "skewer": "skewer",
    "discovered_attack": "discoveredAttack",
    "removal_of_defender": "attraction",
    "back_rank_mate": "backRankMate",
    "smothered_mate": "smotheredMate",
    "deflection": "deflection",
    "pawn_promotion": "promotion",
}

# Endgame-type weakness — bucket-level conversion. Threshold deliberately
# loose because the existing whole-game missed_wins covers the broad case;
# this one catches buckets that are *specifically* weak.
ENDGAME_PATTERN_MIN_REACHED = 3
ENDGAME_PATTERN_CONVERSION_FLOOR = 0.6

# Phase vs peer — flag a phase where your CPL is meaningfully worse than
# the average opponent's CPL in the same phase. Complement to
# phase_weakness (which is YOUR phase vs YOUR baseline) — catches cases
# where your phase looks fine on paper but lags the people you actually play.
PHASE_VS_PEER_DELTA_CP = 5.0
PHASE_VS_PEER_MIN_OPP_MOVES = 50

# Top-N returned to the page
TOP_N = 12


# --- Helpers ----------------------------------------------------------------

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _score(severity: float, volume: float) -> float:
    """Blend severity and volume into a single 0-1 priority score.

    Severity matters more than volume — a single blunder pattern that costs
    games is worth more than a tiny edge spread across many positions — but
    rare leaks are deprioritised.
    """
    return round(0.65 * severity + 0.35 * volume, 4)


async def _player_baseline(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> dict:
    """Player-wide baseline: total games, accuracy, CPL, blunder rate."""
    game_filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        game_filters.append(Game.played_at >= since)

    games = (await session.execute(
        select(Game.id).where(and_(*game_filters))
    )).scalars().all()
    if not games:
        return {
            "games": 0, "accuracy": 0.0, "avg_cpl": 0.0,
            "blunder_rate": 0.0, "user_moves": 0,
        }

    move_rows = (await session.execute(
        select(GameMove)
        .where(GameMove.game_id.in_(games))
        .order_by(GameMove.game_id, GameMove.ply)
    )).scalars().all()

    by_game: dict[uuid.UUID, list[GameMove]] = {}
    for m in move_rows:
        by_game.setdefault(m.game_id, []).append(m)

    accs: list[float] = []
    cpls: list[int] = []
    blunders = 0
    user_moves = 0
    for gid, moves in by_game.items():
        acc, _, n = compute_game_accuracy(moves)
        if n == 0:
            continue
        accs.append(acc)
        for m in moves:
            if not m.is_user_move or m.cp_loss is None:
                continue
            user_moves += 1
            cpls.append(min(m.cp_loss, 1000))
            if m.classification in ("blunder", "miss"):
                blunders += 1

    return {
        "games": len(accs),
        "accuracy": round(sum(accs) / len(accs), 1) if accs else 0.0,
        "avg_cpl": round(sum(cpls) / len(cpls), 1) if cpls else 0.0,
        "blunder_rate": round(blunders / user_moves, 4) if user_moves else 0.0,
        "user_moves": user_moves,
    }


async def _color_split(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> dict[str, dict]:
    """Win rate + clamped avg CPL split by user_color."""
    clamped_cpl = case(
        (GameMove.cp_loss > 1000, 1000),
        else_=GameMove.cp_loss,
    )
    filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        filters.append(Game.played_at >= since)

    rows = (await session.execute(
        select(
            Game.user_color,
            func.count().label("n"),
            func.sum(case((Game.user_result == "win", 1), else_=0)).label("w"),
            func.sum(case((Game.user_result == "draw", 1), else_=0)).label("d"),
        )
        .where(and_(*filters))
        .group_by(Game.user_color)
    )).all()

    out: dict[str, dict] = {}
    for r in rows:
        out[r.user_color] = {
            "games": r.n or 0,
            "wins": r.w or 0,
            "draws": r.d or 0,
            "win_rate": round((r.w or 0) / r.n, 3) if r.n else 0.0,
            "score_rate": round(((r.w or 0) + 0.5 * (r.d or 0)) / r.n, 3) if r.n else 0.0,
        }

    cpl_rows = (await session.execute(
        select(Game.user_color, func.avg(clamped_cpl))
        .join(GameMove, GameMove.game_id == Game.id)
        .where(and_(
            *filters,
            GameMove.is_user_move.is_(True),
            GameMove.cp_loss.isnot(None),
        ))
        .group_by(Game.user_color)
    )).all()
    for color, cpl in cpl_rows:
        if color in out:
            out[color]["avg_cpl"] = round(float(cpl or 0), 1)
    return out


# --- Action-link builders ---------------------------------------------------
# We don't host trainers; we deep-link to existing app pages and to Lichess
# study/puzzle URLs that the player can use immediately.

# Lichess puzzle theme slugs that Lichess actually serves. "tactics" is NOT
# one of them — Lichess routes /training (no slug) to a mixed tactics trainer.
# Motif themes here mirror keys in _MOTIF_PUZZLE_THEME (kept in sync by
# convention; if a motif maps to a slug not in this set the URL builder
# falls back to /training, which is a graceful degradation).
_LICHESS_PUZZLE_THEMES = {
    "opening", "middlegame", "endgame", "hangingPiece",
    "fork", "pin", "skewer", "discoveredAttack", "attraction",
    "backRankMate", "smotheredMate", "deflection", "promotion",
}


def _lichess_puzzle_url(theme: str) -> str:
    """Map an internal theme name to a Lichess training URL.

    Unknown / synthetic themes (e.g. "tactics") fall back to the mixed
    trainer at ``/training``, which is the default tactics puzzle queue.
    """
    if theme in _LICHESS_PUZZLE_THEMES:
        return f"https://lichess.org/training/{quote(theme)}"
    return "https://lichess.org/training"


_PLACEHOLDER_OPENING_NAMES = {"undefined", "unknown", "?"}


def _opening_browser_url(eco: str | None, name: str | None) -> str:
    """Build a Lichess Opening Browser URL.

    Lichess accepts ``/opening/<Name_With_Underscores>`` (no trailing move).
    If only an ECO code is known, the landing page (``/opening``) is the safe
    fallback — it has search, and a bogus name would 404. chess.com sometimes
    writes ``Undefined`` as a placeholder opening name; treat those as missing.
    """
    if name and name.strip().lower() not in _PLACEHOLDER_OPENING_NAMES:
        slug = quote(name.replace(" ", "_"), safe="_")
        return f"https://lichess.org/opening/{slug}"
    if eco:
        return f"https://lichess.org/opening?eco={quote(eco)}"
    return "https://lichess.org/opening"


# Lichess Puzzle Storm is the timed puzzle mode (analogous to chess.com Puzzle Rush).
_PUZZLE_STORM_URL = "https://lichess.org/storm"

# Studies tagged "Opening" — Lichess study topic pages require a /hot or
# /mine suffix; the bare /study/topic/Opening 404s.
_OPENING_STUDIES_URL = "https://lichess.org/study/topic/Opening/hot"


# --- Detectors --------------------------------------------------------------

async def _detect_opening_leaks(
    session: AsyncSession,
    player_id: uuid.UUID,
    baseline: dict,
    total_games: int,
    since: datetime | None,
) -> list[dict]:
    """Openings with high CPL or low win rate vs the player's baseline."""
    if total_games == 0 or baseline["avg_cpl"] == 0:
        return []

    stats = await get_opening_stats(
        session, player_id,
        min_games=MIN_GAMES_FOR_OPENING_LEAK,
        since=since,
    )

    out: list[dict] = []
    base_cpl = max(baseline["avg_cpl"], 5.0)  # avoid divide-by-zero blowups
    for o in stats:
        if not o["opening_name"]:
            continue
        cpl_ratio = o["avg_cpl"] / base_cpl
        is_leak = (
            cpl_ratio >= OPENING_LEAK_CPL_RATIO
            or o["win_rate"] < OPENING_LEAK_WIN_FLOOR
        )
        if not is_leak:
            continue

        severity_cpl = _clamp01((cpl_ratio - 1.0) / 1.5)
        severity_wr = _clamp01((0.5 - o["win_rate"]) / 0.5)
        severity = max(severity_cpl, severity_wr)
        volume = _clamp01(o["games"] / max(total_games, 1) * 3)
        score = _score(severity, volume)

        out.append({
            "id": f"opening:{o['opening_name']}:{o['color']}",
            "kind": "opening_leak",
            "title": f"Leak in {o['opening_name']} as {o['color']}",
            "summary": (
                f"CPL {o['avg_cpl']:.1f} is {cpl_ratio:.1f}× your baseline "
                f"({base_cpl:.1f}). Win rate {int(o['win_rate']*100)}% "
                f"across {o['games']} games."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "opening_name": o["opening_name"],
                "eco": o["eco"],
                "color": o["color"],
                "games": o["games"],
                "wins": o["wins"], "draws": o["draws"], "losses": o["losses"],
                "win_rate": o["win_rate"],
                "avg_cpl": o["avg_cpl"],
                "baseline_cpl": base_cpl,
            },
            "actions": [
                {
                    "kind": "review_games",
                    "label": f"Review your {o['games']} games in this opening",
                    "href": f"/players/{player_id}/opening-stats",
                },
                {
                    "kind": "study_line",
                    "label": "Open on Lichess Opening Browser",
                    "href": _opening_browser_url(o["eco"], o["opening_name"]),
                    "external": True,
                },
            ],
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_phase_weakness(
    session: AsyncSession,
    player_id: uuid.UUID,
    baseline: dict,
    since: datetime | None,
) -> list[dict]:
    if baseline["avg_cpl"] == 0:
        return []
    phases = await get_phase_performance(session, player_id, since)
    out: list[dict] = []
    base_cpl = max(baseline["avg_cpl"], 5.0)

    for p in phases:
        ratio = p["avg_cpl"] / base_cpl
        if ratio < PHASE_WEAK_CPL_RATIO:
            continue
        severity = _clamp01((ratio - 1.0) / 1.5)
        volume = _clamp01(p["sample_size"] / max(baseline["user_moves"], 1) * 2)
        score = _score(severity, volume)

        theme = {"opening": "opening", "middlegame": "middlegame", "endgame": "endgame"}[p["phase"]]
        out.append({
            "id": f"phase:{p['phase']}",
            "kind": "phase_weakness",
            "title": f"{p['phase'].capitalize()} is your weak phase",
            "summary": (
                f"CPL in {p['phase']} is {p['avg_cpl']:.1f} ({ratio:.1f}× baseline). "
                f"Blunder rate {p['blunder_rate']*100:.1f}% across {p['sample_size']} moves."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "phase": p["phase"],
                "sample_size": p["sample_size"],
                "avg_cpl": p["avg_cpl"],
                "blunder_rate": p["blunder_rate"],
                "mistake_rate": p["mistake_rate"],
                "inaccuracy_rate": p["inaccuracy_rate"],
                "baseline_cpl": base_cpl,
            },
            "actions": [
                {
                    "kind": "puzzle_theme",
                    "label": f"Solve Lichess '{theme}' puzzles",
                    "href": _lichess_puzzle_url(theme),
                    "external": True,
                },
                {
                    "kind": "view_phase",
                    "label": "Open Phase dashboard",
                    "href": f"/players/{player_id}/phases",
                },
            ],
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_time_pressure(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    out: list[dict] = []
    for tc in ("blitz", "rapid", "bullet", "classical"):
        buckets = await get_time_pressure(session, player_id, tc, since=since)
        if len(buckets) < 2:
            continue
        # ">120s" is the calm baseline; missing if all games short, then use
        # the first bucket as best.
        best = min(buckets, key=lambda b: b["avg_cpl"])
        worst = max(buckets, key=lambda b: b["avg_cpl"])
        if best["bucket"] == worst["bucket"] or best["avg_cpl"] <= 0:
            continue
        ratio = worst["avg_cpl"] / max(best["avg_cpl"], 1.0)
        if ratio < TIME_CLIFF_CPL_RATIO:
            continue

        total_moves = sum(b["sample_size"] for b in buckets)
        volume = _clamp01(worst["sample_size"] / max(total_moves, 1))
        severity = _clamp01((ratio - 1.0) / 2.0)
        score = _score(severity, volume)

        out.append({
            "id": f"time:{tc}:{worst['bucket']}",
            "kind": "time_pressure",
            "title": f"You collapse under {worst['bucket']} in {tc}",
            "summary": (
                f"CPL jumps to {worst['avg_cpl']:.0f} (vs {best['avg_cpl']:.0f} when "
                f"calm, {ratio:.1f}× worse). Blunder rate "
                f"{worst['blunder_rate']*100:.1f}%."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "time_class": tc,
                "worst_bucket": worst,
                "best_bucket": best,
                "ratio": round(ratio, 2),
            },
            "actions": [
                {
                    "kind": "play_slower",
                    "label": "Try a slower time control (rapid)",
                },
                {
                    "kind": "puzzle_theme",
                    "label": "Practise Puzzle Storm (timed)",
                    "href": _PUZZLE_STORM_URL,
                    "external": True,
                },
                {
                    "kind": "view_time",
                    "label": "Open Time Pressure page",
                    "href": f"/players/{player_id}/time",
                },
            ],
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_rating_walls(
    session: AsyncSession,
    player_id: uuid.UUID,
    baseline: dict,
    since: datetime | None,
) -> list[dict]:
    buckets = await get_rating_performance(session, player_id, since=since)
    if not buckets:
        return []

    out: list[dict] = []
    total_games = sum(b["games"] for b in buckets)
    base_cpl = max(baseline["avg_cpl"], 5.0)

    for b in buckets:
        if b["games"] < 5 or b["win_rate"] >= RATING_WIN_FLOOR:
            continue
        # Distinguish "out-prepared" (CPL ~normal) vs "blundering" (CPL high).
        cpl_ratio = b["avg_cpl"] / base_cpl
        if cpl_ratio < 1.1:
            mode = "out-prepared / positional"
            why = "Your CPL is fine here — losses don't come from blunders."
            actions = [
                {
                    "kind": "study_repertoire",
                    "label": "Strengthen your opening repertoire (Lichess studies)",
                    "href": _OPENING_STUDIES_URL,
                    "external": True,
                },
                {
                    "kind": "review_games",
                    "label": "Drill into your losses against this bracket",
                    "href": f"/players/{player_id}/ratings",
                },
            ]
        else:
            mode = "blunder-driven"
            why = f"CPL is {cpl_ratio:.1f}× baseline against this strength — they punish your mistakes."
            actions = [
                {
                    "kind": "puzzle_theme",
                    "label": "Solve tactics puzzles",
                    "href": _lichess_puzzle_url("tactics"),
                    "external": True,
                },
                {
                    "kind": "review_games",
                    "label": "Review your losses to this bracket",
                    "href": f"/players/{player_id}/ratings",
                },
            ]

        severity = _clamp01((RATING_WIN_FLOOR - b["win_rate"]) / RATING_WIN_FLOOR)
        volume = _clamp01(b["games"] / max(total_games, 1) * 3)
        score = _score(severity, volume)

        out.append({
            "id": f"rating:{b['bucket']}",
            "kind": "rating_wall",
            "title": f"Opponents in {b['bucket']} are beating you",
            "summary": f"{int(b['win_rate']*100)}% win rate across {b['games']} games. {why}",
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "bucket": b["bucket"],
                "games": b["games"],
                "wins": b["wins"], "draws": b["draws"], "losses": b["losses"],
                "win_rate": b["win_rate"],
                "avg_cpl": b["avg_cpl"],
                "baseline_cpl": base_cpl,
                "mode": mode,
            },
            "actions": actions,
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_color_asymmetry(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    by = await _color_split(session, player_id, since)
    if "white" not in by or "black" not in by:
        return []
    w, b = by["white"], by["black"]
    if w["games"] < 5 or b["games"] < 5:
        return []

    score_gap = abs(w["score_rate"] - b["score_rate"]) * 100  # pct
    if score_gap < COLOR_GAP_PCT:
        return []

    weaker = "white" if w["score_rate"] < b["score_rate"] else "black"
    stronger = "black" if weaker == "white" else "white"
    severity = _clamp01(score_gap / 30.0)
    volume = _clamp01(by[weaker]["games"] / max(w["games"] + b["games"], 1) * 2)
    score = _score(severity, volume)

    return [{
        "id": f"color:{weaker}",
        "kind": "color_asymmetry",
        "title": f"Your {weaker} repertoire is underperforming",
        "summary": (
            f"Score rate as {weaker}: {by[weaker]['score_rate']*100:.0f}% vs "
            f"{by[stronger]['score_rate']*100:.0f}% as {stronger} "
            f"({score_gap:.0f}-pt gap)."
        ),
        "score": score,
        "severity": round(severity, 3),
        "volume": round(volume, 3),
        "evidence": {
            "weaker_color": weaker,
            "white": w,
            "black": b,
            "gap_pct": round(score_gap, 1),
        },
        "actions": [
            {
                "kind": "study_repertoire",
                "label": f"Build a better {weaker} repertoire",
                "href": _OPENING_STUDIES_URL,
                "external": True,
            },
            {
                "kind": "filter_games",
                "label": f"Filter to your {weaker} games",
                "href": f"/players/{player_id}/games?color={weaker}",
            },
        ],
    }]


async def _detect_missed_wins(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Games where the user reached a winning eval and failed to convert."""
    filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        filters.append(Game.played_at >= since)

    rows = (await session.execute(
        select(Game.id, Game.user_color, Game.user_result, Game.played_at)
        .where(and_(*filters))
        .order_by(Game.played_at.desc())
    )).all()
    if not rows:
        return []

    game_ids = [r.id for r in rows]
    moves = (await session.execute(
        select(GameMove.game_id, GameMove.eval_after_cp)
        .where(
            GameMove.game_id.in_(game_ids),
            GameMove.eval_after_cp.isnot(None),
        )
    )).all()

    color_by_game = {r.id: r.user_color for r in rows}
    max_fav_by_game: dict[uuid.UUID, int] = {}
    for gid, eval_cp in moves:
        if eval_cp is None:
            continue
        clamped = max(-1000, min(1000, eval_cp))
        favourable = clamped if color_by_game[gid] == "white" else -clamped
        prev = max_fav_by_game.get(gid)
        if prev is None or favourable > prev:
            max_fav_by_game[gid] = favourable

    winning_games: list[uuid.UUID] = []
    converted = 0
    drawn = 0
    lost = 0
    for r in rows:
        peak = max_fav_by_game.get(r.id, -10_000)
        if peak < MISSED_WINS_EVAL_CP:
            continue
        winning_games.append(r.id)
        if r.user_result == "win":
            converted += 1
        elif r.user_result == "draw":
            drawn += 1
        else:
            lost += 1

    if len(winning_games) < MISSED_WINS_MIN_GAMES:
        return []
    conversion = converted / len(winning_games)
    if conversion >= MISSED_WINS_FLOOR:
        return []

    severity = _clamp01((MISSED_WINS_FLOOR - conversion) / MISSED_WINS_FLOOR)
    volume = _clamp01(len(winning_games) / max(len(rows), 1))
    score = _score(severity, volume)
    missed = drawn + lost
    samples = [str(g) for g in winning_games[:3]]

    return [{
        "id": "missed_wins",
        "kind": "missed_wins",
        "title": "You're leaving winning positions on the board",
        "summary": (
            f"Converted only {int(conversion * 100)}% of {len(winning_games)} games "
            f"where your eval reached +{MISSED_WINS_EVAL_CP / 100:.1f}: "
            f"{converted}W / {drawn}D / {lost}L."
        ),
        "score": score,
        "severity": round(severity, 3),
        "volume": round(volume, 3),
        "evidence": {
            "winning_positions": len(winning_games),
            "converted": converted,
            "drawn": drawn,
            "lost": lost,
            "conversion_rate": round(conversion, 3),
            "threshold_cp": MISSED_WINS_EVAL_CP,
            "sample_game_ids": samples,
        },
        "actions": [
            {
                "kind": "puzzle_theme",
                "label": "Solve Lichess 'endgame' puzzles",
                "href": _lichess_puzzle_url("endgame"),
                "external": True,
            },
            {
                "kind": "view_phase",
                "label": "Open Phase dashboard (endgame breakdown)",
                "href": f"/players/{player_id}/phases",
            },
        ],
    }]


async def _detect_anti_repertoire(
    session: AsyncSession,
    player_id: uuid.UUID,
    baseline: dict,
    since: datetime | None,
    skip_keys: set[str],
) -> list[dict]:
    """Openings you face only 3-4 times but score badly — clearly unprepared."""
    if baseline["avg_cpl"] == 0:
        return []
    base_cpl = max(baseline["avg_cpl"], 5.0)
    stats = await get_opening_stats(
        session, player_id,
        min_games=ANTI_REP_MIN_GAMES,
        since=since,
    )
    out: list[dict] = []

    for o in stats:
        if not o["opening_name"]:
            continue
        if not (ANTI_REP_MIN_GAMES <= o["games"] < MIN_GAMES_FOR_OPENING_LEAK):
            continue
        cpl_ratio = o["avg_cpl"] / base_cpl
        is_hole = (
            cpl_ratio >= ANTI_REP_CPL_RATIO
            or o["win_rate"] < ANTI_REP_WIN_FLOOR
        )
        if not is_hole:
            continue
        key = f"{o['opening_name']}:{o['color']}"
        if key in skip_keys:
            continue

        severity_cpl = _clamp01((cpl_ratio - 1.0) / 1.5)
        severity_wr = _clamp01((0.5 - o["win_rate"]) / 0.5)
        severity = max(severity_cpl, severity_wr)
        volume = _clamp01(o["games"] / max(baseline["games"], 1) * 5)
        score = _score(severity, volume)

        out.append({
            "id": f"anti_repertoire:{key}",
            "kind": "anti_repertoire",
            "title": f"Unprepared line: {o['opening_name']} as {o['color']}",
            "summary": (
                f"Only {o['games']} games but {int(o['win_rate']*100)}% win rate / "
                f"CPL {o['avg_cpl']:.1f} ({cpl_ratio:.1f}× baseline). "
                f"Looks like you haven't drilled this line."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "opening_name": o["opening_name"],
                "eco": o["eco"],
                "color": o["color"],
                "games": o["games"],
                "wins": o["wins"], "draws": o["draws"], "losses": o["losses"],
                "win_rate": o["win_rate"],
                "avg_cpl": o["avg_cpl"],
                "baseline_cpl": base_cpl,
            },
            "actions": [
                {
                    "kind": "study_line",
                    "label": "Open on Lichess Opening Browser",
                    "href": _opening_browser_url(o["eco"], o["opening_name"]),
                    "external": True,
                },
                {
                    "kind": "review_games",
                    "label": f"Review your {o['games']} games in this line",
                    "href": f"/players/{player_id}/opening-stats",
                },
            ],
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def _is_hung_piece_blunder(fen_after: str, user_is_white: bool) -> bool:
    """Heuristic: after the user's move, is one of their non-pawn pieces
    attacked by more opponents than defenders (en-prise, no compensation)?

    fen_after is a fen_key (no halfmove/fullmove). Append placeholders so
    python-chess accepts it.
    """
    try:
        board = chess.Board(fen_after + " 0 1")
    except (ValueError, IndexError):
        return False
    user_colour = chess.WHITE if user_is_white else chess.BLACK
    opp_colour = not user_colour
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.color != user_colour:
            continue
        if piece.piece_type in (chess.PAWN, chess.KING):
            continue
        attackers = board.attackers(opp_colour, sq)
        defenders = board.attackers(user_colour, sq)
        if len(attackers) > len(defenders):
            return True
    return False


async def _detect_blunder_pattern(
    session: AsyncSession,
    player_id: uuid.UUID,
    baseline: dict,
    since: datetime | None,
) -> list[dict]:
    """Are the user's blunders mostly hung pieces (basic safety failures)?"""
    filters = [
        GameMove.is_user_move.is_(True),
        # A miss can also be a hung-piece blunder (you were winning, hung a
        # piece, gave back the win). Include both for the heuristic check.
        GameMove.classification.in_(("blunder", "miss")),
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
    ]
    if since is not None:
        filters.append(Game.played_at >= since)

    rows = (await session.execute(
        select(
            GameMove.game_id,
            GameMove.ply,
            Position.fen_key,
            Game.user_color,
        )
        .join(Game, GameMove.game_id == Game.id)
        .join(Position, GameMove.position_after_id == Position.id)
        .where(and_(*filters))
    )).all()

    if len(rows) < BLUNDER_PATTERN_MIN_BLUNDERS:
        return []

    hung = 0
    sample_game_ids: list[uuid.UUID] = []
    for game_id, _ply, fen, user_color in rows:
        if _is_hung_piece_blunder(fen, user_color == "white"):
            hung += 1
            if len(sample_game_ids) < 3 and game_id not in sample_game_ids:
                sample_game_ids.append(game_id)

    rate = hung / len(rows)
    if rate < BLUNDER_PATTERN_HUNG_FLOOR:
        return []

    severity = _clamp01((rate - BLUNDER_PATTERN_HUNG_FLOOR) / (1.0 - BLUNDER_PATTERN_HUNG_FLOOR))
    volume = _clamp01(len(rows) / max(baseline["user_moves"], 1) * 30)
    score = _score(severity, volume)

    return [{
        "id": "blunder_pattern:hung_piece",
        "kind": "blunder_pattern",
        "title": "Your blunders are mostly hanging pieces",
        "summary": (
            f"{hung} of your {len(rows)} blunders ({int(rate * 100)}%) just left a "
            f"piece en-prise. Basic-safety drills will beat deep tactics here."
        ),
        "score": score,
        "severity": round(severity, 3),
        "volume": round(volume, 3),
        "evidence": {
            "total_blunders": len(rows),
            "hung_piece_blunders": hung,
            "hung_rate": round(rate, 3),
            "sample_game_ids": [str(g) for g in sample_game_ids],
        },
        "actions": [
            {
                "kind": "puzzle_theme",
                "label": "Solve Lichess 'hanging piece' puzzles",
                "href": _lichess_puzzle_url("hangingPiece"),
                "external": True,
            },
            {
                "kind": "habit",
                "label": "Before every move: ask 'what does this piece attack?'",
            },
        ],
    }]


async def _detect_time_of_day(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Find a UTC hour bucket where the user plays meaningfully worse."""
    clamped_cpl = case(
        (GameMove.cp_loss > 1000, 1000),
        else_=GameMove.cp_loss,
    )
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        GameMove.is_user_move.is_(True),
        GameMove.cp_loss.isnot(None),
    ]
    if since is not None:
        filters.append(Game.played_at >= since)

    # SQLite: extract hour-of-day from played_at (ISO timestamp).
    hour_expr = func.cast(func.strftime("%H", Game.played_at), Integer)
    bucket_expr = (hour_expr / TIME_OF_DAY_BUCKET_HOURS) * TIME_OF_DAY_BUCKET_HOURS

    rows = (await session.execute(
        select(
            bucket_expr.label("bucket"),
            func.count(func.distinct(Game.id)).label("games"),
            func.avg(clamped_cpl).label("avg_cpl"),
            func.count().label("moves"),
        )
        .join(GameMove, GameMove.game_id == Game.id)
        .where(and_(*filters))
        .group_by(bucket_expr)
    )).all()

    eligible = [r for r in rows if r.games >= TIME_OF_DAY_MIN_GAMES_IN_BUCKET]
    if len(eligible) < 2:
        return []

    best = min(eligible, key=lambda r: float(r.avg_cpl or 0))
    worst = max(eligible, key=lambda r: float(r.avg_cpl or 0))
    if best.bucket == worst.bucket or not best.avg_cpl:
        return []

    ratio = float(worst.avg_cpl) / max(float(best.avg_cpl), 1.0)
    if ratio < TIME_OF_DAY_CPL_RATIO:
        return []

    total_games = sum(int(r.games) for r in rows)
    severity = _clamp01((ratio - 1.0) / 1.5)
    volume = _clamp01(int(worst.games) / max(total_games, 1) * 2)
    score = _score(severity, volume)

    def bucket_label(b: int) -> str:
        end = (b + TIME_OF_DAY_BUCKET_HOURS) % 24
        return f"{b:02d}:00-{end:02d}:00 UTC"

    return [{
        "id": f"time_of_day:{int(worst.bucket)}",
        "kind": "time_of_day",
        "title": "You play meaningfully worse at certain hours",
        "summary": (
            f"CPL in {bucket_label(int(worst.bucket))} is "
            f"{float(worst.avg_cpl):.0f} vs {float(best.avg_cpl):.0f} in "
            f"{bucket_label(int(best.bucket))} ({ratio:.1f}× worse)."
        ),
        "score": score,
        "severity": round(severity, 3),
        "volume": round(volume, 3),
        "evidence": {
            "worst_bucket_utc_start_hour": int(worst.bucket),
            "worst_bucket_label": bucket_label(int(worst.bucket)),
            "worst_bucket_games": int(worst.games),
            "worst_bucket_cpl": round(float(worst.avg_cpl), 1),
            "best_bucket_utc_start_hour": int(best.bucket),
            "best_bucket_label": bucket_label(int(best.bucket)),
            "best_bucket_cpl": round(float(best.avg_cpl), 1),
            "bucket_hours": TIME_OF_DAY_BUCKET_HOURS,
            "ratio": round(ratio, 2),
        },
        "actions": [
            {
                "kind": "habit",
                "label": "Save serious chess for your strong hours; play casually otherwise.",
            },
        ],
    }]


async def _detect_tilt(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Compare in-session next-game accuracy after a loss vs after a win."""
    game_filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        game_filters.append(Game.played_at >= since)

    games = (await session.execute(
        select(Game.id, Game.played_at, Game.user_result)
        .where(and_(*game_filters))
        .order_by(Game.played_at.asc())
    )).all()
    if len(games) < TILT_MIN_SAMPLES_EACH * 2:
        return []

    game_ids = [g.id for g in games]
    move_rows = (await session.execute(
        select(GameMove)
        .where(GameMove.game_id.in_(game_ids))
        .order_by(GameMove.game_id, GameMove.ply)
    )).scalars().all()
    moves_by_game: dict[uuid.UUID, list[GameMove]] = {}
    for m in move_rows:
        moves_by_game.setdefault(m.game_id, []).append(m)

    accuracy_by_game: dict[uuid.UUID, float] = {}
    for gid, ms in moves_by_game.items():
        acc, _cpl, n = compute_game_accuracy(ms)
        if n > 0:
            accuracy_by_game[gid] = acc

    post_loss: list[float] = []
    post_win: list[float] = []
    for i in range(1, len(games)):
        prev, cur = games[i - 1], games[i]
        if not prev.played_at or not cur.played_at:
            continue
        if (cur.played_at - prev.played_at).total_seconds() > SESSION_GAP_SECONDS:
            continue
        cur_acc = accuracy_by_game.get(cur.id)
        if cur_acc is None:
            continue
        if prev.user_result == "loss":
            post_loss.append(cur_acc)
        elif prev.user_result == "win":
            post_win.append(cur_acc)

    if len(post_loss) < TILT_MIN_SAMPLES_EACH or len(post_win) < TILT_MIN_SAMPLES_EACH:
        return []

    avg_loss = sum(post_loss) / len(post_loss)
    avg_win = sum(post_win) / len(post_win)
    gap = avg_win - avg_loss
    if gap < TILT_ACCURACY_GAP:
        return []

    severity = _clamp01(gap / 20.0)
    total_session = len(post_loss) + len(post_win)
    volume = _clamp01(len(post_loss) / max(total_session, 1) * 2)
    score = _score(severity, volume)

    return [{
        "id": "tilt:post_loss",
        "kind": "tilt",
        "title": "You play worse after a loss in the same session",
        "summary": (
            f"After-loss accuracy is {avg_loss:.1f}% vs {avg_win:.1f}% after a win "
            f"({gap:.1f}-point gap across {len(post_loss)}/{len(post_win)} games)."
        ),
        "score": score,
        "severity": round(severity, 3),
        "volume": round(volume, 3),
        "evidence": {
            "post_loss_avg_accuracy": round(avg_loss, 1),
            "post_loss_sample": len(post_loss),
            "post_win_avg_accuracy": round(avg_win, 1),
            "post_win_sample": len(post_win),
            "gap_points": round(gap, 1),
            "session_gap_minutes": SESSION_GAP_SECONDS // 60,
        },
        "actions": [
            {
                "kind": "habit",
                "label": "Stop the session after 2 consecutive losses.",
            },
            {
                "kind": "view_trend",
                "label": "Open Accuracy Trend",
                "href": f"/players/{player_id}/accuracy",
            },
        ],
    }]


async def _detect_tactic_blindspot(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Motifs you miss disproportionately often vs how common they are in chess.

    Raw counts would just surface "you missed a lot of forks" for every
    player (because forks are common); we want the motif whose *share* of
    your missed tactics is over its expected baseline share. Lift ≥ 1.5
    with at least BLINDSPOT_MIN_MISSES instances triggers a flag.
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        GameMove.is_user_move.is_(True),
    ]
    if since is not None:
        filters.append(Game.played_at >= since)

    rows = (await session.execute(
        select(
            MoveTactic.motif,
            func.count().label("misses"),
            func.count(func.distinct(GameMove.game_id)).label("games"),
            func.avg(GameMove.cp_loss).label("avg_cp_loss"),
        )
        .join(GameMove, GameMove.id == MoveTactic.game_move_id)
        .join(Game, Game.id == GameMove.game_id)
        .where(and_(*filters))
        .group_by(MoveTactic.motif)
    )).all()
    if not rows:
        return []
    total = sum(int(r.misses) for r in rows)
    if total < BLINDSPOT_MIN_MISSES:
        return []

    out: list[dict] = []
    for r in rows:
        misses = int(r.misses)
        if misses < BLINDSPOT_MIN_MISSES:
            continue
        baseline = _MOTIF_BASELINE.get(r.motif)
        if baseline is None:
            # Detector grew a new motif kind not yet in the baseline table.
            # Skip rather than fabricate a comparison — drops noisily-flagged
            # zero-share lift values that would always read as "blindspot".
            continue
        share = misses / total
        lift = share / baseline if baseline > 0 else 0.0
        if lift < BLINDSPOT_LIFT_RATIO:
            continue

        severity = _clamp01((lift - 1.0) / 2.0)
        volume = _clamp01(misses / max(total, 1))
        score = _score(severity, volume)
        label = _MOTIF_HUMAN_LABEL.get(r.motif, r.motif.replace("_", " "))
        theme = _MOTIF_PUZZLE_THEME.get(r.motif)
        actions: list[dict] = []
        if theme is not None:
            actions.append({
                "kind": "puzzle_theme",
                "label": f"Solve Lichess '{theme}' puzzles",
                "href": _lichess_puzzle_url(theme),
                "external": True,
            })
        actions.append({
            "kind": "view_tactics",
            "label": "Open Tactical Patterns page",
            "href": f"/players/{player_id}/tactics",
        })

        out.append({
            "id": f"tactic_blindspot:{r.motif}",
            "kind": "tactic_blindspot",
            "title": f"You miss {label} more than expected",
            "summary": (
                f"{label.capitalize()} are {share*100:.0f}% of your missed tactics "
                f"({misses} of {total}) — {lift:.1f}× the baseline share "
                f"({baseline*100:.0f}%) for chess generally."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "motif": r.motif,
                "misses": misses,
                "games_affected": int(r.games or 0),
                "share_of_misses": round(share, 3),
                "baseline_share": round(baseline, 3),
                "lift": round(lift, 2),
                "avg_cp_loss": round(float(r.avg_cp_loss or 0), 0),
                "total_missed_tactics": total,
            },
            "actions": actions,
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_endgame_pattern(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Endgame buckets (KRPvKR, KPvK, etc.) with poor conversion.

    Complements ``missed_wins`` (whole-game) by pinpointing *which kind* of
    endgame is leaking points — a player who converts 90% of pawn endings
    but 30% of rook endings should drill rook technique, not "endgames" as
    a vague category.
    """
    buckets = await get_endgame_summary(
        session, player_id,
        since=since,
        min_reached=ENDGAME_PATTERN_MIN_REACHED,
    )
    if not buckets:
        return []

    total_reached = sum(b["reached"] for b in buckets)
    out: list[dict] = []
    for b in buckets:
        rate = b["conversion_rate"]
        if rate >= ENDGAME_PATTERN_CONVERSION_FLOOR:
            continue
        # "Reached" counts winning-eval entries; "lost the win" is the
        # interesting number to surface, since that's what the player feels.
        lost_the_win = b["reached"] - b["converted"]
        severity = _clamp01(
            (ENDGAME_PATTERN_CONVERSION_FLOOR - rate) / ENDGAME_PATTERN_CONVERSION_FLOOR
        )
        volume = _clamp01(b["reached"] / max(total_reached, 1) * 3)
        score = _score(severity, volume)

        out.append({
            "id": f"endgame_pattern:{b['bucket']}",
            "kind": "endgame_pattern",
            "title": f"{b['bucket']} endings: only {int(rate*100)}% converted",
            "summary": (
                f"Reached {b['bucket']} with a winning eval in {b['reached']} "
                f"games, won {b['converted']} ({int(rate*100)}%). Lost the win "
                f"{lost_the_win} time{'s' if lost_the_win != 1 else ''}."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "bucket": b["bucket"],
                "reached": b["reached"],
                "converted": b["converted"],
                "conversion_rate": rate,
                "lost_the_win": lost_the_win,
                "avg_cp_at_entry": b["avg_cp_at_entry"],
            },
            "actions": [
                {
                    "kind": "view_endgames",
                    "label": "Open Endgames page (drill into this bucket)",
                    "href": f"/players/{player_id}/endgames",
                },
                {
                    "kind": "puzzle_theme",
                    "label": "Solve Lichess endgame puzzles",
                    "href": _lichess_puzzle_url("endgame"),
                    "external": True,
                },
            ],
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return out


async def _detect_phase_vs_peer(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None,
) -> list[dict]:
    """Phases where your CPL is meaningfully worse than your opponents'.

    Different angle than ``phase_weakness``: that one compares a phase to
    YOUR own baseline (so a player whose all phases are equally bad gets
    no flag); this one compares to the opponents you actually face, which
    catches "this phase looks normal for me but the people I play do it
    much better."
    """
    phases = await get_phase_performance(session, player_id, since)
    out: list[dict] = []
    for p in phases:
        if p["opponent_sample_size"] < PHASE_VS_PEER_MIN_OPP_MOVES:
            continue
        delta = p["avg_cpl"] - p["opponent_avg_cpl"]
        if delta < PHASE_VS_PEER_DELTA_CP:
            continue

        severity = _clamp01(delta / 30.0)
        volume = _clamp01(p["sample_size"] / max(p["sample_size"] + p["opponent_sample_size"], 1) * 2)
        score = _score(severity, volume)
        theme = {"opening": "opening", "middlegame": "middlegame", "endgame": "endgame"}.get(p["phase"], "middlegame")

        out.append({
            "id": f"phase_vs_peer:{p['phase']}",
            "kind": "phase_vs_peer",
            "title": f"Opponents outplay you in the {p['phase']}",
            "summary": (
                f"CPL in {p['phase']}: you {p['avg_cpl']:.1f} vs opponents "
                f"{p['opponent_avg_cpl']:.1f} (+{delta:.1f}). They handle this "
                f"phase materially better than you do."
            ),
            "score": score,
            "severity": round(severity, 3),
            "volume": round(volume, 3),
            "evidence": {
                "phase": p["phase"],
                "user_avg_cpl": p["avg_cpl"],
                "opponent_avg_cpl": p["opponent_avg_cpl"],
                "delta_cp": round(delta, 1),
                "user_moves": p["sample_size"],
                "opponent_moves": p["opponent_sample_size"],
            },
            "actions": [
                {
                    "kind": "view_phase",
                    "label": "Open Phase Performance (with You/Opp/Δ breakdown)",
                    "href": f"/players/{player_id}/phases",
                },
                {
                    "kind": "puzzle_theme",
                    "label": f"Solve Lichess '{theme}' puzzles",
                    "href": _lichess_puzzle_url(theme),
                    "external": True,
                },
            ],
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return out


# --- Trend wrapper ----------------------------------------------------------

def _prior_window(since: datetime | None) -> datetime | None:
    """For a "current range starting at ``since``", return the cutoff for the
    equivalent prior period (same length, ending where the current period begins).

    For ``since is None`` (all-time), prior = "older than 90 days" by convention.
    """
    if since is None:
        return None  # signal to caller: compare last 90d vs everything older
    delta = datetime.now(timezone.utc) - since
    return since - delta


async def _run_with_trend(
    detector,
    *args,
    since: datetime | None,
    **kwargs,
) -> list[dict]:
    """Run a detector for the current period AND the prior period, then
    attach a ``trend`` field to each current rec.

    Detectors are pure functions of ``since`` plus their other args.
    """
    current = await detector(*args, since=since, **kwargs)

    # Build the prior-period ``since``.
    if since is None:
        # all-time: prior = older than 90 days; current is "as is" with no
        # since filter. To make the comparison meaningful, run current as
        # "last 90 days" too. To avoid changing the public output, leave
        # current as-is and define prior_since as "since 365 days ago, ending
        # 90 days ago". Just compare on whether the same id surfaced.
        prior_since = datetime.now(timezone.utc) - timedelta(days=365)
        # Prior detection is approximate for all-time view; skip trend chip
        # there to avoid misleading deltas.
        return current
    else:
        prior_since = _prior_window(since)

    if prior_since is None:
        return current

    try:
        prior = await detector(*args, since=prior_since, **kwargs)
    except Exception:
        logger.exception("Prior-period detector failed; trend chip suppressed")
        return current

    prior_by_id = {r["id"]: r for r in prior}
    for rec in current:
        p = prior_by_id.get(rec["id"])
        cur_sev = float(rec.get("severity", 0))
        if p is None:
            rec["trend"] = {
                "direction": "worsening",
                "current": cur_sev,
                "prior": 0.0,
                "delta": cur_sev,
                "note": "new since prior period",
            }
        else:
            prior_sev = float(p.get("severity", 0))
            delta = cur_sev - prior_sev
            if abs(delta) < 0.05:
                direction = "stable"
            elif delta > 0:
                direction = "worsening"
            else:
                direction = "improving"
            rec["trend"] = {
                "direction": direction,
                "current": cur_sev,
                "prior": prior_sev,
                "delta": round(delta, 3),
            }
    return current


# --- Public entry point -----------------------------------------------------

async def get_recommendations(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None = None,
) -> dict:
    """Return a ranked list of weaknesses + training actions."""
    baseline = await _player_baseline(session, player_id, since)

    if baseline["games"] == 0:
        return {
            "baseline": baseline,
            "recommendations": [],
            "message": "No analyzed games in this range yet — finish an import first.",
        }

    # Original detectors. Each gets its trend chip attached for non-"all" ranges.
    opening_leaks = await _run_with_trend(
        _detect_opening_leaks, session, player_id, baseline, baseline["games"],
        since=since,
    )
    # Skip-set so anti_repertoire doesn't duplicate any opening already promoted
    # to a full leak.
    leak_keys = {
        f"{r['evidence']['opening_name']}:{r['evidence']['color']}"
        for r in opening_leaks
    }

    detectors_simple = [
        (_detect_phase_weakness, (session, player_id, baseline)),
        (_detect_phase_vs_peer, (session, player_id)),
        (_detect_time_pressure, (session, player_id)),
        (_detect_rating_walls, (session, player_id, baseline)),
        (_detect_color_asymmetry, (session, player_id)),
        (_detect_missed_wins, (session, player_id)),
        (_detect_endgame_pattern, (session, player_id)),
        (_detect_tactic_blindspot, (session, player_id)),
        (_detect_blunder_pattern, (session, player_id, baseline)),
        (_detect_time_of_day, (session, player_id)),
        (_detect_tilt, (session, player_id)),
    ]

    parts: list[dict] = list(opening_leaks)
    for det, args in detectors_simple:
        parts += await _run_with_trend(det, *args, since=since)

    parts += await _run_with_trend(
        _detect_anti_repertoire, session, player_id, baseline, skip_keys=leak_keys,
        since=since,
    )

    parts.sort(key=lambda r: r["score"], reverse=True)
    # Top-N — the user has a finite attention budget.
    top = parts[:TOP_N]

    return {
        "baseline": baseline,
        "recommendations": top,
        "totals": {
            "candidates": len(parts),
            "returned": len(top),
        },
    }
