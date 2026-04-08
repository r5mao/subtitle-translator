export function formatDurationMmSs(totalSec: number): string {
    const s = Math.max(0, Math.floor(totalSec));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, '0')}`;
}

/** Elapsed wall time + ETA from linear extrapolation of percent complete. */
export function buildTranslationTimingText(elapsedSec: number, progress: number): string {
    const elapsedStr = formatDurationMmSs(elapsedSec);
    if (progress >= 100) {
        return `Finished in ${elapsedStr}`;
    }
    let text = `Elapsed ${elapsedStr}`;
    if (progress <= 0) {
        return `${text} · …`;
    }
    if (progress < 2) {
        return `${text} · Estimating time remaining…`;
    }
    const etaSec = (elapsedSec * (100 - progress)) / progress;
    if (!Number.isFinite(etaSec) || etaSec <= 0) {
        return text;
    }
    if (etaSec >= 3600) {
        return `${text} · ~${formatDurationMmSs(3600)}+ left`;
    }
    return `${text} · ~${formatDurationMmSs(etaSec)} left`;
}
