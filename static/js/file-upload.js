/**
 * File drop zone + hidden input. Calls onAfterChange after any change/reset.
 */
export function setupFileUpload(fileInput, fileDisplay, onAfterChange) {
    const fileIcon = fileDisplay.querySelector('.file-icon');
    const fileText = fileDisplay.querySelector('.file-text');

    function resetFileInput() {
        fileDisplay.classList.remove('has-file');
        fileText.classList.remove('has-file');
        fileText.textContent = 'Click to browse or drag SRT, ASS, SSA, or SUB file here';
        fileIcon.textContent = '📁';
        fileInput.value = '';
        onAfterChange();
    }

    fileInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (file) {
            fileDisplay.classList.add('has-file');
            fileText.classList.add('has-file');
            fileText.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
            fileIcon.textContent = '✅';
        } else {
            resetFileInput();
        }
        onAfterChange();
    });

    fileDisplay.addEventListener('dragover', function (e) {
        e.preventDefault();
        fileDisplay.style.borderColor = '#764ba2';
        fileDisplay.style.background = '#f0f2ff';
    });

    fileDisplay.addEventListener('dragleave', function (e) {
        e.preventDefault();
        fileDisplay.style.borderColor = '#667eea';
        fileDisplay.style.background = '#f8f9ff';
    });

    fileDisplay.addEventListener('drop', function (e) {
        e.preventDefault();
        const files = e.dataTransfer.files;
        if (files.length > 0 && /\.(srt|ass|ssa|sub)$/i.test(files[0].name)) {
            fileInput.files = files;
            fileInput.dispatchEvent(new Event('change'));
        }
        fileDisplay.style.borderColor = '#667eea';
        fileDisplay.style.background = '#f8f9ff';
    });

    return { resetFileInput };
}
