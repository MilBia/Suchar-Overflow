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
            // Scope to the suchar form: a bare document.querySelector('form')
            // resolves to the navbar language-switcher form (base.html), so the
            // submit handler below — validation + loading spinner — was binding
            // to the wrong element and never firing on a real submit.
            form: document.querySelector('.suchar-form-wrapper form'),
            dateError: document.getElementById('dateError'),
            charCounter: document.getElementById('charCounter'),
            submitBtn: document.querySelector(
                '.suchar-form-wrapper button[type="submit"]',
            )
        },

        init() {
            this.setupTextPreview();
            this.setupScheduling();
            this.setupTags();
            this.setupCharCounter();
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
                    previewText.textContent = previewText.dataset.placeholder || '';
                    previewText.classList.add('text-muted', 'fst-italic');
                }
            });
        },

        setupCharCounter() {
            const { textInput, charCounter } = this.elements;
            if (!textInput || !charCounter) return;

            const MAX = 2000;
            const update = () => {
                const len = textInput.value.length;
                charCounter.textContent = `${len} / ${MAX}`;
                charCounter.classList.remove('is-warning', 'is-error');
                if (len >= MAX) {
                    charCounter.classList.add('is-error');
                } else if (len >= 1700) {  // noqa: PLR2004
                    charCounter.classList.add('is-warning');
                }
            };

            textInput.addEventListener('input', update);
            update();
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

            // Duplicated on purpose (a shared `const debounce` across the page's
            // classic scripts would be a bundle-wide SyntaxError — see
            // leaderboard.js). `func` is always the arrow fn passed below, so
            // there is no `this` to forward — call it plainly, like leaderboard.js.
            const debounce = (func, wait) => {
                let timeout;
                return (...args) => {
                    clearTimeout(timeout);
                    timeout = setTimeout(() => func(...args), wait);
                };
            };

            const fetchTags = async (query) => {
                try {
                    const url = tagsInput.dataset.tagsUrl;
                    const response = await fetch(`${url}?q=${encodeURIComponent(query)}`);
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
                // Drop a leading comma + surrounding whitespace from the
                // remainder so completing a middle slot ("foo, |, bar") yields
                // "foo, tag, bar", not "foo, tag, , bar". One optional comma
                // only — a greedy [,\s]* would swallow the user's empty slots.
                const suffix = val.slice(cursorPosition).replace(/^\s*,?\s*/, '');

                const head = (prefix ? prefix + ' ' : '') + tagName + ', ';
                tagsInput.value = head + suffix;

                // Close dropdown
                if (tagsDropdown) tagsDropdown.classList.remove('show');

                tagsInput.focus();
                // Park the caret right after the inserted tag, not at the end
                // of the field — filling a middle slot must not jump past the
                // trailing tags.
                tagsInput.setSelectionRange(head.length, head.length);
                tagsInput.dispatchEvent(new Event('input'));
            };

            const debouncedSearch = debounce(async (term) => {
                const tags = await fetchTags(term);
                if (tags && tags.length > 0) {
                    suggestionsBox.replaceChildren();
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
                previewTags.replaceChildren();
                if (val.trim()) {
                    const tags = val.split(/[ ,]+/).filter(tag => tag.replace(/^#+/, '').trim() !== '');
                    tags.forEach(tag => {
                        const badge = document.createElement('span');
                        badge.className = 'badge text-secondary border me-1 bg-light';
                        badge.textContent = '#' + tag.replace(/^#+/, '').trim();
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
            const { form, dateError, scheduleCheck, publishedAtInput, submitBtn } = this.elements;
            if (!form) return;

            form.addEventListener('submit', (e) => {
                if (scheduleCheck && scheduleCheck.checked && publishedAtInput.value) {
                    const inputDate = new Date(publishedAtInput.value);
                    const now = new Date();

                    if (inputDate <= now) {
                        e.preventDefault();
                        if (dateError) {
                            dateError.classList.remove('d-none');
                            dateError.classList.add('d-block');
                            dateError.textContent = dateError.dataset.errorText;
                        }
                        publishedAtInput.classList.add('is-invalid');
                        return;
                    }
                }

                if (submitBtn) {
                    submitBtn.classList.add('is-loading');
                    // The `.is-loading` spinner is pure CSS (button text goes
                    // transparent) — give assistive tech a spoken cue too (#298).
                    // The live region is appended *after* the button, not inside
                    // it: screen readers skip the subtree of a `disabled`
                    // control. Insert it empty first, then set the text, so the
                    // region is in the DOM before its content changes.
                    const status = document.createElement('span');
                    status.className = 'visually-hidden';
                    status.setAttribute('role', 'status');
                    submitBtn.insertAdjacentElement('afterend', status);
                    status.textContent =
                        submitBtn.dataset.loadingText || 'Publikuję suchar…';
                    submitBtn.disabled = true;
                }
            });

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
