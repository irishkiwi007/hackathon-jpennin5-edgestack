"""Macro regime overlay - the strongest conditioning variable found.

Construction taken from TrustyRustyEngine's `spxlrealyields` strategy, which already
parameter-tested it:

    calm  =  TLT 21-day stdev  <  its own 90-day mean, with 1.5% hysteresis

Why this and not the others. Five overlays were tested on 115 ETF capitulation events and then
re-tested out-of-sample on 4,359 single-name events. Four contradicted:

    overlay                 ETF (n=115)      single names (n=4,359)
    credit healthy          -1.59 t=-2.80    +0.15 t=0.66      contradicts
    risk_on                 -1.38 t=-2.26    +0.49 t=2.22      contradicts (sign flip)
    gold lagging            +0.70 t=1.11     -0.11 t=-0.52     contradicts
    calm AND gold lagging   +1.82 t=2.56     +0.39 t=1.55      evaporated
    macro calm              +1.12 t=1.64     +1.49 t=6.58      CONFIRMS

Only the bond-volatility regime replicated, and it replicated hard:

    calm bonds     n=1598   +1.553%   win 63.3%
    stressed       n=2761   +0.066%   win 55.7%      t(diff) = 6.58

It also STACKS with the volume tiers rather than duplicating them - in a calm regime every
volume cell from 1.4x to 4.0x works (t=2.9 to 6.1); in a stressed regime none does, and the
1.4-1.8 cell is significantly negative.

Mechanism: it is the volume ceiling again, one level up. Extreme volume means real information
arrived at the single-name level, so there is nothing to revert. Stressed bonds mean real risk
is being repriced at the macro level - same thing, same consequence.

Honest limit: era stability is 3/5. It failed in 2016-2017 (t(diff)=-2.01) and was neutral in
2018-2019 - both periods when bond volatility barely varied, so the regime split carried little
information. It works hard in 2020-2026 (t(diff) = 3.49, 5.05, 2.57).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

TLT_STD_LB = 21          # stdev window
VOL_LB = 90              # mean-of-stdev window
TOL = 0.015              # hysteresis, so the state does not chatter at the boundary
MIN_BARS = TLT_STD_LB + VOL_LB


@dataclass(frozen=True)
class RegimeState:
    calm: bool
    current_std: float
    average_std: float
    ratio: float
    as_of: str

    @property
    def label(self) -> str:
        return "CALM" if self.calm else "STRESSED"

    @property
    def reason(self) -> str:
        return ("TLT 21d sd {:.3f} vs 90d mean {:.3f} (ratio {:.2f}) -> {}".format(
            self.current_std, self.average_std, self.ratio, self.label))


def _stdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def evaluate(closes: Sequence[float], dates: Sequence[str]) -> RegimeState | None:
    """Walk the whole history so the hysteresis state is path-correct.

    Evaluating only the last bar would give a different answer than running forward from the
    start, because hysteresis is path-dependent by construction. Cheap enough to redo daily.
    """
    if len(closes) < MIN_BARS:
        return None

    stds: list[float] = []
    for i in range(TLT_STD_LB, len(closes) + 1):
        stds.append(_stdev(closes[i - TLT_STD_LB:i]))
    if len(stds) < VOL_LB:
        return None

    state = False
    now = avg = 0.0
    for j in range(VOL_LB, len(stds) + 1):
        window = stds[j - VOL_LB:j]
        now = window[-1]
        avg = sum(window) / len(window)
        if not state:
            state = now < avg * (1 - TOL)
        else:
            state = now <= avg * (1 + TOL)

    return RegimeState(calm=state, current_std=now, average_std=avg,
                       ratio=(now / avg if avg else 0.0),
                       as_of=dates[-1] if dates else "")
