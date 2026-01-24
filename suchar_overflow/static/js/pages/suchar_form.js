/* Suchar Form Live Preview Logic */

document.addEventListener('DOMContentLoaded', () => {
    const textInput = document.getElementById('id_text');
    const tagsInput = document.getElementById('id_tags_input');
    const previewText = document.getElementById('previewText');
    const previewTags = document.getElementById('previewTags');

    if (!textInput || !previewText) return;

    // Text Preview
    textInput.addEventListener('input', (e) => {
        const val = e.target.value;
        if (val.trim()) {
            previewText.textContent = val;
            previewText.classList.remove('text-muted', 'fst-italic');
        } else {
            previewText.textContent = 'Tutaj pojawi się treść Twojego suchara...';
            previewText.classList.add('text-muted', 'fst-italic');
        }
    });

    if (!tagsInput || !previewTags) return;

    // Tags Preview
    tagsInput.addEventListener('input', (e) => {
        const val = e.target.value;
        previewTags.innerHTML = ''; // Clear

        if (val.trim()) {
            const tags = val.split(/[ ,]+/).filter(tag => tag.trim() !== '');
            tags.forEach(tag => {
                const badge = document.createElement('span');
                badge.className = 'badge text-secondary border me-1 bg-light';
                badge.textContent = '#' + tag.trim();
                previewTags.appendChild(badge);
            });
        }
    });
});
