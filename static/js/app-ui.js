export const OS_MAX_PAGER_PAGES = 10;
/** Shared UI state and DOM refs (filled by main.ts before handlers run). */
export const UI = {
    api: '',
    el: {},
    callbacks: {
        syncSubtitleSourcePanels: () => { },
        resetFileInput: () => { },
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
//# sourceMappingURL=app-ui.js.map