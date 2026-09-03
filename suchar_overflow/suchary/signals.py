"""Signals emitted by the suchary app.

``vote_changed`` fires from the vote endpoint whenever an existing vote is
toggled or removed — the paths where ``post_save`` either carries a stale
flag state (``created=True`` runs before the follow-up ``save()``) or does
not fire at all (a toggle ``save()`` with ``created=False``, or a
``delete()``). It carries the *final* state and fires exactly once per
request. The achievements app listens for it; suchary never imports
achievements, keeping the app dependency one-way.
"""

from django.dispatch import Signal

# kwargs: voter (User), author (User), suchar (Suchar)
vote_changed = Signal()
