import { UI } from './app-ui.js';
import {
    bindOsPosterImgOnError,
    displayLanguageLabel,
    languageCounts,
    rowInfo,
    titleCellWithPoster,
} from './opensubtitles-format.js';
import { esc } from './string-utils.js';
import { applySourceFromOpenSubtitlesRow, validateLanguages } from './language-and-source-ui.js';
import { hideSubtitlePreview, refreshSubtitlePreview } from './subtitle-preview.js';
import type { OpenSubtitlesRow } from './types/opensubtitles.js';

interface FetchSubtitleResponse {
    error?: string;
    fetchedId?: string;
    filename?: string;
}

export function clearOpenSubtitlesSelection(): void {
    const { state } = UI;
    state.fetchedId = null;
    state.fetchedLabel = '';
    state.selectedOsFileId = null;
    state.fetchInProgressFileId = null;
    state.lastPreviewRow = null;
    hideSubtitlePreview();
    validateLanguages();
}

export function renderLangChips(rows: OpenSubtitlesRow[]): void {
    const { state } = UI;
    const counts = languageCounts(rows);
    const keys = Array.from(counts.keys()).sort();
    if (keys.length <= 1) {
        UI.el.osLangChips.hidden = true;
        UI.el.osLangChips.innerHTML = '';
        return;
    }
    UI.el.osLangChips.hidden = false;
    UI.el.osLangChips.innerHTML = '';
    const addChip = (code: string, label: string, count: number | null): void => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'lang-chip' + (state.activeLangFilter === code ? ' active' : '');
        b.textContent = count != null ? `${label} (${count})` : label;
        b.addEventListener('click', () => {
            state.activeLangFilter = code;
            renderLangChips(state.rawSearchResults);
            filterAndRenderResults();
        });
        UI.el.osLangChips.appendChild(b);
    };
    addChip('all', 'All languages', rows.length);
    for (const k of keys) {
        addChip(k, displayLanguageLabel(k, rows), counts.get(k)!);
    }
}

export function filterAndRenderResults(): void {
    const { state } = UI;
    UI.el.osResultsBody.innerHTML = '';
    let rows = state.rawSearchResults;
    if (state.activeLangFilter !== 'all') {
        rows = rows.filter((r) => (r.language || '') === state.activeLangFilter);
    }
    if (state.fetchedId && state.selectedOsFileId != null) {
        const visible = new Set(rows.map((r) => String(r.fileId)));
        if (!visible.has(String(state.selectedOsFileId))) {
            clearOpenSubtitlesSelection();
        }
    }
    if (!rows.length) {
        UI.el.osResultsTable.hidden = true;
        return;
    }
    UI.el.osResultsTable.hidden = false;
    for (const r of rows) {
        const fid = String(r.fileId);
        const tr = document.createElement('tr');
        tr.classList.add('os-result-row');
        const isSelected = Boolean(
            state.fetchedId && state.selectedOsFileId != null && String(state.selectedOsFileId) === fid,
        );
        const isFetching =
            state.fetchInProgressFileId != null && String(state.fetchInProgressFileId) === fid;
        if (isSelected) tr.classList.add('os-row-selected');
        if (isFetching) tr.classList.add('os-row-fetching');
        tr.tabIndex = 0;
        const rowLabel = r.title || r.fileName || r.release || fid;
        tr.setAttribute(
            'aria-label',
            isFetching
                ? `Loading subtitle: ${rowLabel}`
                : isSelected
                  ? `Selected: ${rowLabel}. Activate to clear selection.`
                  : `Select subtitle: ${rowLabel}`,
        );
        tr.innerHTML = `
            <td>${titleCellWithPoster(UI.api, r)}</td>
            <td>${esc(r.languageName || r.language || '')}</td>
            <td class="cell-muted">${esc(rowInfo(r))}</td>
        `;
        bindOsPosterImgOnError(tr.querySelector('img.os-poster-thumb'), 'os-poster-placeholder');
        tr.addEventListener('click', () => selectSubtitleFile(r.fileId, r));
        tr.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                selectSubtitleFile(r.fileId, r);
            }
        });
        UI.el.osResultsBody.appendChild(tr);
    }
}

export async function selectSubtitleFile(fileId: string | number, row: OpenSubtitlesRow): Promise<void> {
    const { state } = UI;
    const fid = String(fileId);
    if (state.fetchedId && state.selectedOsFileId != null && String(state.selectedOsFileId) === fid) {
        clearOpenSubtitlesSelection();
        filterAndRenderResults();
        return;
    }
    if (state.fetchInProgressFileId != null) {
        return;
    }
    const label = row.fileName || row.title || String(fileId);
    state.fetchInProgressFileId = fid;
    filterAndRenderResults();
    try {
        const resp = await fetch(`${UI.api}/api/opensubtitles/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: fileId }),
        });
        const data = (await resp.json().catch(() => ({}))) as FetchSubtitleResponse;
        if (!resp.ok) {
            throw new Error(data.error || resp.statusText || 'Fetch failed');
        }
        state.fetchedId = data.fetchedId ?? null;
        state.fetchedLabel = data.filename || label;
        state.selectedOsFileId = fid;
        applySourceFromOpenSubtitlesRow(row.language);
        UI.el.osSearchStatus.textContent = '';
        state.lastPreviewRow = row;
        void refreshSubtitlePreview(row);
    } catch (e: unknown) {
        console.error(e);
        const msg = e instanceof Error ? e.message : String(e);
        UI.el.osSearchStatus.textContent = msg;
        state.selectedOsFileId = null;
        state.fetchedId = null;
        state.fetchedLabel = '';
        validateLanguages();
    } finally {
        state.fetchInProgressFileId = null;
        filterAndRenderResults();
    }
}
