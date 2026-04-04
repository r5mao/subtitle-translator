import { getApiBase } from './api-base.js';
import { UI } from './app-ui.js';
import { setupFileUpload } from './file-upload.js';
import {
    isSearchMode,
    syncTranslateToggleVisibility,
    updatePrimaryButtonLabel,
    validateLanguages,
    wantsTranslate,
} from './language-and-source-ui.js';
import {
    handleOsQueryKeydown,
    hideOpenSubtitlesSuggestions,
    scheduleFetchOpenSubtitlesSuggestions,
    setRunOpenSubtitlesSearch,
} from './opensubtitles-suggestions.js';
import {
    clearOpenSubtitlesSelection,
    effectiveTotalPages,
    loadOpensubtitlesStatus,
    runOpenSubtitlesSearch,
} from './opensubtitles-results.js';
import { scheduleSubtitlePreviewRefresh } from './subtitle-preview.js';
import {
    runDownloadOriginal,
    runTranslation,
    selectedOptionLabel,
} from './translate-ui.js';

UI.api = getApiBase();

Object.assign(UI.el, {
    fileInput: document.getElementById('srtFile'),
    fileDisplay: document.getElementById('fileDisplay'),
    sourceSearch: document.getElementById('sourceSearch'),
    sourceUpload: document.getElementById('sourceUpload'),
    searchPanel: document.getElementById('searchPanel'),
    uploadPanel: document.getElementById('uploadPanel'),
    opensubtitlesHint: document.getElementById('opensubtitlesHint'),
    osQuery: document.getElementById('osQuery'),
    osSuggestionsPanel: document.getElementById('osSuggestionsPanel'),
    osSuggestionsList: document.getElementById('osSuggestionsList'),
    osSuggestLive: document.getElementById('osSuggestLive'),
    osAnyLanguage: document.getElementById('osAnyLanguage'),
    osSearchBtn: document.getElementById('osSearchBtn'),
    osSearchStatus: document.getElementById('osSearchStatus'),
    osLangChips: document.getElementById('osLangChips'),
    osResultsTable: document.getElementById('osResultsTable'),
    osResultsBody: document.getElementById('osResultsBody'),
    sourceLanguage: document.getElementById('sourceLanguage'),
    osPager: document.getElementById('osPager'),
    osPerPageSelect: document.getElementById('osPerPageSelect'),
    osPagePrev: document.getElementById('osPagePrev'),
    osPageNext: document.getElementById('osPageNext'),
    osPageInfo: document.getElementById('osPageInfo'),
    languageSection: document.getElementById('languageSection'),
    translateToOtherLang: document.getElementById('translateToOtherLang'),
    translateOnlyFields: document.getElementById('translateOnlyFields'),
    translateToggleWrap: document.getElementById('translateToggleWrap'),
    subtitlePreviewPanel: document.getElementById('subtitlePreviewPanel'),
    subtitlePreviewBg: document.getElementById('subtitlePreviewBg'),
    subtitlePreviewOrig: document.getElementById('subtitlePreviewOrig'),
    subtitlePreviewTrans: document.getElementById('subtitlePreviewTrans'),
    subtitlePreviewPinyin: document.getElementById('subtitlePreviewPinyin'),
    downloadSuccessMessage: document.getElementById('downloadSuccessMessage'),
    targetLanguage: document.getElementById('targetLanguage'),
    dualLanguage: document.getElementById('dualLanguage'),
    translationForm: document.getElementById('translationForm'),
    translateBtn: document.getElementById('translateBtn'),
    loadingSpinner: document.getElementById('loadingSpinner'),
    btnText: document.getElementById('btnText'),
    translateConfirmDialog: document.getElementById('translateConfirmDialog'),
    translateConfirmFile: document.getElementById('translateConfirmFile'),
    translateConfirmFrom: document.getElementById('translateConfirmFrom'),
    translateConfirmTo: document.getElementById('translateConfirmTo'),
    translateConfirmCancel: document.getElementById('translateConfirmCancel'),
    translateConfirmOk: document.getElementById('translateConfirmOk'),
    errorMessage: document.getElementById('errorMessage'),
    downloadSection: document.getElementById('downloadSection'),
    progressBar: document.getElementById('progressBar'),
    progressFill: document.getElementById('progressFill'),
    progressPercent: document.getElementById('progressPercent'),
    translationProgressTiming: document.getElementById('translationProgressTiming'),
    downloadBtn: document.getElementById('downloadBtn'),
    translationDuration: document.getElementById('translationDuration'),
});

const { resetFileInput } = setupFileUpload(
    UI.el.fileInput,
    UI.el.fileDisplay,
    validateLanguages,
);
UI.callbacks.resetFileInput = resetFileInput;

function syncSubtitleSourcePanels() {
    const search = isSearchMode();
    UI.el.searchPanel.hidden = !search;
    UI.el.uploadPanel.hidden = search;
    if (search) {
        UI.el.searchPanel.insertBefore(UI.el.languageSection, UI.el.osSearchStatus);
        resetFileInput();
    } else {
        UI.el.uploadPanel.appendChild(UI.el.languageSection);
        clearOpenSubtitlesSelection();
        hideOpenSubtitlesSuggestions();
        UI.state.osSearchRefine = { year: null, imdbId: null };
    }
    syncTranslateToggleVisibility();
}

UI.callbacks.syncSubtitleSourcePanels = syncSubtitleSourcePanels;

setRunOpenSubtitlesSearch(runOpenSubtitlesSearch);

UI.el.translateToOtherLang.addEventListener('change', () => {
    syncTranslateToggleVisibility();
    scheduleSubtitlePreviewRefresh();
});

UI.el.sourceSearch.addEventListener('change', syncSubtitleSourcePanels);
UI.el.sourceUpload.addEventListener('change', syncSubtitleSourcePanels);

syncSubtitleSourcePanels();

UI.el.osQuery.addEventListener('input', (e) => {
    if (e.isTrusted) {
        UI.state.osSearchRefine = { year: null, imdbId: null };
    }
    if (!isSearchMode() || !UI.state.opensubtitlesConfigured) return;
    scheduleFetchOpenSubtitlesSuggestions();
});

UI.el.osQuery.addEventListener('blur', () => {
    window.setTimeout(() => {
        if (document.activeElement && UI.el.osSuggestionsPanel.contains(document.activeElement)) return;
        if (!UI.el.osSuggestionsPanel.hidden) {
            hideOpenSubtitlesSuggestions();
        }
    }, 180);
});

UI.el.osQuery.addEventListener('keydown', handleOsQueryKeydown);

UI.el.osSearchBtn.addEventListener('click', () => {
    runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true });
});

UI.el.osPerPageSelect.addEventListener('change', () => {
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: true });
});

UI.el.osPagePrev.addEventListener('click', () => {
    if (UI.state.osSearchPage <= 1) return;
    UI.state.osSearchPage -= 1;
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
});

UI.el.osPageNext.addEventListener('click', () => {
    if (UI.state.osSearchPage >= effectiveTotalPages()) return;
    UI.state.osSearchPage += 1;
    runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
});

void loadOpensubtitlesStatus();

UI.el.translationForm.addEventListener('submit', (e) => {
    e.preventDefault();
});

UI.el.translateConfirmCancel.addEventListener('click', () => {
    UI.el.translateConfirmDialog.close();
});

UI.el.translateConfirmOk.addEventListener('click', async () => {
    UI.el.translateConfirmDialog.close();
    await runTranslation();
});

UI.el.translateBtn.addEventListener('click', () => {
    const errorMessage = UI.el.errorMessage;
    if (isSearchMode() && !wantsTranslate()) {
        if (!UI.state.fetchedId) {
            errorMessage.textContent =
                'Search and select a subtitle from the results, or switch to Upload file.';
            errorMessage.style.display = 'block';
            return;
        }
        errorMessage.style.display = 'none';
        void runDownloadOriginal();
        return;
    }
    const source = UI.el.sourceLanguage.value;
    const target = UI.el.targetLanguage.value;
    if (source && target && source === target) {
        errorMessage.textContent = 'Source and target languages cannot be the same.';
        errorMessage.style.display = 'block';
        return;
    }
    if (isSearchMode()) {
        if (!UI.state.fetchedId) {
            errorMessage.textContent =
                'Search and select a subtitle from the results, or switch to Upload file.';
            errorMessage.style.display = 'block';
            return;
        }
    } else {
        if (!UI.el.fileInput.files || !UI.el.fileInput.files[0]) {
            errorMessage.textContent = 'Please choose a subtitle file to upload.';
            errorMessage.style.display = 'block';
            return;
        }
    }
    errorMessage.style.display = 'none';
    const fileLabel = isSearchMode() ? UI.state.fetchedLabel : UI.el.fileInput.files[0].name;
    UI.el.translateConfirmFile.textContent = fileLabel;
    UI.el.translateConfirmFrom.textContent = selectedOptionLabel(UI.el.sourceLanguage);
    UI.el.translateConfirmTo.textContent = selectedOptionLabel(UI.el.targetLanguage);
    UI.el.translateConfirmDialog.showModal();
});

function onLanguageOrDualChange() {
    validateLanguages();
    scheduleSubtitlePreviewRefresh();
}

UI.el.sourceLanguage.addEventListener('change', onLanguageOrDualChange);
UI.el.targetLanguage.addEventListener('change', onLanguageOrDualChange);
UI.el.dualLanguage.addEventListener('change', onLanguageOrDualChange);

updatePrimaryButtonLabel();
validateLanguages();
