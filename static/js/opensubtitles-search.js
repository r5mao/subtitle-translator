import { UI, OS_MAX_PAGER_PAGES } from './app-ui.js';
import { isSearchMode } from './language-and-source-ui.js';
import { hideOpenSubtitlesSuggestions } from './opensubtitles-suggestions.js';
import {
    clearOpenSubtitlesSelection,
    filterAndRenderResults,
    renderLangChips,
} from './opensubtitles-results-table.js';

export function effectiveTotalPages() {
    const { state } = UI;
    let tp = 1;
    if (state.osTotalPages != null && state.osTotalPages >= 1) {
        tp = state.osTotalPages;
    }
    return Math.min(tp, OS_MAX_PAGER_PAGES);
}

export function updateOsPagerUI() {
    const { state } = UI;
    const tp = effectiveTotalPages();
    UI.el.osPagePrev.disabled = state.osSearchPage <= 1;
    UI.el.osPageNext.disabled = state.osSearchPage >= tp;
    let info = `Page ${state.osSearchPage} of ${tp}`;
    if (state.osTotalCount != null) {
        info += ` (${state.osTotalCount} total)`;
    }
    UI.el.osPageInfo.textContent = info;
}

export function updateOsPagerVisibility() {
    const { state } = UI;
    UI.el.osPager.hidden = state.rawSearchResults.length === 0;
    if (!UI.el.osPager.hidden) {
        updateOsPagerUI();
    }
}

export async function runOpenSubtitlesSearch(options) {
    const { state } = UI;
    hideOpenSubtitlesSuggestions();
    const refreshFromInput = options && options.refreshFromInput;
    const resetPage = options && options.resetPage;
    const keepRefine = options && options.keepRefine;
    if (refreshFromInput) {
        const q = UI.el.osQuery.value.trim();
        if (!q) {
            UI.el.osSearchStatus.textContent = 'Enter a title to search.';
            return;
        }
        const prevQ = state.osLastSearchQuery;
        if (!keepRefine && q !== prevQ) {
            state.osSearchRefine = { year: null, imdbId: null };
        }
        state.osLastSearchQuery = q;
        state.osLastSearchLang = UI.el.osAnyLanguage.checked ? '' : UI.el.sourceLanguage.value;
    }
    if (!state.opensubtitlesConfigured) {
        UI.el.osSearchStatus.textContent = 'OpenSubtitles is not configured on this server.';
        return;
    }
    if (!state.osLastSearchQuery) {
        UI.el.osSearchStatus.textContent = 'Enter a title to search.';
        return;
    }
    if (resetPage) {
        state.osSearchPage = 1;
    }
    const perPage = parseInt(UI.el.osPerPageSelect.value, 10) || 10;

    UI.el.osSearchBtn.disabled = true;
    UI.el.osSearchStatus.textContent = 'Searching…';
    clearOpenSubtitlesSelection();
    try {
        const searchPayload = {
            query: state.osLastSearchQuery,
            language: state.osLastSearchLang,
            page: state.osSearchPage,
            perPage,
        };
        if (state.osSearchRefine.year != null) {
            searchPayload.year = state.osSearchRefine.year;
        }
        if (state.osSearchRefine.imdbId) {
            searchPayload.imdbId = state.osSearchRefine.imdbId;
        }
        const resp = await fetch(`${UI.api}/api/opensubtitles/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(searchPayload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.error || resp.statusText || 'Search failed');
        }
        state.osTotalPages = data.totalPages != null ? data.totalPages : null;
        state.osTotalCount = data.totalCount != null ? data.totalCount : null;
        state.rawSearchResults = data.results || [];
        state.activeLangFilter = 'all';
        if (!state.rawSearchResults.length) {
            UI.el.osSearchStatus.textContent =
                'No subtitles found — try another query, widen language (all languages), or upload a file.';
            UI.el.osLangChips.hidden = true;
            UI.el.osResultsTable.hidden = true;
            UI.el.osPager.hidden = true;
        } else {
            const shown = state.rawSearchResults.length;
            const totalHint = state.osTotalCount != null ? ` (${state.osTotalCount} matching overall)` : '';
            UI.el.osSearchStatus.textContent = `${shown} result(s) on this page${totalHint}. Pick one subtitle below.`;
            renderLangChips(state.rawSearchResults);
            filterAndRenderResults();
            updateOsPagerVisibility();
        }
    } catch (e) {
        console.error(e);
        UI.el.osSearchStatus.textContent = e.message || String(e);
        state.rawSearchResults = [];
        UI.el.osLangChips.hidden = true;
        UI.el.osResultsTable.hidden = true;
        UI.el.osPager.hidden = true;
        state.osTotalPages = null;
        state.osTotalCount = null;
    } finally {
        UI.el.osSearchBtn.disabled = false;
    }
}

export async function loadOpensubtitlesStatus() {
    const { state } = UI;
    try {
        const resp = await fetch(`${UI.api}/api/opensubtitles/status`);
        const data = await resp.json();
        state.opensubtitlesConfigured = !!data.configured;
        if (!state.opensubtitlesConfigured) {
            hideOpenSubtitlesSuggestions();
            UI.el.opensubtitlesHint.hidden = false;
            UI.el.opensubtitlesHint.textContent =
                'OpenSubtitles search is unavailable (server has no API credentials). Use upload instead.';
            UI.el.sourceSearch.disabled = true;
            if (isSearchMode()) {
                UI.el.sourceUpload.checked = true;
                UI.callbacks.syncSubtitleSourcePanels();
            }
        } else {
            UI.el.opensubtitlesHint.hidden = true;
            UI.el.sourceSearch.disabled = false;
        }
    } catch {
        UI.el.opensubtitlesHint.hidden = false;
        UI.el.opensubtitlesHint.textContent = 'Could not reach server for OpenSubtitles status.';
    }
}
