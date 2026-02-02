/* Suchar Form Live Preview & Logic */

document.addEventListener('DOMContentLoaded', () => {
    // ---- namespace for form logic ----
    const SucharForm = {
        elements: {
            textInput: document.getElementById('id_text'),
            tagsInput: document.getElementById('id_tags_input'),
            tagsDropdown: document.getElementById('tags-dropdown'), // New Wrapper
            previewText: document.getElementById('previewText'),
            previewTags: document.getElementById('previewTags'),
            scheduleCheck: document.getElementById('scheduleCheck'),
            scheduleContainer: document.getElementById('scheduleContainer'),
            publishedAtInput: document.getElementById('id_published_at'),
            suggestionsBox: document.getElementById('tags-suggestions'),
            form: document.querySelector('form'),
            dateError: document.getElementById('dateError')
        },

        init() {
            this.setupTextPreview();
            this.setupScheduling();
            this.setupTags();
            this.setupValidation();
        },

        setupTextPreview() {
            const { textInput, previewText } = this.elements;
            if (!textInput || !previewText) return;

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
        },

        setupScheduling() {
            const { scheduleCheck, scheduleContainer, publishedAtInput } = this.elements;
            if (!scheduleCheck || !scheduleContainer || !publishedAtInput) return;

            // Init State
            const currentVal = publishedAtInput.value;
            const now = new Date();
            const inputDate = currentVal ? new Date(currentVal) : null;

            if (inputDate && inputDate > new Date(now.getTime() + 5 * 60000)) {
                scheduleCheck.checked = true;
                scheduleContainer.classList.remove('d-none');
            }

            // Initialize Flatpickr
            const fp = flatpickr(publishedAtInput, {
                enableTime: true,
                dateFormat: "Y-m-d H:i",
                minDate: "today",
                time_24hr: true,
                disableMobile: true, // Force custom UI
                onChange: function (selectedDates, dateStr, instance) {
                    // Optional: Validate on change
                }
            });

            // Handle Schedule Toggle
            scheduleCheck.addEventListener('change', (e) => {
                if (e.target.checked) {
                    scheduleContainer.classList.remove('d-none');
                    // Small delay to allow transition, then open calendar if empty
                    if (!publishedAtInput.value) {
                        setTimeout(() => fp.open(), 100);
                    }
                    // Re-enable input logic (Flatpickr handles the actual input)
                    publishedAtInput.disabled = false;
                } else {
                    scheduleContainer.classList.add('d-none');
                    fp.clear(); // Clear value via Flatpickr API
                    publishedAtInput.disabled = true;
                }
            });

            // Initial state
            if (!scheduleCheck.checked) {
                publishedAtInput.disabled = true;
            }
        },

        setupTags() {
            const { tagsInput, tagsDropdown, previewTags, suggestionsBox } = this.elements;
            if (!tagsInput || !previewTags || !suggestionsBox) return;

            const debounce = (func, wait) => {
                let timeout;
                return (...args) => {
                    clearTimeout(timeout);
                    timeout = setTimeout(() => func.apply(this, args), wait);
                };
            };

            const fetchTags = async (query) => {
                try {
                    const response = await fetch(`/api/suchary/tags?q=${encodeURIComponent(query)}`);
                    if (response.ok) return await response.json();
                } catch (e) {
                    console.error('Failed to fetch tags', e);
                }
                return [];
            };

            const insertTag = (tagName) => {
                const val = tagsInput.value;
                const cursorPosition = tagsInput.selectionStart;
                const textBeforeCursor = val.slice(0, cursorPosition);
                const lastCommaIndex = textBeforeCursor.lastIndexOf(',');

                const prefix = textBeforeCursor.slice(0, lastCommaIndex + 1);
                const suffix = val.slice(cursorPosition);

                const newText = (prefix ? prefix + ' ' : '') + tagName + ', ' + suffix;
                tagsInput.value = newText;

                // Close dropdown
                if (tagsDropdown) tagsDropdown.classList.remove('show');

                tagsInput.focus();
                tagsInput.dispatchEvent(new Event('input'));
            };

            const debouncedSearch = debounce(async (term) => {
                const tags = await fetchTags(term);
                if (tags && tags.length > 0) {
                    suggestionsBox.innerHTML = '';
                    tags.forEach(tag => {
                        const item = document.createElement('div');
                        // Use project standard class
                        item.className = 'dropdown-item';
                        item.textContent = tag.name;
                        item.addEventListener('click', () => {
                            insertTag(tag.name);
                        });
                        suggestionsBox.appendChild(item);
                    });

                    // Show dropdown logic
                    if (tagsDropdown) tagsDropdown.classList.add('show');
                    else suggestionsBox.style.display = 'block'; // Fallback

                } else {
                    if (tagsDropdown) tagsDropdown.classList.remove('show');
                    else suggestionsBox.style.display = 'none';
                }
            }, 300);

            tagsInput.addEventListener('input', (e) => {
                const val = e.target.value;

                // Update Preview
                previewTags.innerHTML = '';
                if (val.trim()) {
                    const tags = val.split(/[ ,]+/).filter(tag => tag.trim() !== '');
                    tags.forEach(tag => {
                        const badge = document.createElement('span');
                        badge.className = 'badge text-secondary border me-1 bg-light';
                        badge.textContent = '#' + tag.trim();
                        previewTags.appendChild(badge);
                    });
                }

                // Autocomplete
                const cursorPosition = e.target.selectionStart;
                const textBeforeCursor = val.slice(0, cursorPosition);
                const lastCommaIndex = textBeforeCursor.lastIndexOf(',');
                const currentTerm = textBeforeCursor.slice(lastCommaIndex + 1).trim();

                if (currentTerm.length > 0) { // Changed to > 0 to allow single char search if supported, otherwise > 1
                    if (currentTerm.length > 1) debouncedSearch(currentTerm); // Stick to > 1 for perf
                    else {
                        if (tagsDropdown) tagsDropdown.classList.remove('show');
                    }
                } else {
                    if (tagsDropdown) tagsDropdown.classList.remove('show');
                }
            });

            // Close on outside click
            document.addEventListener('click', (e) => {
                if (e.target !== tagsInput && !suggestionsBox.contains(e.target)) {
                    if (tagsDropdown) tagsDropdown.classList.remove('show');
                }
            });
        },

        setupValidation() {
            const { form, dateError, scheduleCheck, publishedAtInput } = this.elements;
            if (!form) return;

            form.addEventListener('submit', (e) => {
                if (scheduleCheck && scheduleCheck.checked && publishedAtInput.value) {
                    const inputDate = new Date(publishedAtInput.value);
                    const now = new Date();

                    if (inputDate <= now) {
                        e.preventDefault();
                        // ... validation logic ...
                        if (dateError) {
                            // Assuming validation feedback is handled elsewhere or simple text
                            dateError.classList.remove('d-none');
                            dateError.classList.add('d-block');
                            dateError.textContent = "Data publikacji nie może być w przeszłości.";
                        }
                        publishedAtInput.classList.add('is-invalid');
                    }
                }
            });
            // ... cleanup ...
            if (publishedAtInput) {
                publishedAtInput.addEventListener('input', () => {
                    if (dateError) {
                        dateError.classList.add('d-none');
                        dateError.classList.remove('d-block');
                    }
                    publishedAtInput.classList.remove('is-invalid');
                });
            }
        }
    };

    SucharForm.init();
});
