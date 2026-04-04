/**
 * API origin for fetch/SSE. Empty string = same host/port as the page (e.g. python app.py).
 * If you use a static server only (e.g. python -m http.server 8080), set a meta tag:
 *   <meta name="subtitle-translator-api-base" content="http://127.0.0.1:5000">
 * or we default localhost:5000 when the page is on :8080 or :5500 (Live Server).
 */
export function getApiBase() {
    const meta = document.querySelector('meta[name="subtitle-translator-api-base"]');
    if (meta) {
        const v = (meta.getAttribute('content') || '').trim();
        if (v) return v.replace(/\/$/, '');
    }
    const port = window.location.port;
    const host = window.location.hostname;
    if (
        (port === '8080' || port === '5500' || port === '3000') &&
        (host === 'localhost' || host === '127.0.0.1')
    ) {
        return `${window.location.protocol}//${host}:5000`;
    }
    return '';
}
