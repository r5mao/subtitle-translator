/**
 * File drop zone + hidden input. Calls onAfterChange after any change/reset.
 */
export function setupFileUpload(
    fileInput: HTMLInputElement,
    fileDisplay: HTMLElement,
    onAfterChange: () => void,
): { resetFileInput: () => void } {
    const fileIconEl = fileDisplay.querySelector('.file-icon');
    const fileTextEl = fileDisplay.querySelector('.file-text');
    if (!fileIconEl || !fileTextEl) {
        throw new Error('setupFileUpload: missing .file-icon or .file-text');
    }
    const fileIcon = fileIconEl;
    const fileText = fileTextEl;

    function resetFileInput(): void {
        fileDisplay.classList.remove('has-file');
        fileText.classList.remove('has-file');
        fileText.textContent = 'Click to browse or drag SRT, ASS, SSA, or SUB file here';
        fileIcon.textContent = '📁';
        fileInput.value = '';
        onAfterChange();
    }

    fileInput.addEventListener('change', function (e: Event) {
        const target = e.target as HTMLInputElement;
        const file = target.files?.[0];
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

    fileDisplay.addEventListener('dragover', function (e: DragEvent) {
        e.preventDefault();
        fileDisplay.style.borderColor = '#764ba2';
        fileDisplay.style.background = '#f0f2ff';
    });

    fileDisplay.addEventListener('dragleave', function (e: DragEvent) {
        e.preventDefault();
        fileDisplay.style.borderColor = '#667eea';
        fileDisplay.style.background = '#f8f9ff';
    });

    fileDisplay.addEventListener('drop', function (e: DragEvent) {
        e.preventDefault();
        const files = e.dataTransfer?.files;
        if (files && files.length > 0 && /\.(srt|ass|ssa|sub)$/i.test(files[0].name)) {
            const inputWithFiles = fileInput as HTMLInputElement & { files: FileList };
            inputWithFiles.files = files;
            fileInput.dispatchEvent(new Event('change'));
        }
        fileDisplay.style.borderColor = '#667eea';
        fileDisplay.style.background = '#f8f9ff';
    });

    return { resetFileInput };
}
