import { getApiBase } from './api-base.js';
import { UI } from './app-ui.js';
import { setupFileUpload } from './file-upload.js';
import { isSearchMode, syncTranslateToggleVisibility, updatePrimaryButtonLabel, validateLanguages, wantsTranslate, } from './language-and-source-ui.js';
import { handleOsQueryKeydown, hideOpenSubtitlesSuggestions, scheduleFetchOpenSubtitlesSuggestions, setRunOpenSubtitlesSearch, } from './opensubtitles-suggestions.js';
import { clearOpenSubtitlesSelection, effectiveTotalPages, loadOpensubtitlesStatus, runOpenSubtitlesSearch, } from './opensubtitles-results.js';
import { scheduleSubtitlePreviewRefresh } from './subtitle-preview.js';
import { runDownloadOriginal, runTranslation, selectedOptionLabel, } from './translate-ui.js';
function byId(id) {
    const el = document.getElementById(id);
    if (!el)
        throw new Error(`Missing #${id}`);
    return el;
}
UI.api = getApiBase();
Object.assign(UI.el, {
    fileInput: byId('srtFile'),
    fileDisplay: byId('fileDisplay'),
    sourceSearch: byId('sourceSearch'),
    sourceUpload: byId('sourceUpload'),
    searchPanel: byId('searchPanel'),
    uploadPanel: byId('uploadPanel'),
    opensubtitlesHint: byId('opensubtitlesHint'),
    osQuery: byId('osQuery'),
    osSuggestionsPanel: byId('osSuggestionsPanel'),
    osSuggestionsList: byId('osSuggestionsList'),
    osSuggestLive: byId('osSuggestLive'),
    osAnyLanguage: byId('osAnyLanguage'),
    osSearchBtn: byId('osSearchBtn'),
    osSearchStatus: byId('osSearchStatus'),
    osLangChips: byId('osLangChips'),
    osResultsTable: byId('osResultsTable'),
    osResultsBody: byId('osResultsBody'),
    sourceLanguage: byId('sourceLanguage'),
    osPager: byId('osPager'),
    osPerPageSelect: byId('osPerPageSelect'),
    osPagePrev: byId('osPagePrev'),
    osPageNext: byId('osPageNext'),
    osPageInfo: byId('osPageInfo'),
    languageSection: byId('languageSection'),
    translateToOtherLang: byId('translateToOtherLang'),
    translateOnlyFields: byId('translateOnlyFields'),
    translateToggleWrap: byId('translateToggleWrap'),
    subtitlePreviewPanel: byId('subtitlePreviewPanel'),
    subtitlePreviewBg: byId('subtitlePreviewBg'),
    subtitlePreviewOrig: byId('subtitlePreviewOrig'),
    subtitlePreviewTrans: byId('subtitlePreviewTrans'),
    subtitlePreviewPinyin: byId('subtitlePreviewPinyin'),
    downloadSuccessMessage: byId('downloadSuccessMessage'),
    targetLanguage: byId('targetLanguage'),
    dualLanguage: byId('dualLanguage'),
    translationForm: byId('translationForm'),
    translateBtn: byId('translateBtn'),
    loadingSpinner: byId('loadingSpinner'),
    btnText: byId('btnText'),
    translateConfirmDialog: byId('translateConfirmDialog'),
    translateConfirmFile: byId('translateConfirmFile'),
    translateConfirmFrom: byId('translateConfirmFrom'),
    translateConfirmTo: byId('translateConfirmTo'),
    translateConfirmCancel: byId('translateConfirmCancel'),
    translateConfirmOk: byId('translateConfirmOk'),
    errorMessage: byId('errorMessage'),
    downloadSection: byId('downloadSection'),
    progressBar: byId('progressBar'),
    progressFill: byId('progressFill'),
    progressPercent: byId('progressPercent'),
    translationProgressTiming: byId('translationProgressTiming'),
    downloadBtn: byId('downloadBtn'),
    translationDuration: byId('translationDuration'),
});
const { resetFileInput } = setupFileUpload(UI.el.fileInput, UI.el.fileDisplay, validateLanguages);
UI.callbacks.resetFileInput = resetFileInput;
function syncSubtitleSourcePanels() {
    const search = isSearchMode();
    UI.el.searchPanel.hidden = !search;
    UI.el.uploadPanel.hidden = search;
    if (search) {
        UI.el.searchPanel.insertBefore(UI.el.languageSection, UI.el.osSearchStatus);
        resetFileInput();
    }
    else {
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
    const ie = e;
    if (ie.isTrusted) {
        UI.state.osSearchRefine = { year: null, imdbId: null };
    }
    if (!isSearchMode() || !UI.state.opensubtitlesConfigured)
        return;
    scheduleFetchOpenSubtitlesSuggestions();
});
UI.el.osQuery.addEventListener('blur', () => {
    window.setTimeout(() => {
        if (document.activeElement && UI.el.osSuggestionsPanel.contains(document.activeElement))
            return;
        if (!UI.el.osSuggestionsPanel.hidden) {
            hideOpenSubtitlesSuggestions();
        }
    }, 180);
});
UI.el.osQuery.addEventListener('keydown', (e) => handleOsQueryKeydown(e));
UI.el.osSearchBtn.addEventListener('click', () => {
    void runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true });
});
UI.el.osPerPageSelect.addEventListener('change', () => {
    void runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: true });
});
UI.el.osPagePrev.addEventListener('click', () => {
    if (UI.state.osSearchPage <= 1)
        return;
    UI.state.osSearchPage -= 1;
    void runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
});
UI.el.osPageNext.addEventListener('click', () => {
    if (UI.state.osSearchPage >= effectiveTotalPages())
        return;
    UI.state.osSearchPage += 1;
    void runOpenSubtitlesSearch({ refreshFromInput: false, resetPage: false });
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
    }
    else {
        if (!UI.el.fileInput.files || !UI.el.fileInput.files[0]) {
            errorMessage.textContent = 'Please choose a subtitle file to upload.';
            errorMessage.style.display = 'block';
            return;
        }
    }
    errorMessage.style.display = 'none';
    const fileLabel = isSearchMode()
        ? UI.state.fetchedLabel
        : (UI.el.fileInput.files?.[0]?.name ?? '');
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
//# sourceMappingURL=main.js.map