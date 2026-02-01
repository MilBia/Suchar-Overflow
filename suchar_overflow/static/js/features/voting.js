/* AJAX Voting Logic */

document.addEventListener('DOMContentLoaded', () => {
    const voteButtons = document.querySelectorAll('.btn-vote');

    voteButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();

            // Get Data
            const sucharId = btn.dataset.sucharId;
            const voteType = btn.dataset.voteType;
            const container = btn.closest('.voting-controls');

            if (!sucharId || !voteType || !container) return;

            // Disable buttons during request
            const allBtns = container.querySelectorAll('.btn-vote');
            allBtns.forEach(b => b.disabled = true);

            try {
                // Determine CSRF Token
                const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                if (!csrftoken) {
                    console.error("CSRF Token found nowhere!");
                    return;
                }

                // Call API
                const response = await fetch(`/api/suchary/${sucharId}/vote`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken
                    },
                    body: JSON.stringify({ vote_type: voteType })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                // Find buttons
                const funnyBtn = container.querySelector('.btn-vote[data-vote-type="funny"]');
                const dryBtn = container.querySelector('.btn-vote[data-vote-type="dry"]');

                // Update Counts
                if (funnyBtn) {
                    const countSpan = funnyBtn.querySelector('.vote-count');
                    if (countSpan) countSpan.textContent = data.funny_count;
                }
                if (dryBtn) {
                    const countSpan = dryBtn.querySelector('.vote-count');
                    if (countSpan) countSpan.textContent = data.dry_count;
                }

                // Update States
                if (funnyBtn) {
                    if (data.user_is_funny) funnyBtn.classList.add('active');
                    else funnyBtn.classList.remove('active');
                }
                if (dryBtn) {
                    if (data.user_is_dry) dryBtn.classList.add('active');
                    else dryBtn.classList.remove('active');
                }

            } catch (error) {
                console.error("Vote failed:", error);
                alert("Nie udało się zagłosować. Spróbuj ponownie.");
            } finally {
                allBtns.forEach(b => b.disabled = false);
            }
        });
    });
});
