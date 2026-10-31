/**
 * Food Ingredient Safety Scanner Front-end Interaction Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Drag & Drop Upload Zone Handlers
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('labelImageInput');
    const previewContainer = document.getElementById('previewContainer');
    const imagePreview = document.getElementById('imagePreview');
    const fileNameDisplay = document.getElementById('fileName');

    if (dropZone && fileInput) {
        dropZone.addEventListener('click', () => fileInput.click());

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            });
        });

        dropZone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                handleFileSelection(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleFileSelection(e.target.files[0]);
            }
        });
    }

    function handleFileSelection(file) {
        if (!file.type.startsWith('image/')) {
            alert('Please select an image file (PNG, JPG, WEBP).');
            return;
        }

        if (fileNameDisplay) {
            fileNameDisplay.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            if (imagePreview) {
                imagePreview.src = e.target.result;
            }
            if (previewContainer) {
                previewContainer.classList.remove('d-none');
            }
        };
        reader.readAsDataURL(file);
    }

    // 2. Prefill Sample Text for Quick Testing
    const fillSampleBtn = document.getElementById('fillSampleBtn');
    const rawTextArea = document.getElementById('raw_text');
    const productNameInput = document.getElementById('product_name');
    const validationAlert = document.getElementById('validationAlert');

    if (fillSampleBtn && rawTextArea) {
        fillSampleBtn.addEventListener('click', () => {
            rawTextArea.value = "Wheat flour, sugar, palm oil, salt, sodium benzoate (E211), tartrazine, citric acid";
            if (productNameInput && !productNameInput.value) {
                productNameInput.value = "Sample Food Product";
            }
            if (validationAlert) {
                validationAlert.classList.add('d-none');
            }
            rawTextArea.focus();
        });
    }

    // 3. Form Reset Handler
    const clearFormBtn = document.getElementById('clearFormBtn');
    if (clearFormBtn) {
        clearFormBtn.addEventListener('click', () => {
            if (previewContainer) previewContainer.classList.add('d-none');
            if (fileNameDisplay) fileNameDisplay.textContent = '';
            if (fileInput) fileInput.value = '';
            if (validationAlert) validationAlert.classList.add('d-none');
        });
    }

    // 4. Form Submit Loading Spinner & Duplicate Submission Prevention
    const scanForm = document.getElementById('scanForm');
    const scanSubmitBtn = document.getElementById('scanSubmitBtn');
    const submitBtnText = document.getElementById('submitBtnText');
    const submitIcon = document.getElementById('submitIcon');
    const loadingIndicator = document.getElementById('loadingIndicator');

    if (scanForm && scanSubmitBtn) {
        scanForm.addEventListener('submit', (e) => {
            const hasImage = fileInput && fileInput.files && fileInput.files.length > 0;
            const hasText = rawTextArea && rawTextArea.value.trim().length > 0;

            if (!hasImage && !hasText) {
                e.preventDefault();
                if (validationAlert) {
                    validationAlert.classList.remove('d-none');
                    validationAlert.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                return false;
            }

            // Hide validation alert if shown
            if (validationAlert) {
                validationAlert.classList.add('d-none');
            }

            // Immediately show the Bootstrap 5 loading spinner and message
            if (loadingIndicator) {
                loadingIndicator.classList.remove('d-none');
            }

            // Prevent duplicate clicks and update button label
            scanSubmitBtn.disabled = true;
            if (submitIcon) {
                submitIcon.className = 'spinner-border spinner-border-sm me-1';
            }
            if (submitBtnText) {
                submitBtnText.textContent = 'Scanning...';
            }

            // Programmatically submit the form since disabling the button might halt native submit in some browsers
            scanForm.submit();
            return true;
        });
    }

    // 5. Password Visibility Toggle Handlers (Login & Register Pages)
    const passwordToggleButtons = document.querySelectorAll('.password-toggle-btn');
    passwordToggleButtons.forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = btn.getAttribute('data-target');
            let targetInput = targetId ? document.getElementById(targetId) : null;
            if (!targetInput) {
                const group = btn.closest('.input-group');
                if (group) {
                    targetInput = group.querySelector('input');
                }
            }

            if (!targetInput) return;

            const isCurrentlyPassword = targetInput.type === 'password';
            targetInput.type = isCurrentlyPassword ? 'text' : 'password';

            const icon = btn.querySelector('i');
            if (icon) {
                if (isCurrentlyPassword) {
                    icon.classList.remove('bi-eye');
                    icon.classList.add('bi-eye-slash');
                } else {
                    icon.classList.remove('bi-eye-slash');
                    icon.classList.add('bi-eye');
                }
            }

            const isConfirm = targetInput.id === 'confirm_password';
            const actionWord = isCurrentlyPassword ? 'Hide' : 'Show';
            const fieldName = isConfirm ? 'confirm password' : 'password';
            const labelText = `${actionWord} ${fieldName}`;

            btn.setAttribute('aria-label', labelText);
            btn.setAttribute('title', labelText);
            btn.setAttribute('aria-pressed', isCurrentlyPassword ? 'true' : 'false');
        });
    });

    // 6. Live Search and Filter for "Ingredients Found in This Product"
    const ingredientSearchInput = document.getElementById('ingredientSearchInput');
    const ingredientRows = document.querySelectorAll('.ingredient-entry-item');
    const ingredientCountBadge = document.getElementById('ingredientSearchCount');
    const noResultsAlert = document.getElementById('noIngredientResults');
    const filterPills = document.querySelectorAll('.ingredient-filter-pill');

    let currentFilterStatus = 'all';

    function applyIngredientFilter() {
        const query = ingredientSearchInput ? ingredientSearchInput.value.toLowerCase().trim() : '';
        let visibleCount = 0;

        ingredientRows.forEach((row) => {
            const rowText = (row.getAttribute('data-search-text') || row.textContent).toLowerCase();
            const rowStatus = (row.getAttribute('data-status-filter') || '').toLowerCase();

            const matchesQuery = !query || rowText.includes(query);
            let matchesStatus = (currentFilterStatus === 'all');
            if (!matchesStatus) {
                if (currentFilterStatus === 'no specific concern identified' || currentFilterStatus === 'safe') {
                    matchesStatus = (rowStatus === 'no specific concern identified' || rowStatus === 'safe');
                } else if (currentFilterStatus === 'caution') {
                    matchesStatus = (rowStatus === 'caution' || rowStatus === 'use caution');
                } else if (currentFilterStatus === 'potential concern' || currentFilterStatus === 'concern') {
                    matchesStatus = (rowStatus === 'potential concern' || rowStatus === 'harmful' || rowStatus === 'concern');
                } else if (currentFilterStatus === 'insufficient information' || currentFilterStatus === 'unverified') {
                    matchesStatus = (rowStatus === 'insufficient information' || rowStatus === 'unverified' || rowStatus === 'ocr issue');
                } else {
                    matchesStatus = (rowStatus === currentFilterStatus);
                }
            }

            if (matchesQuery && matchesStatus) {
                row.classList.remove('d-none');
                visibleCount++;
            } else {
                row.classList.add('d-none');
            }
        });

        if (ingredientCountBadge) {
            ingredientCountBadge.textContent = visibleCount;
        }
        if (noResultsAlert) {
            if (visibleCount === 0) {
                noResultsAlert.classList.remove('d-none');
            } else {
                noResultsAlert.classList.add('d-none');
            }
        }
    }

    if (ingredientSearchInput) {
        ingredientSearchInput.addEventListener('input', applyIngredientFilter);
    }

    filterPills.forEach((pill) => {
        pill.addEventListener('click', (e) => {
            e.preventDefault();
            filterPills.forEach((p) => {
                p.classList.remove('active');
                p.classList.remove('btn-dark');
                p.classList.add('btn-outline-secondary');
            });

            pill.classList.remove('btn-outline-secondary');
            pill.classList.add('active', 'btn-dark');

            currentFilterStatus = pill.getAttribute('data-filter') || 'all';
            applyIngredientFilter();
        });
    });
});
