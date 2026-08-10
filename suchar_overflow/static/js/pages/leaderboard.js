/* Leaderboard: activity chart + sliding tab/timeframe indicators */

document.addEventListener('DOMContentLoaded', function() {
    const activityCanvas = document.getElementById('activityChart');
    if (!activityCanvas) return;

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

        function positionTimeframeSlider(btn, animate) {
            if (!animate) slider.style.transition = 'none';
            const containerRect = timeframeSelector.getBoundingClientRect();
            const btnRect = btn.getBoundingClientRect();
            slider.style.left = (btnRect.left - containerRect.left) + 'px';
            slider.style.top = (btnRect.top - containerRect.top) + 'px';
            slider.style.width = btnRect.width + 'px';
            slider.style.height = btnRect.height + 'px';
            if (!animate) requestAnimationFrame(() => {
                slider.style.transition = '';
            });
        }

        const initialActive = timeframeSelector.querySelector('button.active');
        if (initialActive) {
            setTimeout(() => positionTimeframeSlider(initialActive, false), 50);
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

                positionTimeframeSlider(this, true);
            });
        });

        // Reposition on window resize
        window.addEventListener('resize', () => {
            const activeBtn = timeframeSelector.querySelector('button.active');
            if (activeBtn) {
                positionTimeframeSlider(activeBtn, false);
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

        function positionSlider(btn, animate) {
            if (!animate) slider.style.transition = 'none';
            const containerRect = tabList.getBoundingClientRect();
            const btnRect = btn.getBoundingClientRect();
            slider.style.left = (btnRect.left - containerRect.left) + 'px';
            slider.style.top = (btnRect.top - containerRect.top) + 'px';
            slider.style.width = btnRect.width + 'px';
            slider.style.height = btnRect.height + 'px';
            tabList.dataset.activeTab = tabColorMap[btn.id] || 'overall';
            if (!animate) requestAnimationFrame(() => {
                slider.style.transition = '';
            });
        }

        const initialActive = tabList.querySelector('.nav-link.active');
        if (initialActive) {
            setTimeout(() => positionSlider(initialActive, false), 50);
        }

        tabList.querySelectorAll('[data-toggle="tab"]').forEach(btn => {
            btn.addEventListener('click', () => positionSlider(btn, true));
        });

        // Reposition tabs on window resize
        window.addEventListener('resize', () => {
            const activeBtn = tabList.querySelector('.nav-link.active');
            if (activeBtn) {
                positionSlider(activeBtn, false);
            }
        });
    }
});
