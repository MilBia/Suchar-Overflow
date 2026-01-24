/* AJAX Voting Logic */

document.addEventListener('DOMContentLoaded', () => {
    const voteButtons = document.querySelectorAll('.btn-vote');

    voteButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();

            // Get Data
            const sucharId = btn.dataset.sucharId;
            const value = parseInt(btn.dataset.value);
            const container = btn.closest('.d-flex.align-items-center.justify-content-between');
            if (!sucharId || !container) return;

            // Optimistic UI Update (Optional, but let's wait for API for accuracy first)
            // Or better: disable buttons
            btn.disabled = true;

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
                    body: JSON.stringify({ value: value })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                // Update Score
                const scoreEl = container.querySelector('.vote-score');
                // Extract just the icon if strictly needed, or just replace text node
                // Assuming structure: <svg>...</svg> SCORE
                if (scoreEl) {
                    // split to keep svg, or assume svg is first child
                    const svg = scoreEl.querySelector('svg');
                    scoreEl.innerHTML = '';
                    if (svg) scoreEl.appendChild(svg);
                    scoreEl.append(` ${data.new_score}`);
                }

                // Update Button States
                const upBtn = container.querySelector('.btn-vote[data-value="1"]');
                const downBtn = container.querySelector('.btn-vote[data-value="-1"]');

                // Reset both
                if (upBtn) upBtn.classList.remove('active');
                if (downBtn) downBtn.classList.remove('active');

                // Set new active
                if (data.user_vote === 1 && upBtn) upBtn.classList.add('active');
                if (data.user_vote === -1 && downBtn) downBtn.classList.add('active');

            } catch (error) {
                console.error("Vote failed:", error);
                // Create a toast or alert?
                alert("Nie udało się zagłosować. Spróbuj ponownie.");
            } finally {
                btn.disabled = false;
            }
        });
    });
});
