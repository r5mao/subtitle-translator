import { attrEscapeUrl, esc } from './string-utils.js';

export function languageCounts(rows) {
    const m = new Map();
    for (const r of rows) {
        const k = r.language || '?';
        m.set(k, (m.get(k) || 0) + 1);
    }
    return m;
}

export function displayLanguageLabel(code, rows) {
    if (!code || code === '?') return code;
    for (const r of rows) {
        if ((r.language || '') === code && r.languageName) {
            return r.languageName;
        }
    }
    return code;
}

/** Map OpenSubtitles subtitle language code to #sourceLanguage option value. */
export const OS_LANG_TO_UI_SOURCE = {
    en: 'en',
    es: 'es',
    fr: 'fr',
    de: 'de',
    it: 'it',
    pt: 'pt',
    'pt-br': 'pt',
    'pt-pt': 'pt',
    ru: 'ru',
    'zh-cn': 'zh-cn',
    'zh-tw': 'zh-tw',
    zh: 'zh-cn',
    cmn: 'zh-cn',
    ja: 'ja',
    ko: 'ko',
    ar: 'ar',
    hi: 'hi',
    nl: 'nl',
    sv: 'sv',
    da: 'da',
    no: 'no',
    fi: 'fi',
    pl: 'pl',
    tr: 'tr',
    he: 'he',
};

export function opensubtitlesLangToUiSource(code) {
    if (!code || typeof code !== 'string') return null;
    const c = code.trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(OS_LANG_TO_UI_SOURCE, c)) {
        return OS_LANG_TO_UI_SOURCE[c];
    }
    if (c.startsWith('pt')) return 'pt';
    return null;
}

export function rowInfo(r) {
    const parts = [];
    const dl = r.downloads;
    if (typeof dl === 'number' && Number.isFinite(dl) && dl >= 0) {
        parts.push(`${dl} dl`);
    }
    const fps = r.fps;
    if (typeof fps === 'number' && Number.isFinite(fps) && fps > 0) {
        parts.push(`${fps} fps`);
    }
    if (r.hearingImpaired) parts.push('HI');
    if (r.machineTranslated) parts.push('MT');
    return parts.length ? parts.join(' · ') : '—';
}

export function titleCell(r) {
    let t = r.title || '';
    if (r.year) t += ` (${r.year})`;
    if (r.season != null && r.episode != null) {
        t += ` S${r.season}E${r.episode}`;
    }
    let html = t ? esc(t) : '';
    if (r.release) html += `<div class="cell-muted">${esc(r.release)}</div>`;
    if (r.fileName) html += `<div class="cell-muted">${esc(r.fileName)}</div>`;
    return html || '—';
}

export function normalizeHttpUrl(raw) {
    if (raw == null) return '';
    let s = String(raw).trim();
    if (!s) return '';
    if (s.startsWith('//')) s = `https:${s}`;
    if (/^https?:\/\//i.test(s)) return s;
    /* Match server _maybe_absolutize_opensubtitles_image_url so relative poster paths still proxy. */
    if (s.startsWith('/') && !s.includes('/../')) {
        const low = s.toLowerCase().split('?', 1)[0];
        if (
            /\.(jpe?g|png|webp|gif|jfif)$/i.test(low) ||
            low.includes('/pictures/') ||
            low.includes('/posters/') ||
            low.includes('/poster') ||
            low.includes('/img/')
        ) {
            return `https://www.opensubtitles.com${s}`;
        }
    }
    return '';
}

/** Same-origin proxy avoids CDN hotlink / referrer blocks on poster thumbnails. */
export function posterProxySrc(api, remoteUrl) {
    const base = (api || '').replace(/\/$/, '');
    const q = encodeURIComponent(remoteUrl);
    return `${base}/api/opensubtitles/poster-image?url=${q}`;
}

/**
 * Text to put in the search box after picking a suggestion (matches server clean_work_search_query).
 * API sends searchQuery; older servers may omit it — strip redundant "YEAR -" / "(YEAR)" from title.
 */
export function suggestionSearchText(s) {
    const fromApi = s && s.searchQuery != null ? String(s.searchQuery).trim() : '';
    if (fromApi) return fromApi;
    let t = String((s && s.title) || '').trim();
    const y = s && s.year;
    if (y != null && y !== '') {
        const ys = String(y).trim();
        if (/^\d{4}$/.test(ys)) {
            t = t.replace(new RegExp(`^\\s*${ys}\\s*-\\s*`, 'i'), '').trim();
            t = t.replace(new RegExp(`\\s*\\(\\s*${ys}\\s*\\)\\s*$`, 'i'), '').trim();
        }
    }
    return t.replace(/\s+/g, ' ').trim() || String((s && s.title) || '').trim();
}

export function bindOsPosterImgOnError(img, placeholderClass) {
    if (!img || img.tagName !== 'IMG') return;
    img.addEventListener('error', function handleOsPosterImgError() {
        img.removeEventListener('error', handleOsPosterImgError);
        const ph = document.createElement('span');
        ph.className = placeholderClass;
        ph.setAttribute('aria-hidden', 'true');
        img.replaceWith(ph);
    });
}

export function titleCellWithPoster(api, r) {
    const url = normalizeHttpUrl(r.posterUrl);
    const useProxy = url && /^https?:\/\//i.test(url);
    const src = useProxy ? posterProxySrc(api, url) : '';
    const posterHtml = src
        ? `<img class="os-poster-thumb" src="${attrEscapeUrl(src)}" alt="" loading="lazy">`
        : '<span class="os-poster-placeholder" aria-hidden="true"></span>';
    return `<div class="os-title-cell">${posterHtml}<div class="os-title-cell-text">${titleCell(r)}</div></div>`;
}
