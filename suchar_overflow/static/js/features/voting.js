/* AJAX Voting Logic */

// Toggle the pure-CSS `.loading` spinner on a voting-controls container and,
// alongside it, a visually-hidden live-region string so screen readers get a
// spoken "busy" cue the animation alone can't give (issue #298).
function setVotingBusy(container, busy) {
    container.classList.toggle('loading', busy);
    let status = container.querySelector('.vote-status');
    if (busy) {
        if (!status) {
            status = document.createElement('span');
            status.className = 'vote-status visually-hidden';
            status.setAttribute('role', 'status');
            status.textContent = 'Zliczam głos…';
            container.appendChild(status);
        }
    } else if (status) {
        status.remove();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // One delegated listener instead of one per `.btn-vote` — resilient to lists
    // that grow or re-render without re-binding. No stable list container exists
    // (cards sit directly in the column), so delegate on `document`.
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.btn-vote');
        if (!btn) return;

        e.preventDefault();

        if (btn.dataset.anonymous === 'true') {
            window.location.href = '/accounts/login/';
            return;
        }

        const sucharId = btn.dataset.sucharId;
        const voteType = btn.dataset.voteType;
        const container = btn.closest('.voting-controls');

        if (!sucharId || !voteType || !container) return;

        const funnyBtn = container.querySelector('.btn-vote[data-vote-type="funny"]');
        const dryBtn = container.querySelector('.btn-vote[data-vote-type="dry"]');

        // Snapshot for rollback on error
        const snapshot = {
            funnyActive: funnyBtn.classList.contains('active'),
            dryActive: dryBtn.classList.contains('active'),
            funnyCount: parseInt(funnyBtn.querySelector('.vote-count').textContent, 10),
            dryCount: parseInt(dryBtn.querySelector('.vote-count').textContent, 10),
        };

        // Optimistic update — apply immediately before the request
        const wasActive = btn.classList.contains('active');
        btn.classList.toggle('active', !wasActive);
        btn.setAttribute('aria-pressed', String(!wasActive));
        const countSpan = btn.querySelector('.vote-count');
        countSpan.textContent = wasActive
            ? Math.max(0, snapshot[`${voteType}Count`] - 1)
            : snapshot[`${voteType}Count`] + 1;

        setVotingBusy(container, true);

        try {
            const csrftoken = getCsrfToken();
            if (!csrftoken) {
                console.error('CSRF token not found');
                setVotingBusy(container, false);
                return;
            }

            const response = await fetch(`/api/suchary/${sucharId}/vote`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                },
                body: JSON.stringify({ vote_type: voteType }),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();

            // Reconcile with authoritative server counts
            funnyBtn.querySelector('.vote-count').textContent = data.funny_count;
            dryBtn.querySelector('.vote-count').textContent = data.dry_count;
            funnyBtn.classList.toggle('active', data.user_is_funny);
            funnyBtn.setAttribute('aria-pressed', String(data.user_is_funny));
            dryBtn.classList.toggle('active', data.user_is_dry);
            dryBtn.setAttribute('aria-pressed', String(data.user_is_dry));

            // #295: this vote may have latched the "overdried" flag (#294) —
            // add the craquelure marker in place so the card cracks without a
            // reload. The latch is one-way, so we only ever add it here.
            if (data.is_overdried) {
                const card = container.closest('.card.suchar-card');
                if (card && !card.hasAttribute('data-overdried')) {
                    card.setAttribute('data-overdried', '');
                }
            }

        } catch (error) {
            console.error('Vote failed:', error);

            // Rollback optimistic update
            funnyBtn.classList.toggle('active', snapshot.funnyActive);
            funnyBtn.setAttribute('aria-pressed', String(snapshot.funnyActive));
            dryBtn.classList.toggle('active', snapshot.dryActive);
            dryBtn.setAttribute('aria-pressed', String(snapshot.dryActive));
            funnyBtn.querySelector('.vote-count').textContent = snapshot.funnyCount;
            dryBtn.querySelector('.vote-count').textContent = snapshot.dryCount;

            if (window.showToast) {
                window.showToast('Głos ugrzązł w suszy. Spróbuj ponownie.', 'Błąd', 'error');
            }
        } finally {
            setVotingBusy(container, false);
        }
    });
});

// Test-only handle for the busy-state helper — inert in the browser (`module`
// is undefined there) and preserved by rjsmin. See CLAUDE.md "JS tests
// (Vitest)"; not dead code.
if (typeof module !== "undefined" && module.exports) {
    module.exports = { setVotingBusy };
}
