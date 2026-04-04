import { UI } from './app-ui.js';
import {
    attrEscapeUrl,
    esc,
} from './string-utils.js';
import {
    bindOsPosterImgOnError,
    normalizeHttpUrl,
    posterProxySrc,
    suggestionSearchText,
} from './opensubtitles-format.js';

const OS_SUGGEST_DEBOUNCE_MS = 300;
const OS_SUGGEST_MIN_LEN = 2;

/** Set from main after opensubtitles-search loads (avoids circular import). */
let runOpenSubtitlesSearch = async () => {};

export function setRunOpenSubtitlesSearch(fn) {
    runOpenSubtitlesSearch = fn;
}

function isSearchMode() {
    return UI.el.sourceSearch?.checked;
}

export function hideOpenSubtitlesSuggestions() {
    const { state } = UI;
    if (state.suggestDebounceTimer) {
        clearTimeout(state.suggestDebounceTimer);
        state.suggestDebounceTimer = null;
    }
    if (state.suggestAbort) {
        state.suggestAbort.abort();
        state.suggestAbort = null;
    }
    state.suggestionRows = [];
    state.activeSuggestionIndex = -1;
    UI.el.osSuggestionsList.innerHTML = '';
    UI.el.osSuggestionsPanel.hidden = true;
    UI.el.osQuery.setAttribute('aria-expanded', 'false');
    UI.el.osQuery.removeAttribute('aria-activedescendant');
}

export function updateOpenSubtitlesSuggestionActiveClasses() {
    const { state } = UI;
    const items = UI.el.osSuggestionsList.querySelectorAll('.os-suggestion-item');
    items.forEach((el, i) => {
        const on = i === state.activeSuggestionIndex;
        el.classList.toggle('os-suggestion-item-active', on);
        el.setAttribute('aria-selected', on ? 'true' : 'false');
        if (on) el.scrollIntoView({ block: 'nearest' });
    });
    if (state.activeSuggestionIndex >= 0) {
        UI.el.osQuery.setAttribute('aria-activedescendant', `os-sugg-${state.activeSuggestionIndex}`);
    } else {
        UI.el.osQuery.removeAttribute('aria-activedescendant');
    }
}

export function renderOpenSubtitlesSuggestions(list) {
    const { state } = UI;
    state.suggestionRows = list;
    state.activeSuggestionIndex = -1;
    UI.el.osSuggestionsList.innerHTML = '';
    if (!list.length) {
        UI.el.osSuggestionsPanel.hidden = true;
        UI.el.osQuery.setAttribute('aria-expanded', 'false');
        return;
    }
    for (let i = 0; i < list.length; i += 1) {
        const s = list[i];
        const li = document.createElement('li');
        li.id = `os-sugg-${i}`;
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', 'false');
        li.className = 'os-suggestion-item';
        const url = normalizeHttpUrl(s.posterUrl);
        const useProxy = url && /^https?:\/\//i.test(url);
        const src = useProxy ? posterProxySrc(UI.api, url) : '';
        const posterHtml = src
            ? `<img class="os-suggestion-poster" src="${attrEscapeUrl(src)}" alt="" loading="lazy">`
            : '<span class="os-suggestion-poster os-suggestion-poster-placeholder" aria-hidden="true"></span>';
        const yearStr = s.year != null && s.year !== '' ? String(s.year) : '—';
        let meta = yearStr;
        if (s.season != null && s.episode != null) meta += ` · S${s.season}E${s.episode}`;
        const head = suggestionSearchText(s);
        li.innerHTML = `<div class="os-suggestion-row">${posterHtml}<div class="os-suggestion-text"><span class="os-suggestion-title">${esc(head)}</span><span class="os-suggestion-meta">${esc(meta)}</span></div></div>`;
        li.addEventListener('mousedown', (e) => e.preventDefault());
        li.addEventListener('click', () => applyOpenSubtitlesSuggestion(s));
        UI.el.osSuggestionsList.appendChild(li);
        bindOsPosterImgOnError(
            li.querySelector('img.os-suggestion-poster'),
            'os-suggestion-poster os-suggestion-poster-placeholder',
        );
    }
    UI.el.osSuggestionsPanel.hidden = false;
    UI.el.osQuery.setAttribute('aria-expanded', 'true');
}

export function applyOpenSubtitlesSuggestion(s) {
    const { state } = UI;
    const label = suggestionSearchText(s);
    const y = s.year;
    const yr =
        y != null && y !== '' && Number.isFinite(Number(y)) ? Math.trunc(Number(y)) : null;
    state.osSearchRefine = {
        year: yr != null && yr >= 1870 && yr <= 2100 ? yr : null,
        imdbId: s.imdbId && String(s.imdbId).trim() ? String(s.imdbId).trim() : null,
    };
    UI.el.osQuery.value = label;
    hideOpenSubtitlesSuggestions();
    UI.el.osSuggestLive.textContent = `Selected ${label}`;
    void runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true, keepRefine: true });
}

export function scheduleFetchOpenSubtitlesSuggestions() {
    const { state } = UI;
    if (state.suggestDebounceTimer) clearTimeout(state.suggestDebounceTimer);
    state.suggestDebounceTimer = setTimeout(() => {
        state.suggestDebounceTimer = null;
        void fetchOpenSubtitlesSuggestions();
    }, OS_SUGGEST_DEBOUNCE_MS);
}

export async function fetchOpenSubtitlesSuggestions() {
    const { state } = UI;
    if (!isSearchMode() || !state.opensubtitlesConfigured) {
        hideOpenSubtitlesSuggestions();
        return;
    }
    const q = UI.el.osQuery.value.trim();
    if (q.length < OS_SUGGEST_MIN_LEN) {
        hideOpenSubtitlesSuggestions();
        return;
    }
    if (state.suggestAbort) state.suggestAbort.abort();
    state.suggestAbort = new AbortController();
    const ac = state.suggestAbort;
    UI.el.osSuggestLive.textContent = 'Loading suggestions…';
    try {
        const resp = await fetch(`${UI.api}/api/opensubtitles/suggestions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q }),
            signal: ac.signal,
        });
        const data = await resp.json().catch(() => ({}));
        if (state.suggestAbort !== ac) return;
        if (!resp.ok) {
            hideOpenSubtitlesSuggestions();
            UI.el.osSuggestLive.textContent = data.error || 'Suggestions failed';
            return;
        }
        const list = data.suggestions || [];
        UI.el.osSuggestLive.textContent =
            list.length === 0 ? 'No title suggestions' : `${list.length} suggestions`;
        renderOpenSubtitlesSuggestions(list);
    } catch (e) {
        if (e.name === 'AbortError') return;
        hideOpenSubtitlesSuggestions();
        UI.el.osSuggestLive.textContent = '';
    }
}

/**
 * @param {KeyboardEvent} e
 */
export function handleOsQueryKeydown(e) {
    const { state } = UI;
    const panelOpen = !UI.el.osSuggestionsPanel.hidden && state.suggestionRows.length > 0;
    if (e.key === 'Escape') {
        if (panelOpen) {
            e.preventDefault();
            hideOpenSubtitlesSuggestions();
            UI.el.osSuggestLive.textContent = 'Suggestions closed';
        }
        return;
    }
    if (e.key === 'ArrowDown') {
        if (panelOpen) {
            e.preventDefault();
            if (state.activeSuggestionIndex < state.suggestionRows.length - 1) {
                state.activeSuggestionIndex += 1;
            } else {
                state.activeSuggestionIndex = 0;
            }
            updateOpenSubtitlesSuggestionActiveClasses();
        }
        return;
    }
    if (e.key === 'ArrowUp') {
        if (panelOpen) {
            e.preventDefault();
            if (state.activeSuggestionIndex > 0) {
                state.activeSuggestionIndex -= 1;
            } else {
                state.activeSuggestionIndex = state.suggestionRows.length - 1;
            }
            updateOpenSubtitlesSuggestionActiveClasses();
        }
        return;
    }
    if (e.key === 'Enter') {
        if (panelOpen && state.activeSuggestionIndex >= 0) {
            e.preventDefault();
            applyOpenSubtitlesSuggestion(state.suggestionRows[state.activeSuggestionIndex]);
            return;
        }
        e.preventDefault();
        runOpenSubtitlesSearch({ refreshFromInput: true, resetPage: true });
    }
}
