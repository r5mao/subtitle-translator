import type {
    OpenSubtitlesRow,
    OpenSubtitlesSuggestion,
    OsSearchRefine,
} from './types/opensubtitles.js';

export const OS_MAX_PAGER_PAGES = 10;

export interface UiCallbacks {
    syncSubtitleSourcePanels: () => void;
    resetFileInput: () => void;
}

export interface UiElements {
    fileInput: HTMLInputElement;
    fileDisplay: HTMLElement;
    sourceSearch: HTMLInputElement;
    sourceUpload: HTMLInputElement;
    searchPanel: HTMLElement;
    uploadPanel: HTMLElement;
    opensubtitlesHint: HTMLElement;
    osQuery: HTMLInputElement;
    osSuggestionsPanel: HTMLElement;
    osSuggestionsList: HTMLUListElement;
    osSuggestLive: HTMLElement;
    osAnyLanguage: HTMLInputElement;
    osSearchBtn: HTMLButtonElement;
    osSearchStatus: HTMLElement;
    osLangChips: HTMLElement;
    osResultsTable: HTMLTableElement;
    osResultsBody: HTMLTableSectionElement;
    sourceLanguage: HTMLSelectElement;
    osPager: HTMLElement;
    osPerPageSelect: HTMLSelectElement;
    osPagePrev: HTMLButtonElement;
    osPageNext: HTMLButtonElement;
    osPageInfo: HTMLElement;
    languageSection: HTMLElement;
    translateToOtherLang: HTMLInputElement;
    translateOnlyFields: HTMLElement;
    translateToggleWrap: HTMLElement;
    subtitlePreviewPanel: HTMLElement;
    subtitlePreviewBg: HTMLImageElement;
    subtitlePreviewOrig: HTMLElement;
    subtitlePreviewTrans: HTMLElement;
    subtitlePreviewPinyin: HTMLElement;
    downloadSuccessMessage: HTMLElement;
    targetLanguage: HTMLSelectElement;
    dualLanguage: HTMLInputElement;
    translationForm: HTMLFormElement;
    translateBtn: HTMLButtonElement;
    loadingSpinner: HTMLElement;
    btnText: HTMLElement;
    translateConfirmDialog: HTMLDialogElement;
    translateConfirmFile: HTMLElement;
    translateConfirmFrom: HTMLElement;
    translateConfirmTo: HTMLElement;
    translateConfirmCancel: HTMLButtonElement;
    translateConfirmOk: HTMLButtonElement;
    errorMessage: HTMLElement;
    downloadSection: HTMLElement;
    progressBar: HTMLElement;
    progressFill: HTMLElement;
    progressPercent: HTMLElement;
    translationProgressTiming: HTMLElement;
    downloadBtn: HTMLAnchorElement;
    translationDuration: HTMLElement;
}

export interface UiState {
    opensubtitlesConfigured: boolean;
    rawSearchResults: OpenSubtitlesRow[];
    activeLangFilter: string;
    fetchedId: string | null;
    fetchedLabel: string;
    selectedOsFileId: string | null;
    fetchInProgressFileId: string | null;
    osLastSearchQuery: string;
    osLastSearchLang: string;
    osSearchRefine: OsSearchRefine;
    osSearchPage: number;
    osTotalPages: number | null;
    osTotalCount: number | null;
    suggestAbort: AbortController | null;
    suggestDebounceTimer: ReturnType<typeof setTimeout> | null;
    suggestionRows: OpenSubtitlesSuggestion[];
    activeSuggestionIndex: number;
    lastPreviewRow: OpenSubtitlesRow | null;
    previewRequestSeq: number;
    previewAbort: AbortController | null;
    previewDebounceTimer: ReturnType<typeof setTimeout> | null;
}

/** Shared UI state and DOM refs (filled by main.ts before handlers run). */
export const UI: {
    api: string;
    el: UiElements;
    callbacks: UiCallbacks;
    state: UiState;
} = {
    api: '',
    el: {} as UiElements,
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
