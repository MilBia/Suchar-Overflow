"""Comedy Rank names for the profile page (issue #291).

``UserDetailView`` shows a dense rank by funny votes received (#229). The raw
number is dry, so it is rendered under a playful rank name instead (the number
stays as small secondary text next to the name, and in the element's ``title``).

The mapping is a pure function of three integers so it can be unit-tested at the
band boundaries without a DB. Percentile cutoffs use integer cross-multiplication
rather than float division so the boundaries are exact.

Small communities: below ~10 users with at least one funny vote received, the
tightest band (``Pun Sommelier``, top 10%) is unreachable for anyone who is not
rank 1 — ``1 / N <= 0.10`` needs ``N >= 10``. That is inherent to percentile
bucketing, not a bug.
"""

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.utils.functional import Promise

# Worst -> best. The top name goes to whoever has nobody above them
# (``higher_users == 0``); a user with no funny votes received always takes the
# floor name, even when that leaves them at rank 1 (a site with zero votes puts
# everyone at rank 1, and nobody has earned the top name there).
_FLOOR = _("Junior Quizmaster")
_TOP = _("Godfather of Puns")

# Bands for everyone in between, keyed by how large a share of the ranked users
# (those with at least one funny vote received) sit strictly above this user.
# Each entry is ``(share_numerator, share_denominator, name)`` and its name wins
# while ``higher_users * share_denominator`` is at most
# ``ranked_population * share_numerator`` — i.e. the share is within the cutoff.
_PERCENTILE_BANDS: tuple[tuple[int, int, Promise], ...] = (
    (10, 100, _("Pun Sommelier")),
    (35, 100, _("Laughter Carousel Chairman")),
    (70, 100, _("Wedding Uncle")),
)


def comedy_rank_name(
    *,
    funny_score: int,
    higher_users: int,
    ranked_population: int,
) -> Promise:
    """Return the Comedy Rank name for a profile.

    ``funny_score`` is the user's own count of funny votes received;
    ``higher_users`` the number of users with a strictly higher ``funny_score``
    (so ``higher_users == 0`` is exactly the displayed rank 1 under dense
    ranking); ``ranked_population`` the number of users with any funny vote
    received.
    """
    if funny_score <= 0 or ranked_population <= 0:
        return _FLOOR
    if higher_users == 0:
        return _TOP
    for numerator, denominator, name in _PERCENTILE_BANDS:
        if higher_users * denominator <= ranked_population * numerator:
            return name
    return _FLOOR
