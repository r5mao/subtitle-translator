// File input handling with visual feedback
const fileInput = document.getElementById('srtFile');
const fileDisplay = document.getElementById('fileDisplay');
const fileIcon = fileDisplay.querySelector('.file-icon');
const fileText = fileDisplay.querySelector('.file-text');

fileInput.addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        fileDisplay.classList.add('has-file');
        fileText.classList.add('has-file');
        fileText.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        fileIcon.textContent = '✅';
    } else {
        resetFileInput();
    }
});

function resetFileInput() {
    fileDisplay.classList.remove('has-file');
    fileText.classList.remove('has-file');
    fileText.textContent = 'Click to browse or drag SRT file here';
    fileIcon.textContent = '📁';
}

// Drag and drop functionality
fileDisplay.addEventListener('dragover', function(e) {
    e.preventDefault();
    fileDisplay.style.borderColor = '#764ba2';
    fileDisplay.style.background = '#f0f2ff';
});

fileDisplay.addEventListener('dragleave', function(e) {
    e.preventDefault();
    fileDisplay.style.borderColor = '#667eea';
    fileDisplay.style.background = '#f8f9ff';
});

fileDisplay.addEventListener('drop', function(e) {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (
        files.length > 0 &&
        /\.(srt|ass|ssa|sub)$/i.test(files[0].name)
    ) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change'));
    }
    fileDisplay.style.borderColor = '#667eea';
    fileDisplay.style.background = '#f8f9ff';
});

// Form submission and translation logic
document.getElementById('translationForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    const formData = new FormData(this);
    const translateBtn = document.getElementById('translateBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const btnText = document.getElementById('btnText');
    const errorMessage = document.getElementById('errorMessage');
    const downloadSection = document.getElementById('downloadSection');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const dualLanguage = document.getElementById('dualLanguage');

    // Reset UI state
    errorMessage.style.display = 'none';
    downloadSection.style.display = 'none';
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressPercent.style.display = 'block';
    progressPercent.textContent = '0%';

    // Show loading state
    translateBtn.disabled = true;
    loadingSpinner.style.display = 'inline-block';
    btnText.textContent = 'Translating...';

    try {
        const taskResponse = await fetch('http://localhost:5000/api/task');

        if (!taskResponse.ok) {
            const errorText = await taskResponse.text();
            throw new Error(errorText || 'Server error');
        }

        const taskJson = await taskResponse.json();
        const taskId = taskJson.taskId;
        formData.append('taskId', taskId);
        formData.set('dualLanguage', dualLanguage.checked ? 'true' : 'false');

        // Start listening for progress updates via SSE BEFORE starting the translation POST
        const evtSource = new EventSource(`http://localhost:5000/api/translate/progress/${taskId}`);
        const ssePromise = new Promise((resolve, reject) => {
            let completed = false;
            progressBar.style.display = 'block';
            progressFill.style.width = '0%';
            evtSource.onmessage = function(event) {
                let progress = parseInt(event.data);
                if (isNaN(progress)) progress = 0;
                progressFill.style.width = progress + '%';
                progressFill.setAttribute('aria-valuenow', progress);
                progressPercent.textContent = progress + '%';
                if (progress >= 100 && !completed) {
                    completed = true;
                    evtSource.close();
                    resolve();
                }
            };
            evtSource.onerror = function(err) {
                evtSource.close();
                // Proceed but indicate loss of live updates
                reject(new Error('Lost connection to progress server.'));
            };
        });

        // Kick off the translation POST concurrently (do not await yet)
        const translatePromise = (async () => {
            const response = await fetch('http://localhost:5000/api/translate', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || 'Server error');
            }
            const json = await response.json();
            if (!json.success || !json.downloadUrl) {
                throw new Error(json.error || 'Translation failed');
            }
            return json;
        })();

        // Wait for progress to reach 100% (SSE) while POST runs
        try {
            await ssePromise;
        } catch (sseErr) {
            // Show a warning but continue waiting for the translate response
            console.warn(sseErr?.message || sseErr);
        }

        // Now wait for the translate response and proceed
        const json = await translatePromise;
        const downloadUrl = json.downloadUrl;
        const translationDuration = json.translationDuration;
        const serverFilename = json.filename;
        console.log('Download URL:', downloadUrl);

        // Fetch the translated file content
        const srtResponse = await fetch('http://localhost:5000' + downloadUrl);
        if (!srtResponse.ok) {
            throw new Error('Failed to download translated subtitle file');
        }
        const translatedContent = await srtResponse.text();

        // Create download link with translated content
        const blob = new Blob([translatedContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const downloadBtn = document.getElementById('downloadBtn');
        downloadBtn.href = url;
        const originalFileName = formData.get('srtFile').name;
        const targetLang = formData.get('targetLanguage');
        // Prefer server-provided filename (respects dual mode and format)
        let newFileName = serverFilename;
        if (!newFileName) {
            // Fallback: build client-side, append _dual when enabled
            const dualSuffix = (typeof dualLanguage !== 'undefined' && dualLanguage?.checked) ? '_dual' : '';
            newFileName = originalFileName.replace(/\.(srt|ass|ssa|sub)$/i, `_GoogleTrans_${targetLang}${dualSuffix}.$1`);
            if (newFileName === originalFileName) {
                newFileName = originalFileName + `_GoogleTrans_${targetLang}${dualSuffix}`;
            }
        }
        downloadBtn.download = newFileName;

        // Show translation duration at the bottom
        const durationDiv = document.getElementById('translationDuration');
        if (translationDuration) {
            durationDiv.textContent = `Time for translation to complete: ${translationDuration}`;
        } else {
            durationDiv.textContent = '';
        }

        downloadSection.style.display = 'block';
        downloadSection.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        console.error('Translation error:', error);
        errorMessage.textContent = `Error: ${error.message}. Please check your file format (SRT, ASS, SSA, SUB) and try again.`;
        errorMessage.style.display = 'block';
        progressFill.style.width = '0%';
    } finally {
        // Reset button state
        translateBtn.disabled = false;
        loadingSpinner.style.display = 'none';
        btnText.textContent = 'Translate Subtitles';
        setTimeout(() => {
            progressBar.style.display = 'none';
            progressFill.style.width = '0%';
            progressPercent.style.display = 'none';
            progressPercent.textContent = '0%';
        }, 1000);
    }
});

// Language validation
document.getElementById('sourceLanguage').addEventListener('change', validateLanguages);
document.getElementById('targetLanguage').addEventListener('change', validateLanguages);

function validateLanguages() {
    const source = document.getElementById('sourceLanguage').value;
    const target = document.getElementById('targetLanguage').value;
    const errorMessage = document.getElementById('errorMessage');

    if (source && target && source === target) {
        errorMessage.textContent = 'Source and target languages cannot be the same.';
        errorMessage.style.display = 'block';
        document.getElementById('translateBtn').disabled = true;
    } else {
        errorMessage.style.display = 'none';
        document.getElementById('translateBtn').disabled = false;
    }
}
