"""DraftKings' NFL Classic lineup rules, and a checker for a lineup.

The rules are kept here as constants, like the scoring rules
(docs/adr/0002-draftkings-scoring-rules-in-code.md). They come from the same
DraftKings page, last checked on the same date: see RULES_URL and
RULES_LAST_CHECKED in draftkings_scoring.

A lineup with fewer than 9 players isn't illegal, just incomplete: the
checker reports its open slots and the salary left for them, which is what
helps when building a lineup a player at a time.
"""

from dataclasses import dataclass

SALARY_CAP = 50_000

# The 9 slots, in DraftKings' order. FLEX takes an RB, WR or TE.
ROSTER_SLOTS: tuple[str, ...] = (
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "DST",
)
FLEX_POSITIONS = frozenset({"RB", "WR", "TE"})

# A lineup can't come from a single NFL game.
MIN_GAMES = 2


@dataclass(frozen=True)
class LineupPlayer:
    """A player on the slate. position is QB, RB, WR, TE or DST."""

    name: str
    position: str
    salary: int
    team: str
    opponent: str


@dataclass(frozen=True)
class LineupCheck:
    """What the checker found.

    slots pairs each filled slot with its player, in ROSTER_SLOTS order.
    problems lists every rule the lineup breaks; an incomplete lineup with no
    problems isn't legal yet, but nothing is wrong with it so far.
    """

    problems: list[str]
    slots: list[tuple[str, LineupPlayer]]
    open_slots: list[str]
    salary: int
    salary_left: int

    @property
    def complete(self) -> bool:
        return not self.open_slots

    @property
    def legal(self) -> bool:
        return self.complete and not self.problems

    @property
    def salary_left_per_open_slot(self) -> float | None:
        if not self.open_slots:
            return None
        return self.salary_left / len(self.open_slots)


def check_lineup(players: list[LineupPlayer]) -> LineupCheck:
    """Check a lineup of up to 9 players against DraftKings' Classic rules."""
    problems: list[str] = []
    lineup: list[LineupPlayer] = []
    for player in players:
        if any(_same(player, chosen) for chosen in lineup):
            problems.append(f"{player.name} is in the lineup more than once.")
        else:
            lineup.append(player)

    filled: dict[int, LineupPlayer] = {}
    for player in lineup:
        slot = _open_slot(player.position, filled)
        if slot is not None:
            filled[slot] = player
        elif player.position in ROSTER_SLOTS:
            problems.append(_too_many(player))
        else:
            problems.append(
                f"{player.name} plays {player.position}, which has no slot in a "
                "DraftKings Classic lineup."
            )

    salary = sum(player.salary for player in lineup)
    if salary > SALARY_CAP:
        problems.append(
            f"${salary:,} is ${salary - SALARY_CAP:,} over the "
            f"${SALARY_CAP:,} salary cap."
        )

    open_slots = [slot for i, slot in enumerate(ROSTER_SLOTS) if i not in filled]
    games = {frozenset((player.team, player.opponent)) for player in filled.values()}
    if not open_slots and len(games) < MIN_GAMES:
        teams = " vs ".join(sorted(next(iter(games))))
        problems.append(
            f"All players are from one game ({teams}); a lineup needs players "
            f"from at least {MIN_GAMES} games."
        )

    return LineupCheck(
        problems=problems,
        slots=[(ROSTER_SLOTS[i], filled[i]) for i in sorted(filled)],
        open_slots=open_slots,
        salary=salary,
        salary_left=SALARY_CAP - salary,
    )


def _same(a: LineupPlayer, b: LineupPlayer) -> bool:
    return (a.name, a.team) == (b.name, b.team)


def _open_slot(position: str, filled: dict[int, LineupPlayer]) -> int | None:
    # A player's own position first, then FLEX. Each player has one position
    # and FLEX is the only shared slot, so this fills every slot that can be.
    for i, slot in enumerate(ROSTER_SLOTS):
        if slot == position and i not in filled:
            return i
    for i, slot in enumerate(ROSTER_SLOTS):
        if slot == "FLEX" and position in FLEX_POSITIONS and i not in filled:
            return i
    return None


def _too_many(player: LineupPlayer) -> str:
    position = player.position
    count = ROSTER_SLOTS.count(position)
    allowed = f"{count} {position}" + ("s" if count > 1 else "")
    if position in FLEX_POSITIONS:
        allowed += " plus the FLEX"
    return (
        f"Too many {position}s: a lineup has room for {allowed}, so there's no "
        f"slot for {player.name}."
    )
