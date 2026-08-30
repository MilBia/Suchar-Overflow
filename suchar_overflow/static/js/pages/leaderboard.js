/* Leaderboard: activity chart + sliding tab/timeframe indicators */

document.addEventListener('DOMContentLoaded', function() {
    const activityCanvas = document.getElementById('activityChart');
    if (!activityCanvas) return;

    // Everything below is scoped to this handler rather than the (shared,
    // page-global) script scope a classic `defer` script otherwise leaks into:
    // a second `const debounce`/`RESIZE_DEBOUNCE_MS` in any other script on the
    // same page would be a whole-script SyntaxError (issue #248). Matches
    // pages/suchar_form.js, which likewise keeps its `debounce` local.

    // Coalesce rapid-fire events into a single trailing call. `resize` fires
    // dozens of times per second while the user drags the window, and every
    // repositioning pass below forces a synchronous reflow via
    // getBoundingClientRect() — so we only reposition once the drag settles.
    // Same pattern as the tag autocomplete in pages/suchar_form.js.
    function debounce(func, wait) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    }

    const RESIZE_DEBOUNCE_MS = 150;

    // Shared by the timeframe and tab sliding indicators below: positions
    // `slider` over `btn`, relative to `container`, optionally without a
    // transition (used for the initial, unanimated placement).
    function positionSliderOverButton(slider, container, btn, animate) {
        if (!animate) slider.style.transition = 'none';
        const containerRect = container.getBoundingClientRect();
        const btnRect = btn.getBoundingClientRect();
        slider.style.left = (btnRect.left - containerRect.left) + 'px';
        slider.style.top = (btnRect.top - containerRect.top) + 'px';
        slider.style.width = btnRect.width + 'px';
        slider.style.height = btnRect.height + 'px';
        if (!animate) requestAnimationFrame(() => {
            slider.style.transition = '';
        });
    }

    // Repositioning callbacks collected by the blocks below, all run by the
    // single debounced `resize` listener registered at the end of setup.
    const resizeHandlers = [];

    const datasetsEl = document.getElementById('chart-datasets-data');
    const datasets = JSON.parse(datasetsEl.textContent);
    const newJokesLabel = activityCanvas.dataset.newJokesLabel;
    let activeTimeframe = '30';

    const chart = new Chart(activityCanvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: datasets[activeTimeframe].labels,
            datasets: [{
                label: newJokesLabel,
                data: datasets[activeTimeframe].values,
                borderColor: '#3b82f6', // Primary Blue
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4,
                fill: true,
                borderWidth: 2,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    },
                    border: {
                        dash: [2, 4]
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });

    // Sliding timeframe selector indicator
    const timeframeSelector = document.querySelector('.chart-timeframe-selector');
    if (timeframeSelector) {
        const slider = document.createElement('span');
        slider.className = 'chart-timeframe-slider';
        slider.setAttribute('aria-hidden', 'true');
        timeframeSelector.appendChild(slider);

        const initialActive = timeframeSelector.querySelector('button.active');
        if (initialActive) {
            setTimeout(() => positionSliderOverButton(slider, timeframeSelector, initialActive, false), 50);
        }

        // Bind timeframe buttons
        timeframeSelector.querySelectorAll('button').forEach(button => {
            button.addEventListener('click', function() {
                const timeframe = this.getAttribute('data-timeframe');

                timeframeSelector.querySelectorAll('button').forEach(btn => {
                    btn.classList.remove('active');
                });
                this.classList.add('active');

                chart.data.labels = datasets[timeframe].labels;
                chart.data.datasets[0].data = datasets[timeframe].values;
                chart.update();

                positionSliderOverButton(slider, timeframeSelector, this, true);
            });
        });

        // Reposition on window resize
        resizeHandlers.push(() => {
            const activeBtn = timeframeSelector.querySelector('button.active');
            if (activeBtn) {
                positionSliderOverButton(slider, timeframeSelector, activeBtn, false);
            }
        });
    }

    // Sliding tab indicator
    const tabList = document.getElementById('leaderboardTabs');
    if (tabList) {
        const tabColorMap = {
            'overall-tab': 'overall',
            'funny-tab': 'funny',
            'dry-tab': 'dry'
        };
        const slider = document.createElement('span');
        slider.className = 'leaderboard-tab-slider';
        slider.setAttribute('aria-hidden', 'true');
        tabList.appendChild(slider);

        function positionTabSlider(btn, animate) {
            positionSliderOverButton(slider, tabList, btn, animate);
            tabList.dataset.activeTab = tabColorMap[btn.id] || 'overall';
        }

        const initialActive = tabList.querySelector('.nav-link.active');
        if (initialActive) {
            setTimeout(() => positionTabSlider(initialActive, false), 50);
        }

        tabList.querySelectorAll('[data-toggle="tab"]').forEach(btn => {
            btn.addEventListener('click', () => positionTabSlider(btn, true));
        });

        // Reposition tabs on window resize
        resizeHandlers.push(() => {
            const activeBtn = tabList.querySelector('.nav-link.active');
            if (activeBtn) {
                positionTabSlider(activeBtn, false);
            }
        });
    }

    // One shared, debounced listener for every indicator registered above.
    if (resizeHandlers.length > 0) {
        window.addEventListener('resize', debounce(() => {
            resizeHandlers.forEach(reposition => reposition());
        }, RESIZE_DEBOUNCE_MS));
    }
});
