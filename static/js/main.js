const API = '';

// --- File upload UI ---
const fileInput = document.getElementById('srtFile');
const fileDisplay = document.getElementById('fileDisplay');
const fileIcon = fileDisplay.querySelector('.file-icon');
const fileText = fileDisplay.querySelector('.file-text');

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
});

function resetFileInput() {
    fileDisplay.classList.remove('has-file');
    fileText.classList.remove('has-file');
    fileText.textContent = 'Click to browse or drag SRT, ASS, SSA, or SUB file here';
    fileIcon.textContent = '📁';
    fileInput.value = '';
}

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

// --- OpenSubtitles search ---
const sourceSearch = document.getElementById('sourceSearch');
const sourceUpload = document.getElementById('sourceUpload');
const searchPanel = document.getElementById('searchPanel');
const uploadPanel = document.getElementById('uploadPanel');
const opensubtitlesHint = document.getElementById('opensubtitlesHint');
const osQuery = document.getElementById('osQuery');
const osAnyLanguage = document.getElementById('osAnyLanguage');
const osSearchBtn = document.getElementById('osSearchBtn');
const osSearchStatus = document.getElementById('osSearchStatus');
const osLangChips = document.getElementById('osLangChips');
const osResultsTable = document.getElementById('osResultsTable');
const osResultsBody = document.getElementById('osResultsBody');
const osSelectedBanner = document.getElementById('osSelectedBanner');
const osSelectedText = document.getElementById('osSelectedText');
const osChangeBtn = document.getElementById('osChangeBtn');
const sourceLanguage = document.getElementById('sourceLanguage');

let opensubtitlesConfigured = false;
let rawSearchResults = [];
let activeLangFilter = 'all';
let fetchedId = null;
let fetchedLabel = '';

function isSearchMode() {
    return sourceSearch.checked;
}

function clearOpenSubtitlesSelection() {
    fetchedId = null;
    fetchedLabel = '';
    osSelectedBanner.hidden = true;
    osSelectedText.textContent = '';
}

function syncSubtitleSourcePanels() {
    const search = isSearchMode();
    searchPanel.hidden = !search;
    uploadPanel.hidden = search;
    if (!search) {
        clearOpenSubtitlesSelection();
    } else {
        resetFileInput();
    }
}

sourceSearch.addEventListener('change', syncSubtitleSourcePanels);
sourceUpload.addEventListener('change', syncSubtitleSourcePanels);

osChangeBtn.addEventListener('click', () => {
    clearOpenSubtitlesSelection();
    filterAndRenderResults();
});

function languageCounts(rows) {
    const m = new Map();
    for (const r of rows) {
        const k = r.language || '?';
        m.set(k, (m.get(k) || 0) + 1);
    }
    return m;
}

function renderLangChips(rows) {
    const counts = languageCounts(rows);
    const keys = Array.from(counts.keys()).sort();
    if (keys.length <= 1) {
        osLangChips.hidden = true;
        osLangChips.innerHTML = '';
        return;
    }
    osLangChips.hidden = false;
    osLangChips.innerHTML = '';
    const addChip = (code, label, count) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'lang-chip' + (activeLangFilter === code ? ' active' : '');
        b.textContent = count != null ? `${label} (${count})` : label;
        b.addEventListener('click', () => {
            activeLangFilter = code;
            renderLangChips(rawSearchResults);
            filterAndRenderResults();
        });
        osLangChips.appendChild(b);
    };
    addChip('all', 'All languages', rows.length);
    for (const k of keys) {
        addChip(k, k, counts.get(k));
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
}

function rowInfo(r) {
    const parts = [];
    if (r.downloads != null) parts.push(`${r.downloads} dl`);
    if (r.fps != null) parts.push(`${r.fps} fps`);
    if (r.hearingImpaired) parts.push('HI');
    if (r.machineTranslated) parts.push('MT');
    return parts.length ? parts.join(' · ') : '—';
}

function titleCell(r) {
    let t = r.title || '';
    if (r.year) t += ` (${r.year})`;
    if (r.season != null && r.episode != null) {
        t += ` S${r.season}E${r.episode}`;
    }
    let html = esc(t);
    if (r.release) html += `<div class="cell-muted">${esc(r.release)}</div>`;
    return html || esc(r.fileName);
}

function filterAndRenderResults() {
    osResultsBody.innerHTML = '';
    let rows = rawSearchResults;
    if (activeLangFilter !== 'all') {
        rows = rows.filter((r) => (r.language || '') === activeLangFilter);
    }
    if (!rows.length) {
        osResultsTable.hidden = true;
        return;
    }
    osResultsTable.hidden = false;
    for (const r of rows) {
        const tr = document.createElement('tr');
        const busy = fetchedId !== null;
        tr.innerHTML = `
            <td>${titleCell(r)}</td>
            <td>${esc(r.language || '')}</td>
            <td><span class="cell-muted">${esc(r.fileName || '')}</span></td>
            <td class="cell-muted">${esc(rowInfo(r))}</td>
            <td><button type="button" class="os-select-btn" data-file-id="${esc(r.fileId)}">Select</button></td>
        `;
        const btn = tr.querySelector('.os-select-btn');
        if (busy) btn.disabled = true;
        btn.addEventListener('click', () => selectSubtitleFile(r.fileId, r));
        osResultsBody.appendChild(tr);
    }
}

async function selectSubtitleFile(fileId, row) {
    const label = row.fileName || row.title || fileId;
    const buttons = osResultsBody.querySelectorAll('.os-select-btn');
    buttons.forEach((b) => {
        b.disabled = true;
    });
    try {
        const resp = await fetch(`${API}/api/opensubtitles/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: fileId }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.error || resp.statusText || 'Fetch failed');
        }
        fetchedId = data.fetchedId;
        fetchedLabel = data.filename || label;
        osSelectedBanner.hidden = false;
        osSelectedText.textContent = `Using: ${fetchedLabel}`;
        osSearchStatus.textContent = '';
        filterAndRenderResults();
    } catch (e) {
        console.error(e);
        osSearchStatus.textContent = e.message || String(e);
        filterAndRenderResults();
    }
}

osSearchBtn.addEventListener('click', async () => {
    const q = osQuery.value.trim();
    if (!q) {
        osSearchStatus.textContent = 'Enter a title to search.';
        return;
    }
    if (!opensubtitlesConfigured) {
        osSearchStatus.textContent = 'OpenSubtitles is not configured on this server.';
        return;
    }
    osSearchBtn.disabled = true;
    osSearchStatus.textContent = 'Searching…';
    clearOpenSubtitlesSelection();
    try {
        const lang = osAnyLanguage.checked ? '' : sourceLanguage.value;
        const resp = await fetch(`${API}/api/opensubtitles/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q, language: lang, page: 1 }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.error || resp.statusText || 'Search failed');
        }
        rawSearchResults = data.results || [];
        activeLangFilter = 'all';
        if (!rawSearchResults.length) {
            osSearchStatus.textContent =
                'No subtitles found — try another query, widen language (all languages), or upload a file.';
            osLangChips.hidden = true;
            osResultsTable.hidden = true;
        } else {
            osSearchStatus.textContent = `${rawSearchResults.length} result(s). Pick one subtitle below.`;
            renderLangChips(rawSearchResults);
            filterAndRenderResults();
        }
    } catch (e) {
        console.error(e);
        osSearchStatus.textContent = e.message || String(e);
        rawSearchResults = [];
        osLangChips.hidden = true;
        osResultsTable.hidden = true;
    } finally {
        osSearchBtn.disabled = false;
    }
});

async function loadOpensubtitlesStatus() {
    try {
        const resp = await fetch(`${API}/api/opensubtitles/status`);
        const data = await resp.json();
        opensubtitlesConfigured = !!data.configured;
        if (!opensubtitlesConfigured) {
            opensubtitlesHint.hidden = false;
            opensubtitlesHint.textContent =
                'OpenSubtitles search is unavailable (server has no API credentials). Use upload instead.';
            sourceSearch.disabled = true;
            if (isSearchMode()) {
                sourceUpload.checked = true;
                syncSubtitleSourcePanels();
            }
        } else {
            opensubtitlesHint.hidden = true;
            sourceSearch.disabled = false;
        }
    } catch {
        opensubtitlesHint.hidden = false;
        opensubtitlesHint.textContent = 'Could not reach server for OpenSubtitles status.';
    }
}

loadOpensubtitlesStatus();

// --- Form submit / translate ---
document.getElementById('translationForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const translateBtn = document.getElementById('translateBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const btnText = document.getElementById('btnText');
    const errorMessage = document.getElementById('errorMessage');
    const downloadSection = document.getElementById('downloadSection');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const dualLanguage = document.getElementById('dualLanguage');

    if (isSearchMode()) {
        if (!fetchedId) {
            errorMessage.textContent =
                'Search and select a subtitle from the results, or switch to Upload file.';
            errorMessage.style.display = 'block';
            return;
        }
    } else {
        if (!fileInput.files || !fileInput.files[0]) {
            errorMessage.textContent = 'Please choose a subtitle file to upload.';
            errorMessage.style.display = 'block';
            return;
        }
    }

    errorMessage.style.display = 'none';
    downloadSection.style.display = 'none';
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressPercent.style.display = 'block';
    progressPercent.textContent = '0%';

    translateBtn.disabled = true;
    loadingSpinner.style.display = 'inline-block';
    btnText.textContent = 'Translating...';

    try {
        const taskResponse = await fetch(`${API}/api/task`);

        if (!taskResponse.ok) {
            const errorText = await taskResponse.text();
            throw new Error(errorText || 'Server error');
        }

        const taskJson = await taskResponse.json();
        const taskId = taskJson.taskId;

        const formData = new FormData();
        formData.append('sourceLanguage', document.getElementById('sourceLanguage').value);
        formData.append('targetLanguage', document.getElementById('targetLanguage').value);
        formData.append('dualLanguage', dualLanguage.checked ? 'true' : 'false');
        formData.append('taskId', taskId);
        if (fetchedId && isSearchMode()) {
            formData.append('fetchedId', fetchedId);
        } else {
            formData.append('srtFile', fileInput.files[0]);
        }

        const evtSource = new EventSource(`${API}/api/translate/progress/${taskId}`);
        const ssePromise = new Promise((resolve, reject) => {
            let completed = false;
            progressBar.style.display = 'block';
            progressFill.style.width = '0%';
            evtSource.onmessage = function (event) {
                let progress = parseInt(event.data, 10);
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
            evtSource.onerror = function () {
                evtSource.close();
                reject(new Error('Lost connection to progress server.'));
            };
        });

        const translatePromise = (async () => {
            const response = await fetch(`${API}/api/translate`, {
                method: 'POST',
                body: formData,
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

        try {
            await ssePromise;
        } catch (sseErr) {
            console.warn(sseErr?.message || sseErr);
        }

        const json = await translatePromise;
        const downloadUrl = json.downloadUrl;
        const translationDuration = json.translationDuration;
        const serverFilename = json.filename;

        const srtResponse = await fetch(`${API}${downloadUrl}`);
        if (!srtResponse.ok) {
            throw new Error('Failed to download translated subtitle file');
        }
        const translatedContent = await srtResponse.text();

        const blob = new Blob([translatedContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const downloadBtn = document.getElementById('downloadBtn');
        downloadBtn.href = url;
        const targetLang = formData.get('targetLanguage');
        let newFileName = serverFilename;
        if (!newFileName) {
            const originalFileName = isSearchMode()
                ? fetchedLabel || 'subtitle.srt'
                : fileInput.files[0].name;
            const dualSuffix = dualLanguage?.checked ? '_dual' : '';
            newFileName = originalFileName.replace(
                /\.(srt|ass|ssa|sub)$/i,
                `_GoogleTrans_${targetLang}${dualSuffix}.$1`
            );
            if (newFileName === originalFileName) {
                newFileName = originalFileName + `_GoogleTrans_${targetLang}${dualSuffix}`;
            }
        }
        downloadBtn.download = newFileName;

        const durationDiv = document.getElementById('translationDuration');
        if (translationDuration) {
            durationDiv.textContent = `Time for translation to complete: ${translationDuration}`;
        } else {
            durationDiv.textContent = '';
        }

        if (isSearchMode() && fetchedId) {
            clearOpenSubtitlesSelection();
            rawSearchResults = [];
            osLangChips.hidden = true;
            osResultsTable.hidden = true;
            osResultsBody.innerHTML = '';
        }

        downloadSection.style.display = 'block';
        downloadSection.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Translation error:', error);
        let msg = error.message || String(error);
        try {
            const parsed = JSON.parse(msg);
            if (parsed && parsed.error) msg = parsed.error;
        } catch {
            /* plain text */
        }
        errorMessage.textContent = `Error: ${msg}. Please check your file format (SRT, ASS, SSA, SUB) and try again.`;
        errorMessage.style.display = 'block';
        progressFill.style.width = '0%';
    } finally {
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
