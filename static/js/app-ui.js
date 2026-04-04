/** Shared UI state and DOM refs (filled by main.js before handlers run). */

export const OS_MAX_PAGER_PAGES = 10;

export const UI = {
    api: '',
    el: {},
    /** Filled by main.js (avoids circular imports). */
    callbacks: {
        syncSubtitleSourcePanels: () => {},
        resetFileInput: () => {},
    },
    state: {
        opensubtitlesConfigured: false,
        rawSearchResults: [],
        activeLangFilter: 'all',
        fetchedId: null,
        fetchedLabel: '',
        selectedOsFileId: null,
        fetchInProgressFileId: null,
        osLastSearchQuery: '',
        osLastSearchLang: '',
        osSearchRefine: { year: null, imdbId: null },
        osSearchPage: 1,
        osTotalPages: null,
        osTotalCount: null,
        suggestAbort: null,
        suggestDebounceTimer: null,
        suggestionRows: [],
        activeSuggestionIndex: -1,
        lastPreviewRow: null,
        previewRequestSeq: 0,
        previewAbort: null,
        previewDebounceTimer: null,
    },
};
