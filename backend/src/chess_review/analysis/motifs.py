"""Tactical motif detection on the engine's preferred line.

Given a position the user reached and an engine PV they didn't follow, this
module classifies the kind of tactic the user missed: fork, pin, skewer,
discovered attack, removal of defender, back-rank mate.

All detectors are pure ``python-chess`` board predicates — no engine calls,
no ML. The intent is precision over recall: a false positive ("you missed
back-rank mates") is worse than a quiet miss, because it teaches the wrong
lesson.
"""

from __future__ import annotations

import chess

# Standard piece values (centipawn-ish, only used for ordering "more valuable").
_PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 100000,
}


# Public motif names. Kept as plain strings so they're easy to surface in the
# API without an enum dance.
FORK = "fork"
PIN = "pin"
SKEWER = "skewer"
DISCOVERED_ATTACK = "discovered_attack"
REMOVAL_OF_DEFENDER = "removal_of_defender"
BACK_RANK_MATE = "back_rank_mate"

ALL_MOTIFS = (
    FORK,
    PIN,
    SKEWER,
    DISCOVERED_ATTACK,
    REMOVAL_OF_DEFENDER,
    BACK_RANK_MATE,
)


def detect_motifs(
    fen_before: str,
    best_uci: str,
    pv_uci: str,
    eval_mate: int | None,
) -> list[str]:
    """Return the motifs present on the engine's best move.

    ``fen_before`` is the position before the missed move. ``best_uci`` is
    the engine's first move on the PV. ``pv_uci`` is space-separated UCI
    moves of the PV (typically 5 moves). ``eval_mate`` is the engine's mate
    score from White's perspective if any, used only for back-rank-mate
    detection.

    Returns a deduplicated list of motif strings. Empty if nothing matched.
    """
    try:
        board = chess.Board(fen_before)
    except ValueError:
        return []

    try:
        best_move = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return []
    if best_move not in board.legal_moves:
        return []

    pv_moves: list[chess.Move] = []
    for tok in pv_uci.split():
        try:
            pv_moves.append(chess.Move.from_uci(tok))
        except (ValueError, chess.InvalidMoveError):
            break

    motifs: set[str] = set()

    if _is_back_rank_mate(board, best_move, eval_mate):
        motifs.add(BACK_RANK_MATE)

    # Snapshot attacker state BEFORE the move so we can diff after.
    mover_color = board.turn
    from_sq = best_move.from_square
    to_sq = best_move.to_square

    # Capture/removal-of-defender check uses pre-move attacker maps.
    captured_piece = board.piece_at(to_sq)

    # Push the move and inspect the resulting board.
    board.push(best_move)

    if _is_fork(board, best_move, mover_color):
        motifs.add(FORK)

    pin_motif = _pin_or_skewer(board, best_move, mover_color)
    if pin_motif:
        motifs.add(pin_motif)

    if _is_discovered_attack(board, from_sq, to_sq, mover_color):
        motifs.add(DISCOVERED_ATTACK)

    # Removal-of-defender: best move captured a defender, leaving its
    # previous protectee hanging or capturable on the next ply. Uses
    # post-move board to find newly attackable targets.
    if captured_piece is not None:
        if _is_removal_of_defender(board, to_sq, captured_piece, mover_color, pv_moves):
            motifs.add(REMOVAL_OF_DEFENDER)

    return sorted(motifs)


def _is_fork(board: chess.Board, move: chess.Move, mover_color: chess.Color) -> bool:
    """The moved piece now attacks two or more enemy pieces, at least one of
    which is more valuable than the moved piece (or undefended).
    """
    moved_piece = board.piece_at(move.to_square)
    if moved_piece is None:
        return False
    enemy = not mover_color
    attacks = board.attacks(move.to_square)
    targets: list[tuple[chess.Square, chess.Piece]] = []
    for sq in attacks:
        p = board.piece_at(sq)
        if p is not None and p.color == enemy:
            targets.append((sq, p))
    if len(targets) < 2:
        return False

    moved_val = _PIECE_VALUE[moved_piece.piece_type]
    valuable_targets = 0
    for sq, piece in targets:
        if piece.piece_type == chess.KING:
            valuable_targets += 1
            continue
        defenders = board.attackers(enemy, sq)
        if _PIECE_VALUE[piece.piece_type] > moved_val or not defenders:
            valuable_targets += 1
    return valuable_targets >= 2


def _pin_or_skewer(
    board: chess.Board, move: chess.Move, mover_color: chess.Color
) -> str | None:
    """Does the moved sliding piece create a line that ties an enemy piece to
    a more valuable enemy piece (pin) or a less valuable one in front (skewer)?
    """
    moved = board.piece_at(move.to_square)
    if moved is None or moved.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return None
    enemy = not mover_color

    # Sliding directions that piece type can use.
    deltas: list[tuple[int, int]] = []
    if moved.piece_type in (chess.BISHOP, chess.QUEEN):
        deltas.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
    if moved.piece_type in (chess.ROOK, chess.QUEEN):
        deltas.extend([(1, 0), (-1, 0), (0, 1), (0, -1)])

    sq = move.to_square
    file, rank = chess.square_file(sq), chess.square_rank(sq)

    for df, dr in deltas:
        first: chess.Piece | None = None
        first_sq: chess.Square | None = None
        f, r = file + df, rank + dr
        while 0 <= f < 8 and 0 <= r < 8:
            test_sq = chess.square(f, r)
            piece = board.piece_at(test_sq)
            if piece is not None:
                if first is None:
                    if piece.color != enemy:
                        break  # blocked by friendly piece, no skewer/pin here
                    first = piece
                    first_sq = test_sq
                else:
                    if piece.color != enemy:
                        break  # second piece is friendly — not a pin/skewer
                    # Two enemy pieces aligned with the attacker.
                    front_val = _PIECE_VALUE[first.piece_type]
                    back_val = _PIECE_VALUE[piece.piece_type]
                    if piece.piece_type == chess.KING:
                        return PIN  # absolute pin
                    if back_val > front_val:
                        return PIN
                    if front_val > back_val:
                        return SKEWER
                    break
            f += df
            r += dr
    return None


def _is_discovered_attack(
    board: chess.Board,
    from_sq: chess.Square,
    to_sq: chess.Square,
    mover_color: chess.Color,
) -> bool:
    """Moving the piece off ``from_sq`` uncovered an attack by a *different*
    friendly slider on an enemy piece.
    """
    enemy = not mover_color
    file_from, rank_from = chess.square_file(from_sq), chess.square_rank(from_sq)
    deltas = [(1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]

    for df, dr in deltas:
        # Walk back from ``from_sq`` toward our own side to find the friendly
        # slider that was previously blocked, then walk forward to find the
        # enemy piece it now attacks.
        attacker_sq: chess.Square | None = None
        f, r = file_from - df, rank_from - dr
        while 0 <= f < 8 and 0 <= r < 8:
            sq = chess.square(f, r)
            piece = board.piece_at(sq)
            if piece is not None:
                if piece.color == mover_color and _slides_along(piece.piece_type, df, dr):
                    attacker_sq = sq
                break
            f -= df
            r -= dr
        if attacker_sq is None:
            continue

        # Walk forward from ``from_sq`` (skipping ``to_sq`` if collinear) to
        # find the new target.
        f, r = file_from + df, rank_from + dr
        while 0 <= f < 8 and 0 <= r < 8:
            sq = chess.square(f, r)
            if sq == to_sq:
                # The moving piece landed on this ray — still blocking, so
                # no discovery here.
                break
            piece = board.piece_at(sq)
            if piece is not None:
                if piece.color == enemy and piece.piece_type != chess.PAWN:
                    return True
                break
            f += df
            r += dr
    return False


def _slides_along(piece_type: chess.PieceType, df: int, dr: int) -> bool:
    diagonal = df != 0 and dr != 0
    if diagonal:
        return piece_type in (chess.BISHOP, chess.QUEEN)
    return piece_type in (chess.ROOK, chess.QUEEN)


def _is_removal_of_defender(
    board_after: chess.Board,
    captured_sq: chess.Square,
    captured_piece: chess.Piece,
    mover_color: chess.Color,
    pv_moves: list[chess.Move],
) -> bool:
    """The captured piece was defending an enemy piece that's now hanging.

    We check by replaying the PV one more half-move: if the opponent's reply
    doesn't save the protectee and our next move can win it, it's a removal
    pattern.
    """
    enemy = not mover_color
    # The captured piece's old attack squares before capture: just the
    # squares we can see from ``captured_sq`` using the captured piece's
    # move pattern.
    # python-chess doesn't expose "attacks-from-a-given-piece-at-square" for
    # an arbitrary piece, but ``board.attacks`` reads the piece at that
    # square — after capture there's a mover_color piece sitting there.
    # Use ``board.attackers`` to find what defenders an enemy piece has now;
    # if a protectee lost its only defender (which was on ``captured_sq``)
    # and the new attacker (our piece) sits there, the protectee is
    # vulnerable.
    if not pv_moves or len(pv_moves) < 2:
        return False

    # The protectee candidates are enemy pieces that used to be defended
    # only by the captured piece. We approximate "used to be defended" by
    # checking, on the post-capture board, which enemy pieces are attacked
    # by our piece on ``captured_sq`` and would have been undefended once
    # the original defender was removed.
    our_piece = board_after.piece_at(captured_sq)
    if our_piece is None:
        return False

    for sq in board_after.attacks(captured_sq):
        target = board_after.piece_at(sq)
        if target is None or target.color != enemy:
            continue
        if target.piece_type == chess.KING:
            continue
        # If the captured defender was the only one defending ``sq``, and
        # ``sq`` now has no enemy defenders, this is a removal-of-defender.
        defenders_now = board_after.attackers(enemy, sq)
        attackers_now = board_after.attackers(mover_color, sq)
        if attackers_now and not defenders_now:
            # And the target is at least as valuable as the captured piece
            # (otherwise capturing the defender was just a trade, not a win).
            if _PIECE_VALUE[target.piece_type] >= _PIECE_VALUE[captured_piece.piece_type]:
                return True
    return False


def _is_back_rank_mate(
    board_before: chess.Board, move: chess.Move, eval_mate: int | None
) -> bool:
    """Heuristic: short forced mate by a rook/queen landing on the enemy back
    rank, with the enemy king on its back rank and pawns blocking its escape.
    """
    if eval_mate is None or abs(eval_mate) > 3:
        return False
    mover_color = board_before.turn
    enemy = not mover_color
    enemy_king_sq = board_before.king(enemy)
    if enemy_king_sq is None:
        return False
    back_rank = 0 if enemy == chess.WHITE else 7
    if chess.square_rank(enemy_king_sq) != back_rank:
        return False

    # The move's target square is on the back rank, with a rook or queen.
    moving_piece = board_before.piece_at(move.from_square)
    if moving_piece is None or moving_piece.piece_type not in (chess.ROOK, chess.QUEEN):
        return False
    if chess.square_rank(move.to_square) != back_rank:
        return False

    # The king's escape squares on rank-from-back are blocked by own pawns.
    escape_rank = 1 if enemy == chess.WHITE else 6
    king_file = chess.square_file(enemy_king_sq)
    escape_files = [f for f in (king_file - 1, king_file, king_file + 1) if 0 <= f < 8]
    for f in escape_files:
        sq = chess.square(f, escape_rank)
        p = board_before.piece_at(sq)
        if p is None or p.color != enemy or p.piece_type != chess.PAWN:
            return False
    return True
