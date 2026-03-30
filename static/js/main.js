/**
 * API origin for fetch/SSE. Empty string = same host/port as the page (e.g. python app.py).
 * If you use a static server only (e.g. python -m http.server 8080), set a meta tag:
 *   <meta name="subtitle-translator-api-base" content="http://127.0.0.1:5000">
 * or we default localhost:5000 when the page is on :8080 or :5500 (Live Server).
 */
function getApiBase() {
    const meta = document.querySelector('meta[name="subtitle-translator-api-base"]');
    if (meta) {
        const v = (meta.getAttribute('content') || '').trim();
        if (v) return v.replace(/\/$/, '');
    }
    const port = window.location.port;
    const host = window.location.hostname;
    if (
        (port === '8080' || port === '5500' || port === '3000') &&
        (host === 'localhost' || host === '127.0.0.1')
    ) {
        return `${window.location.protocol}//${host}:5000`;
    }
    return '';
}

const API = getApiBase();

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
const sourceLanguage = document.getElementById('sourceLanguage');
const osPager = document.getElementById('osPager');
const osPerPageSelect = document.getElementById('osPerPageSelect');
const osPagePrev = document.getElementById('osPagePrev');
const osPageNext = document.getElementById('osPageNext');
const osPageInfo = document.getElementById('osPageInfo');
const translationForm = document.getElementById('translationForm');
const translateBtn = document.getElementById('translateBtn');
const translateConfirmDialog = document.getElementById('translateConfirmDialog');
const translateConfirmSummary = document.getElementById('translateConfirmSummary');
const translateConfirmCancel = document.getElementById('translateConfirmCancel');
const translateConfirmOk = document.getElementById('translateConfirmOk');

let opensubtitlesConfigured = false;
let rawSearchResults = [];
let activeLangFilter = 'all';
let fetchedId = null;
let fetchedLabel = '';
/** OpenSubtitles file id for the row that is selected (highlight + toggle off). */
let selectedOsFileId = null;
let fetchInProgressFileId = null;
let osLastSearchQuery = '';
let osLastSearchLang = '';
let osSearchPage = 1;
let osTotalPages = null;
let osTotalCount = null;

function isSearchMode() {
    return sourceSearch.checked;
}

function clearOpenSubtitlesSelection() {
    fetchedId = null;
    fetchedLabel = '';
    selectedOsFileId = null;
    fetchInProgressFileId = null;
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

function languageCounts(rows) {
    const m = new Map();
    for (const r of rows) {
        const k = r.language || '?';
        m.set(k, (m.get(k) || 0) + 1);
    }
    return m;
}

function displayLanguageLabel(code, rows) {
    if (!code || code === '?') return code;
    for (const r of rows) {
        if ((r.language || '') === code && r.languageName) {
            return r.languageName;
        }
    }
    return code;
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
        addChip(k, displayLanguageLabel(k, rows), counts.get(k));
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
}

function attrEscapeUrl(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/** Map OpenSubtitles subtitle language code to #sourceLanguage option value. */
const OS_LANG_TO_UI_SOURCE = {
    en: 'en',
    es: 'es',
    fr: 'fr',
    de: 'de',
    it: 'it',
    pt: 'pt',
    'pt-br': 'pt',
    'pt-pt': 'pt',
    ru: 'ru',
    'zh-cn': 'zh-cn',
    'zh-tw': 'zh-tw',
    zh: 'zh-cn',
    cmn: 'zh-cn',
    ja: 'ja',
    ko: 'ko',
    ar: 'ar',
    hi: 'hi',
    nl: 'nl',
    sv: 'sv',
    da: 'da',
    no: 'no',
    fi: 'fi',
    pl: 'pl',
    tr: 'tr',
    he: 'he',
};

function opensubtitlesLangToUiSource(code) {
    if (!code || typeof code !== 'string') return null;
    const c = code.trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(OS_LANG_TO_UI_SOURCE, c)) {
        return OS_LANG_TO_UI_SOURCE[c];
    }
    if (c.startsWith('pt')) return 'pt';
    return null;
}

function applySourceFromOpenSubtitlesRow(langCode) {
    const v = opensubtitlesLangToUiSource(langCode);
    if (!v) return;
    let found = false;
    for (let i = 0; i < sourceLanguage.options.length; i += 1) {
        if (sourceLanguage.options[i].value === v) {
            found = true;
            break;
        }
    }
    if (!found) return;
    sourceLanguage.value = v;
    validateLanguages();
}

function rowInfo(r) {
    const parts = [];
    const dl = r.downloads;
    if (typeof dl === 'number' && Number.isFinite(dl) && dl >= 0) {
        parts.push(`${dl} dl`);
    }
    const fps = r.fps;
    if (typeof fps === 'number' && Number.isFinite(fps) && fps > 0) {
        parts.push(`${fps} fps`);
    }
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
    let html = t ? esc(t) : '';
    if (r.release) html += `<div class="cell-muted">${esc(r.release)}</div>`;
    if (r.fileName) html += `<div class="cell-muted">${esc(r.fileName)}</div>`;
    return html || '—';
}

function normalizeHttpUrl(raw) {
    if (raw == null) return '';
    let s = String(raw).trim();
    if (!s) return '';
    if (s.startsWith('//')) s = `https:${s}`;
    return /^https?:\/\//i.test(s) ? s : '';
}

function titleCellWithPoster(r) {
    const url = normalizeHttpUrl(r.posterUrl);
    const posterHtml = url
        ? `<img class="os-poster-thumb" src="${attrEscapeUrl(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : '<span class="os-poster-placeholder" aria-hidden="true"></span>';
    return `<div class="os-title-cell">${posterHtml}<div class="os-title-cell-text">${titleCell(r)}</div></div>`;
}

function filterAndRenderResults() {
    osResultsBody.innerHTML = '';
    let rows = rawSearchResults;
    if (activeLangFilter !== 'all') {
        rows = rows.filter((r) => (r.language || '') === activeLangFilter);
    }
    if (fetchedId && selectedOsFileId != null) {
        const visible = new Set(rows.map((r) => String(r.fileId)));
        if (!visible.has(String(selectedOsFileId))) {
            clearOpenSubtitlesSelection();
        }
    }
    if (!rows.length) {
        osResultsTable.hidden = true;
        return;
    }
    osResultsTable.hidden = false;
    for (const r of rows) {
        const fid = String(r.fileId);
        const tr = document.createElement('tr');
        const isSelected = Boolean(fetchedId && selectedOsFileId != null && String(selectedOsFileId) === fid);
        const isFetching = fetchInProgressFileId != null && String(fetchInProgressFileId) === fid;
        if (isSelected) tr.classList.add('os-row-selected');
        const btnLabel = isFetching ? '…' : isSelected ? 'Selected' : 'Select';
        tr.innerHTML = `
            <td>${titleCell(r)}</td>
            <td>${esc(r.languageName || r.language || '')}</td>
            <td class="cell-muted">${esc(rowInfo(r))}</td>
            <td><button type="button" class="os-select-btn" data-file-id="${esc(r.fileId)}" aria-pressed="${isSelected ? 'true' : 'false'}">${btnLabel}</button></td>
        `;
        const btn = tr.querySelector('.os-select-btn');
        btn.addEventListener('click', () => selectSubtitleFile(r.fileId, r));
        osResultsBody.appendChild(tr);
    }
}

async function selectSubtitleFile(fileId, row) {
    const fid = String(fileId);
    if (fetchedId && selectedOsFileId != null && String(selectedOsFileId) === fid) {
        clearOpenSubtitlesSelection();
        filterAndRenderResults();
        return;
    }
    if (fetchInProgressFileId != null) {
        return;
    }
    const label = row.fileName || row.title || fileId;
    fetchInProgressFileId = fid;
    filterAndRenderResults();
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
        selectedOsFileId = fid;
        applySourceFromOpenSubtitlesRow(row.language);
        osSearchStatus.textContent = '';
    } catch (e) {
        console.error(e);
        osSearchStatus.textContent = e.message || String(e);
        selectedOsFileId = null;
        fetchedId = null;
        fetchedLabel = '';
    } finally {
        fetchInProgressFileId = null;
        filterAndRenderResults();
    }
}

function selectedOptionLabel(selectEl) {
    const opt = selectEl.options[selectEl.selectedIndex];
    return opt ? opt.textContent.trim() : '';
}

function effectiveTotalPages() {
    if (osTotalPages != null && osTotalPages >= 1) {
        return osTotalPages;
    }
    return 1;
}

function updateOsPagerUI() {
    const tp = effectiveTotalPages();
    osPagePrev.disabled = osSearchPage <= 1;
    osPageNext.disabled = osSearchPage >= tp;
    let info = `Page ${osSearchPage} of ${tp}`;
    if (osTotalCount != null) {
        info += ` (${osTotalCount} total)`;
    }
    osPageInfo.textContent = info;
}

function updateOsPagerVisibility() {
    osPager.hidden = rawSearchResults.length === 0;
    if (!osPager.hidden) {
        updateOsPagerUI();
    }
}

async function runOpenSubtitlesSearch(options) {
    const refreshFromInput = options && options.refreshFromInput;
    const resetPage = options && options.resetPage;
    if (refreshFromInput) {
        const q = osQuery.value.trim();
        if (!q) {
            osSearchStatus.textContent = 'Enter a title to search.';
            return;
        }
        osLastSearchQuery = q;
        osLastSearchLang = osAnyLanguage.checked ? '' : sourceLanguage.value;
    }
    if (!opensubtitlesConfigured) {
        osSearchStatus.textContent = 'OpenSubtitles is not configured on this server.';
        return;
    }
    if (!osLastSearchQuery) {
        osSearchStatus.textContent = 'Enter a title to search.';
        return;
    }
    if (resetPage) {
        osSearchPage = 1;
    }
    const perPage = parseInt(osPerPageSelect.value, 10) || 25;

    osSearchBtn.disabled = true;
    osSearchStatus.textContent = 'Searching…';
    clearOpenSubtitlesSelection();
    try {
        const resp = await fetch(`${API}/api/opensubtitles/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: osLastSearchQuery,
                language: osLastSearchLang,
                page: osSearchPage,
                perPage,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.error || resp.statusText || 'Search failed');
        }
        osTotalPages = data.totalPages != null ? data.totalPages : null;
        osTotalCount = data.totalCount != null ? data.totalCount : null;
        rawSearchResults = data.results || [];
        activeLangFilter = 'all';
        if (!rawSearchResults.length) {
            osSearchStatus.textContent =
                'No subtitles found — try another query, widen language (all languages), or upload a file.';
            osLangChips.hidden = true;
            osResultsTable.hidden = true;
            osPager.hidden = true;
        } else {
            const shown = rawSearchResults.length;
            const totalHint = osTotalCount != null ? ` (${osTotalCount} matching overall)` : '';
            osSearchStatus.textContent = `${shown} result(s) on this page${totalHint}. Pick one subtitle below.`;
            renderLangChips(rawSearchResults);
            filterAndRenderResults();
            updateOsPagerVisibility();
        }
    } catch (e) {
        console.error(e);
        osSearchStatus.textContent = e.message || String(e);
        rawSearchResults = [];
        osLangChips.hidden = true;
        osResultsTable.hidden = true;
        osPager.hidden = true;
        osTotalPages = null;
        osTotalCount = null;
    } finally {
        osSearchBtn.disabled = false;
    }
}

osQuery.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true });
    }
});

osSearchBtn.addEventListener('click', () => {
    runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true });
});

osPerPageSelect.addEventListener('change', () => {
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: true });
});

osPagePrev.addEventListener('click', () => {
    if (osSearchPage <= 1) return;
    osSearchPage -= 1;
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
});

osPageNext.addEventListener('click', () => {
    if (osSearchPage >= effectiveTotalPages()) return;
    osSearchPage += 1;
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
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

translationForm.addEventListener('submit', (e) => {
    e.preventDefault();
});

translateConfirmCancel.addEventListener('click', () => {
    translateConfirmDialog.close();
});

translateConfirmOk.addEventListener('click', async () => {
    translateConfirmDialog.close();
    await runTranslation();
});

translateBtn.addEventListener('click', () => {
    const errorMessage = document.getElementById('errorMessage');
    const source = document.getElementById('sourceLanguage').value;
    const target = document.getElementById('targetLanguage').value;
    if (source && target && source === target) {
        errorMessage.textContent = 'Source and target languages cannot be the same.';
        errorMessage.style.display = 'block';
        return;
    }
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
    let summary;
    if (isSearchMode()) {
        summary = `Subtitle file: ${fetchedLabel}\nFrom: ${selectedOptionLabel(sourceLanguage)}\nTo: ${selectedOptionLabel(document.getElementById('targetLanguage'))}`;
    } else {
        summary = `Subtitle file: ${fileInput.files[0].name}\nFrom: ${selectedOptionLabel(sourceLanguage)}\nTo: ${selectedOptionLabel(document.getElementById('targetLanguage'))}`;
    }
    translateConfirmSummary.textContent = summary;
    translateConfirmDialog.showModal();
});

async function runTranslation() {
    const loadingSpinner = document.getElementById('loadingSpinner');
    const btnText = document.getElementById('btnText');
    const errorMessage = document.getElementById('errorMessage');
    const downloadSection = document.getElementById('downloadSection');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const dualLanguage = document.getElementById('dualLanguage');

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
            osPager.hidden = true;
            osTotalPages = null;
            osTotalCount = null;
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
}

document.getElementById('sourceLanguage').addEventListener('change', validateLanguages);
document.getElementById('targetLanguage').addEventListener('change', validateLanguages);

function validateLanguages() {
    const source = document.getElementById('sourceLanguage').value;
    const target = document.getElementById('targetLanguage').value;
    const errorMessage = document.getElementById('errorMessage');

    if (source && target && source === target) {
        errorMessage.textContent = 'Source and target languages cannot be the same.';
        errorMessage.style.display = 'block';
        translateBtn.disabled = true;
    } else {
        errorMessage.style.display = 'none';
        translateBtn.disabled = false;
    }
}
