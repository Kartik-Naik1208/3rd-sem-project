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
});
