/** Title suggestion from `/api/opensubtitles/suggestions`. */
export interface OpenSubtitlesSuggestion {
    searchQuery?: string | null;
    title?: string;
    year?: string | number | null;
    season?: number | null;
    episode?: number | null;
    imdbId?: string | null;
    posterUrl?: string | null;
}

/** Flattened subtitle row from `/api/opensubtitles/search` or selection flow. */
export interface OpenSubtitlesRow {
    fileId: string | number;
    title?: string;
    year?: string | number | null;
    season?: number | null;
    episode?: number | null;
    release?: string;
    fileName?: string;
    language?: string;
    languageName?: string;
    downloads?: number;
    fps?: number;
    hearingImpaired?: boolean;
    machineTranslated?: boolean;
    posterUrl?: string | null;
    backdropUrl?: string | null;
}

export interface OsSearchRefine {
    year: number | null;
    imdbId: string | null;
}

export interface RunOpenSubtitlesSearchOptions {
    refreshFromInput?: boolean;
    resetPage?: boolean;
    keepRefine?: boolean;
}
