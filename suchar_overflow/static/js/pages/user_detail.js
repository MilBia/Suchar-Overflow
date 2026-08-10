/* User detail page: activity (dryness) and reception charts */

document.addEventListener('DOMContentLoaded', function() {
    // Activity Chart
    const ctxActivity = document.getElementById('userActivityChart');
    if (ctxActivity) {
        const labels = JSON.parse(document.getElementById('activity-labels-data').textContent);
        const data = JSON.parse(document.getElementById('activity-values-data').textContent);

        new Chart(ctxActivity.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Suchary',
                    data: data,
                    backgroundColor: '#3b82f6',
                    borderRadius: 2
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
                            display: false
                        },
                        grid: {
                            display: false
                        }
                    },
                    x: {
                        display: false
                    }
                }
            }
        });
    }

    // Reception Chart
    const ctxReception = document.getElementById('userReceptionChart');
    if (ctxReception) {
        const data = JSON.parse(document.getElementById('reception-data-data').textContent); // [funny, dry]

        new Chart(ctxReception.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: [ctxReception.dataset.funnyLabel, ctxReception.dataset.dryLabel],
                datasets: [{
                    data: data,
                    backgroundColor: ['#E58E26', '#0ea5e9'], // Orange (Funny), Blue (Dry)
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            boxWidth: 10
                        }
                    }
                }
            }
        });
    }
});
