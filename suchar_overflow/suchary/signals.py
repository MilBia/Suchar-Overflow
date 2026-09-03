"""Signals emitted by the suchary app.

``vote_changed`` fires from the vote endpoint whenever an existing vote is
toggled or removed — the paths where ``post_save`` either carries a stale
flag state (``created=True`` runs before the follow-up ``save()``) or does
not fire at all (a toggle ``save()`` with ``created=False``, or a
``delete()``). It carries the *final* state and fires exactly once per
request. The achievements app listens for it; suchary never imports
achievements, keeping the app dependency one-way.

``suchar_edited`` fires from ``SucharUpdateView`` after every successful
edit-window save, once the ``edit_count`` bump is persisted. The
achievements app re-runs the engine for the author (the 'Recydywa'
achievement). Same one-way dependency as ``vote_changed``.
"""

from django.dispatch import Signal

# kwargs: voter (User), author (User), suchar (Suchar)
vote_changed = Signal()

# kwargs: author (User), suchar (Suchar)
suchar_edited = Signal()
