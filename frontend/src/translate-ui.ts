import { UI } from './app-ui.js';
import { buildTranslationTimingText } from './timing-utils.js';
import { isSearchMode, updatePrimaryButtonLabel } from './language-and-source-ui.js';
export function selectedOptionLabel(selectEl: HTMLSelectElement): string {
    const opt = selectEl.options[selectEl.selectedIndex];
    return opt ? opt.textContent?.trim() || '' : '';
}

export async function runDownloadOriginal(): Promise<void> {
    const { state } = UI;
    const errorMessage = UI.el.errorMessage;
    const downloadSection = UI.el.downloadSection;
    const progressBar = UI.el.progressBar;
    const progressPercent = UI.el.progressPercent;

    errorMessage.style.display = 'none';
    downloadSection.style.display = 'none';
    progressBar.style.display = 'none';
    progressPercent.style.display = 'none';

    UI.el.translateBtn.disabled = true;
    UI.el.loadingSpinner.style.display = 'inline-block';
    UI.el.btnText.textContent = 'Downloading...';

    try {
        const url = `${UI.api}/api/opensubtitles/fetched/${encodeURIComponent(state.fetchedId!)}/download`;
        const resp = await fetch(url);
        if (!resp.ok) {
            const errText = await resp.text();
            let msg = errText;
            try {
                const j = JSON.parse(errText) as { error?: string };
                if (j.error) msg = j.error;
            } catch {
                /* plain */
            }
            throw new Error(msg || resp.statusText || 'Download failed');
        }
        const blob = await resp.blob();
        const objUrl = URL.createObjectURL(blob);
        UI.el.downloadBtn.href = objUrl;
        UI.el.downloadBtn.download = state.fetchedLabel || 'subtitle.srt';
        UI.el.downloadSuccessMessage.textContent = 'Subtitle file ready.';
        UI.el.downloadBtn.textContent = '📥 Download original subtitle';
        UI.el.translationDuration.textContent = '';
        downloadSection.style.display = 'block';
        downloadSection.scrollIntoView({ behavior: 'smooth' });
    } catch (error: unknown) {
        console.error('Download error:', error);
        let msg = error instanceof Error ? error.message : String(error);
        try {
            const parsed = JSON.parse(msg) as { error?: string };
            if (parsed?.error) msg = parsed.error;
        } catch {
            /* plain */
        }
        const networkFailure =
            error instanceof TypeError ||
            msg === 'Failed to fetch' ||
            /networkerror when attempting to fetch resource/i.test(msg);
        if (networkFailure) {
            errorMessage.textContent =
                'Could not reach the server. Open this app via your Flask URL (e.g. http://127.0.0.1:5000/), not as a file:// page.';
        } else {
            errorMessage.textContent = `Error: ${msg}`;
        }
        errorMessage.style.display = 'block';
    } finally {
        UI.el.translateBtn.disabled = false;
        UI.el.loadingSpinner.style.display = 'none';
        updatePrimaryButtonLabel();
    }
}

interface TaskApiResponse {
    taskId?: string;
}

interface TranslateApiResponse {
    success?: boolean;
    downloadUrl?: string;
    error?: string;
    translationDuration?: string;
    filename?: string;
}

export async function runTranslation(): Promise<void> {
    const { state } = UI;
    const errorMessage = UI.el.errorMessage;
    const downloadSection = UI.el.downloadSection;
    const progressBar = UI.el.progressBar;
    const progressFill = UI.el.progressFill;
    const progressPercent = UI.el.progressPercent;
    const translationProgressTiming = UI.el.translationProgressTiming;

    errorMessage.style.display = 'none';
    downloadSection.style.display = 'none';
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressPercent.style.display = 'block';
    progressPercent.textContent = '0%';

    const translationStartMs = Date.now();
    let translationLastProgress = 0;
    let translationDoneAtMs: number | null = null;
    let translationTimingIntervalId: ReturnType<typeof setInterval> | null = null;
    function renderTranslationTiming(): void {
        const elapsedSec =
            translationLastProgress >= 100 && translationDoneAtMs != null
                ? (translationDoneAtMs - translationStartMs) / 1000
                : (Date.now() - translationStartMs) / 1000;
        translationProgressTiming.textContent = buildTranslationTimingText(
            elapsedSec,
            translationLastProgress,
        );
    }
    translationProgressTiming.hidden = false;
    renderTranslationTiming();
    translationTimingIntervalId = setInterval(renderTranslationTiming, 250);

    UI.el.translateBtn.disabled = true;
    UI.el.loadingSpinner.style.display = 'inline-block';
    UI.el.btnText.textContent = 'Translating...';

    try {
        const taskResponse = await fetch(`${UI.api}/api/task`);

        if (!taskResponse.ok) {
            const errorText = await taskResponse.text();
            throw new Error(errorText || 'Server error');
        }

        const taskJson = (await taskResponse.json()) as TaskApiResponse;
        const taskId = taskJson.taskId;
        if (!taskId) throw new Error('Missing taskId');

        const formData = new FormData();
        formData.append('sourceLanguage', UI.el.sourceLanguage.value);
        formData.append('targetLanguage', UI.el.targetLanguage.value);
        formData.append('dualLanguage', UI.el.dualLanguage.checked ? 'true' : 'false');
        formData.append('taskId', taskId);
        if (state.fetchedId && isSearchMode()) {
            formData.append('fetchedId', state.fetchedId);
        } else {
            const file = UI.el.fileInput.files?.[0];
            if (!file) throw new Error('No file selected');
            formData.append('srtFile', file);
        }

        const evtSource = new EventSource(`${UI.api}/api/translate/progress/${taskId}`);
        const ssePromise = new Promise<void>((resolve, reject) => {
            let completed = false;
            progressBar.style.display = 'block';
            progressFill.style.width = '0%';
            evtSource.onmessage = function (event: MessageEvent<string>) {
                let progress = parseInt(event.data, 10);
                if (isNaN(progress)) progress = 0;
                translationLastProgress = progress;
                if (progress >= 100 && translationDoneAtMs == null) {
                    translationDoneAtMs = Date.now();
                }
                renderTranslationTiming();
                progressFill.style.width = progress + '%';
                progressFill.setAttribute('aria-valuenow', String(progress));
                progressPercent.textContent = progress + '%';
                if (progress >= 100 && !completed) {
                    completed = true;
                    evtSource.close();
                    resolve();
                }
            };
            evtSource.onerror = function () {
                evtSource.close();
                reject(new Error('Lost connection to progress server.'));
            };
        });

        const translatePromise = (async () => {
            const response = await fetch(`${UI.api}/api/translate`, {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || 'Server error');
            }
            const json = (await response.json()) as TranslateApiResponse;
            if (!json.success || !json.downloadUrl) {
                throw new Error(json.error || 'Translation failed');
            }
            return json;
        })();

        try {
            await ssePromise;
        } catch (sseErr: unknown) {
            console.warn(sseErr instanceof Error ? sseErr.message : sseErr);
        }

        const json = await translatePromise;
        const downloadUrl = json.downloadUrl;
        const translationDuration = json.translationDuration;
        const serverFilename = json.filename;

        const srtResponse = await fetch(`${UI.api}${downloadUrl}`);
        if (!srtResponse.ok) {
            throw new Error('Failed to download translated subtitle file');
        }
        const translatedContent = await srtResponse.text();

        const blob = new Blob([translatedContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        UI.el.downloadBtn.href = url;
        const targetLang = String(formData.get('targetLanguage') ?? '');
        let newFileName = serverFilename;
        if (!newFileName) {
            const originalFileName = isSearchMode()
                ? state.fetchedLabel || 'subtitle.srt'
                : UI.el.fileInput.files![0]!.name;
            const dualSuffix = UI.el.dualLanguage.checked ? '_dual' : '';
            newFileName = originalFileName.replace(
                /\.(srt|ass|ssa|sub)$/i,
                `_GoogleTrans_${targetLang}${dualSuffix}.$1`,
            );
            if (newFileName === originalFileName) {
                newFileName = originalFileName + `_GoogleTrans_${targetLang}${dualSuffix}`;
            }
        }
        UI.el.downloadBtn.download = newFileName;
        UI.el.downloadSuccessMessage.textContent = 'Translation completed successfully! 🎉';
        UI.el.downloadBtn.textContent = 'Download translated subtitle';

        if (translationDuration) {
            UI.el.translationDuration.textContent = `Time for translation to complete: ${translationDuration}`;
        } else {
            UI.el.translationDuration.textContent = '';
        }

        if (isSearchMode()) {
            // #region agent log
            fetch('http://127.0.0.1:7505/ingest/90df03b9-60a9-49fb-a632-90c7d1c30d39', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Debug-Session-Id': '090bbc',
                },
                body: JSON.stringify({
                    sessionId: '090bbc',
                    runId: 'post-fix',
                    hypothesisId: 'H1',
                    location: 'translate-ui.ts:afterTranslateSuccess',
                    message: 'Keeping OpenSubtitles selection for re-translate (no releaseFetchedAfterTranslate)',
                    data: {
                        fetchedId: state.fetchedId,
                        selectedOsFileId: state.selectedOsFileId,
                    },
                    timestamp: Date.now(),
                }),
            }).catch(() => {});
            // #endregion
        }

        downloadSection.style.display = 'block';
        downloadSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error: unknown) {
        console.error('Translation error:', error);
        let msg = error instanceof Error ? error.message : String(error);
        try {
            const parsed = JSON.parse(msg) as { error?: string };
            if (parsed?.error) msg = parsed.error;
        } catch {
            /* plain text */
        }
        const networkFailure =
            error instanceof TypeError ||
            msg === 'Failed to fetch' ||
            /networkerror when attempting to fetch resource/i.test(msg) ||
            msg.includes('Lost connection to progress server');
        if (networkFailure) {
            errorMessage.textContent =
                'Could not reach the translation server. Open this app at http://127.0.0.1:5000/ after running python app.py (do not open index.html as a file:// page). If you use another dev port or HTTPS, set the subtitle-translator-api-base meta tag in index.html to your Flask URL (e.g. http://127.0.0.1:5000). Note: an HTTPS page cannot call an HTTP API (mixed content).';
        } else {
            errorMessage.textContent = `Error: ${msg}. Please check your file format (SRT, ASS, SSA, SUB) and try again.`;
        }
        errorMessage.style.display = 'block';
        progressFill.style.width = '0%';
    } finally {
        if (translationTimingIntervalId != null) {
            clearInterval(translationTimingIntervalId);
            translationTimingIntervalId = null;
        }
        translationProgressTiming.hidden = true;
        translationProgressTiming.textContent = '';
        UI.el.translateBtn.disabled = false;
        UI.el.loadingSpinner.style.display = 'none';
        updatePrimaryButtonLabel();
        setTimeout(() => {
            progressBar.style.display = 'none';
            progressFill.style.width = '0%';
            progressPercent.style.display = 'none';
            progressPercent.textContent = '0%';
        }, 1000);
    }
}
