/* AJAX Voting Logic */

document.addEventListener('DOMContentLoaded', () => {
    const voteButtons = document.querySelectorAll('.btn-vote');

    voteButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
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

            container.classList.add('loading');

            try {
                const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                if (!csrftoken) {
                    console.error('CSRF token not found');
                    container.classList.remove('loading');
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
                    window.showToast('Nie udało się zagłosować. Spróbuj ponownie.', 'Błąd', 'error');
                }
            } finally {
                container.classList.remove('loading');
            }
        });
    });
});
