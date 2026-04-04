import { UI } from './app-ui.js';
import { normalizeHttpUrl, posterProxySrc } from './opensubtitles-format.js';
import { wantsTranslate } from './language-and-source-ui.js';

export function hideSubtitlePreview() {
    UI.el.subtitlePreviewPanel.hidden = true;
    UI.el.subtitlePreviewBg.removeAttribute('src');
    UI.el.subtitlePreviewBg.hidden = true;
    UI.el.subtitlePreviewOrig.textContent = '';
    UI.el.subtitlePreviewTrans.textContent = '';
    UI.el.subtitlePreviewTrans.hidden = true;
    UI.el.subtitlePreviewPinyin.textContent = '';
    UI.el.subtitlePreviewPinyin.hidden = true;
}

function applyPreviewPayload(data) {
    const orig = Array.isArray(data.originalLines)
        ? data.originalLines
        : Array.isArray(data.sampleLines)
          ? data.sampleLines
          : [];
    UI.el.subtitlePreviewOrig.textContent = orig.length ? orig.join(' ') : '—';
    const trans = data.translatedLines;
    if (Array.isArray(trans) && trans.length) {
        UI.el.subtitlePreviewTrans.textContent = trans.join(' ');
        UI.el.subtitlePreviewTrans.hidden = false;
    } else {
        UI.el.subtitlePreviewTrans.textContent = '';
        UI.el.subtitlePreviewTrans.hidden = true;
    }
    const pin = data.pinyinLines;
    if (Array.isArray(pin) && pin.length) {
        UI.el.subtitlePreviewPinyin.textContent = pin.join(' ');
        UI.el.subtitlePreviewPinyin.hidden = false;
    } else {
        UI.el.subtitlePreviewPinyin.textContent = '';
        UI.el.subtitlePreviewPinyin.hidden = true;
    }
}

export function scheduleSubtitlePreviewRefresh() {
    const { state } = UI;
    if (!state.fetchedId || !state.lastPreviewRow) return;
    clearTimeout(state.previewDebounceTimer);
    state.previewDebounceTimer = setTimeout(() => {
        void refreshSubtitlePreview(state.lastPreviewRow);
    }, 320);
}

export async function refreshSubtitlePreview(row) {
    const { state } = UI;
    if (!state.fetchedId) {
        hideSubtitlePreview();
        return;
    }
    const bgRaw = (row && row.backdropUrl) || (row && row.posterUrl);
    const url = normalizeHttpUrl(bgRaw);
    if (url && /^https?:\/\//i.test(url)) {
        UI.el.subtitlePreviewBg.src = posterProxySrc(UI.api, url);
        UI.el.subtitlePreviewBg.hidden = false;
    } else {
        UI.el.subtitlePreviewBg.removeAttribute('src');
        UI.el.subtitlePreviewBg.hidden = true;
    }
    state.previewRequestSeq += 1;
    const seq = state.previewRequestSeq;
    if (state.previewAbort) state.previewAbort.abort();
    state.previewAbort = new AbortController();
    try {
        const prev = await fetch(
            `${UI.api}/api/opensubtitles/fetched/${encodeURIComponent(state.fetchedId)}/preview`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sourceLanguage: UI.el.sourceLanguage.value,
                    targetLanguage: UI.el.targetLanguage.value,
                    dualLanguage: UI.el.dualLanguage.checked,
                    wantsTranslate: wantsTranslate(),
                }),
                signal: state.previewAbort.signal,
            },
        );
        if (seq !== state.previewRequestSeq) return;
        const data = await prev.json().catch(() => ({}));
        if (!prev.ok) throw new Error(data.error || 'Preview failed');
        applyPreviewPayload(data);
        UI.el.subtitlePreviewPanel.hidden = false;
    } catch (e) {
        if (e.name === 'AbortError') return;
        if (seq !== state.previewRequestSeq) return;
        UI.el.subtitlePreviewOrig.textContent = state.fetchedLabel || 'Subtitle ready';
        UI.el.subtitlePreviewTrans.hidden = true;
        UI.el.subtitlePreviewPinyin.hidden = true;
        UI.el.subtitlePreviewPanel.hidden = false;
    }
}
