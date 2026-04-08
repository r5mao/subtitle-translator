import { UI } from './app-ui.js';
import { opensubtitlesLangToUiSource } from './opensubtitles-format.js';

export function isSearchMode(): boolean {
    return UI.el.sourceSearch.checked;
}

export function wantsTranslate(): boolean {
    if (!isSearchMode()) return true;
    return UI.el.translateToOtherLang.checked;
}

export function updatePrimaryButtonLabel(): void {
    const btnText = UI.el.btnText;
    if (!isSearchMode() || wantsTranslate()) {
        btnText.textContent = 'Translate subtitles';
    } else {
        btnText.textContent = 'Download subtitle';
    }
}

export function syncTranslateToggleVisibility(): void {
    if (!isSearchMode()) {
        UI.el.translateToggleWrap.hidden = true;
        UI.el.translateToOtherLang.checked = true;
        UI.el.translateOnlyFields.hidden = false;
    } else {
        UI.el.translateToggleWrap.hidden = false;
        UI.el.translateOnlyFields.hidden = !UI.el.translateToOtherLang.checked;
    }
    updatePrimaryButtonLabel();
    validateLanguages();
}

export function applySourceFromOpenSubtitlesRow(langCode: unknown): void {
    const v = opensubtitlesLangToUiSource(langCode);
    if (!v) return;
    let found = false;
    for (let i = 0; i < UI.el.sourceLanguage.options.length; i += 1) {
        if (UI.el.sourceLanguage.options[i]!.value === v) {
            found = true;
            break;
        }
    }
    if (!found) return;
    UI.el.sourceLanguage.value = v;
    validateLanguages();
}

export function validateLanguages(): void {
    const source = UI.el.sourceLanguage.value;
    const target = UI.el.targetLanguage.value;
    const errorMessage = UI.el.errorMessage;
    const langClashMsg = 'Source and target languages cannot be the same.';

    if (!wantsTranslate()) {
        if (errorMessage.textContent === langClashMsg) {
            errorMessage.style.display = 'none';
        }
        UI.el.translateBtn.disabled = isSearchMode() && !UI.state.fetchedId;
        return;
    }

    if (source && target && source === target) {
        errorMessage.textContent = langClashMsg;
        errorMessage.style.display = 'block';
        UI.el.translateBtn.disabled = true;
        return;
    }
    if (errorMessage.textContent === langClashMsg) {
        errorMessage.style.display = 'none';
    }
    const needFile = !isSearchMode() && (!UI.el.fileInput.files || !UI.el.fileInput.files[0]);
    const needFetch = isSearchMode() && !UI.state.fetchedId;
    UI.el.translateBtn.disabled = needFile || needFetch;
}
