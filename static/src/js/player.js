/* Portal-side player host. Owns the launch ticket and talks to the APIs. */
import { HostBridge } from "./host_protocol.js";

const API_TIMEOUT_MS = 10_000;

const frame = document.getElementById("game-frame");
if (frame) {
    const gameId = frame.dataset.gameId;
    const csrf = frame.dataset.csrf || "";
    const runtimeUrl = frame.dataset.src;
    const iframeOrigin = new URL(runtimeUrl).origin;
    let sessionId = "";
    let currentContext = {};
    let bridge = null;
    const submissionKeys = new Map();
    const submissionChains = new Map();
    let sessionSwitch = Promise.resolve();

    function headers(extra = {}) {
        return {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            ...extra,
        };
    }

    async function api(path, options = {}) {
        const canRetry = options.retry !== false;
        const requestOptions = { ...options };
        delete requestOptions.retry;
        let lastError;
        for (let attempt = 0; attempt < 3; attempt += 1) {
            try {
                const request = {
                    credentials: "same-origin",
                    ...requestOptions,
                };
                // A blackholed request must not block a restart forever: every
                // attempt gets its own timeout, then api() retries/fails.
                request.signal ??= AbortSignal.timeout(API_TIMEOUT_MS);
                const response = await fetch(path, request);
                let payload = null;
                if (response.status !== 204) {
                    payload = await response.json().catch(() => null);
                }
                if (response.ok) {
                    return { response, payload };
                }
                const error = new Error(payload?.message || "request failed");
                error.code = payload?.code || "E_INTERNAL";
                error.status = response.status;
                if (response.status < 500 || !canRetry || attempt === 2) {
                    throw error;
                }
                lastError = error;
            } catch (error) {
                if (error.status && error.status < 500) {
                    throw error;
                }
                lastError = error;
                if (!canRetry || attempt === 2) {
                    throw error;
                }
            }
            await new Promise((resolve) => globalThis.setTimeout(resolve, 200 * 2 ** attempt));
        }
        throw lastError;
    }

    async function createSession() {
        // Creation is safely retryable: a lost response can leave a CREATED
        // orphan, not an ACTIVE session; activation remains single-shot.
        const created = await api("/api/v1/sessions", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ game_id: gameId }),
        });
        const createdPayload = created.payload;
        const nonce = crypto.randomUUID().replaceAll("-", "");
        const activated = await api(
            `/api/v1/sessions/${createdPayload.sessionId}/activate`,
            {
                method: "POST",
                headers: headers(),
                body: JSON.stringify({
                    ticket: createdPayload.ticket,
                    binding_nonce: nonce,
                }),
                retry: false,
            },
        );
        sessionId = createdPayload.sessionId;
        currentContext = activated.payload.context;
        return { sessionId, seed: currentContext.seed, context: currentContext };
    }

    function submitResult(requestId, payload) {
        const requestSession = sessionId;
        const previous = submissionChains.get(requestSession) || Promise.resolve();
        const promise = previous
            .catch(() => undefined)
            .then(() => submitResultFor(requestSession, requestId, payload));
        submissionChains.set(requestSession, promise);
        promise
            .finally(() => {
                if (submissionChains.get(requestSession) === promise) {
                    submissionChains.delete(requestSession);
                }
            })
            .catch(() => undefined);
        return promise;
    }

    async function waitForSubmission(targetSession) {
        // A submission can arrive while we await an earlier one, so re-check
        // the chain instead of awaiting only the promise seen at entry.
        for (;;) {
            const pending = submissionChains.get(targetSession);
            if (!pending) {
                return;
            }
            await pending.catch(() => undefined);
            if (submissionChains.get(targetSession) === pending) {
                return;
            }
        }
    }

    async function submitResultFor(requestSession, requestId, payload) {
        const idempotencyKey = submissionKeys.get(requestSession) || crypto.randomUUID();
        submissionKeys.set(requestSession, idempotencyKey);
        try {
            // Final heartbeat closes the 30s credit gap before the server
            // compares duration_ms with credited_ms. A transient failure is
            // retried; an expired session is surfaced immediately.
            try {
                await api(`/api/v1/sessions/${requestSession}/heartbeat`, {
                    method: "POST",
                    headers: headers(),
                });
            } catch (error) {
                if (error.status === 410) {
                    throw error;
                }
            }
            const { payload: result } = await api(
                `/api/v1/sessions/${requestSession}/result`,
                {
                    method: "POST",
                    headers: headers({ "Idempotency-Key": idempotencyKey }),
                    body: JSON.stringify({
                        value: payload.value,
                        durationMs: payload.durationMs,
                        eventLog: payload.eventLog,
                        seed: payload.seed,
                        ...(payload.clientMeta ? { clientMeta: payload.clientMeta } : {}),
                    }),
                },
            );
            // A response from a superseded session must not touch the new round.
            if (sessionId !== requestSession) {
                return;
            }
            bridge.sendResult(requestId, {
                status: result.status,
                rank: result.rank ?? null,
                isPersonalBest: Boolean(result.is_personal_best),
                isRecord: Boolean(result.is_record),
                trustLevel: result.trust_level ?? "client_reported",
            });
        } catch (error) {
            if (sessionId !== requestSession) {
                return;
            }
            if (error.code === "E_GUEST_FORBIDDEN") {
                bridge.sendResult(requestId, {
                    status: "guest",
                    code: "E_GUEST_FORBIDDEN",
                    rank: null,
                    isPersonalBest: false,
                    isRecord: false,
                    trustLevel: "client_reported",
                });
                return;
            }
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function leaderboard(requestId, payload) {
        const requestSession = sessionId;
        try {
            if (payload.bestOnly) {
                const { payload: best } = await api(
                    `/api/v1/games/${gameId}/me/best`,
                    { headers: { Accept: "application/json" } },
                );
                if (sessionId !== requestSession) {
                    return;
                }
                const hasBest = best?.value !== null && best?.value !== undefined;
                bridge.sendLeaderboardData(requestId, {
                    entries: hasBest
                        ? [
                              {
                                  rank: best.rank,
                                  nickname: null,
                                  value: best.value,
                                  achievedAt: best.achieved_at ?? null,
                              },
                          ]
                        : [],
                    myRank: hasBest ? (best.rank ?? null) : null,
                });
                return;
            }
            const limit = payload.limit ?? 10;
            const { payload: board } = await api(
                `/api/v1/games/${gameId}/leaderboard?limit=${encodeURIComponent(limit)}`,
                { headers: { Accept: "application/json" } },
            );
            if (sessionId !== requestSession) {
                return;
            }
            bridge.sendLeaderboardData(requestId, {
                entries: (board.entries ?? []).map((entry) => ({
                    rank: entry.rank,
                    nickname: entry.nickname,
                    value: entry.value,
                    achievedAt: entry.achieved_at,
                    trustLevel: entry.trust_level,
                })),
                myRank: board.me?.rank ?? null,
            });
        } catch (error) {
            if (sessionId !== requestSession) {
                return;
            }
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function storage(requestId, payload) {
        const requestSession = sessionId;
        try {
            const { response, payload: current } = await api(
                `/api/v1/games/${gameId}/storage`,
                { headers: { Accept: "application/json" } },
            );
            if (sessionId !== requestSession) {
                return;
            }
            const data = current.data && typeof current.data === "object" ? current.data : {};
            if (payload.op === "get") {
                bridge.sendStorageData(requestId, {
                    value: Object.prototype.hasOwnProperty.call(data, payload.key)
                        ? data[payload.key]
                        : null,
                    revision: current.revision ?? 0,
                });
                return;
            }
            const next = { ...data };
            if (payload.op === "set") {
                next[payload.key] = payload.value;
            } else {
                delete next[payload.key];
            }
            const { payload: saved } = await api(
                `/api/v1/games/${gameId}/storage`,
                {
                    method: "PUT",
                    headers: headers({
                        "If-Match":
                            current.revision === 0
                                ? "*"
                                : response.headers.get("ETag") || `"${current.revision ?? 0}"`,
                    }),
                    body: JSON.stringify(next),
                },
            );
            if (sessionId !== requestSession) {
                return;
            }
            bridge.sendStorageData(requestId, {
                value: payload.op === "set" ? saved.data?.[payload.key] : null,
                revision: saved.revision ?? 0,
            });
        } catch (error) {
            if (sessionId !== requestSession) {
                return;
            }
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    function newSession(requestId) {
        // Serialize restarts: two quick newSession messages must not both
        // close the same session and create two replacements.
        sessionSwitch = sessionSwitch
            .catch(() => undefined)
            .then(() => performNewSession(requestId));
        return sessionSwitch;
    }

    async function performNewSession(requestId) {
        try {
            // Finish the previous active session before opening the next one.
            // Otherwise guest replays accumulate active sessions and hit the
            // three-session cap. An in-flight result for that session must
            // settle first: closing it early would turn a valid submission
            // into E_SESSION_EXPIRED and lose the score.
            const previousSession = sessionId;
            await waitForSubmission(previousSession);
            await closeSession(previousSession);
            submissionKeys.delete(previousSession);
            const created = await createSession();
            bridge.setSession(sessionId);
            bridge.sendSession(requestId, created);
        } catch (error) {
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function exitSession() {
        const current = sessionId;
        await waitForSubmission(current);
        await closeSession(current);
    }

    async function closeSession(targetSession = sessionId) {
        if (!targetSession) {
            return;
        }
        try {
            await api(`/api/v1/sessions/${targetSession}/close`, {
                method: "POST",
                headers: headers(),
                retry: false,
            });
        } catch {
            /* close is best-effort */
        }
    }

    function startHeartbeat() {
        globalThis.setInterval(() => {
            if (document.visibilityState !== "visible") {
                return;
            }
            void api(`/api/v1/sessions/${sessionId}/heartbeat`, {
                method: "POST",
                headers: headers(),
            }).catch(() => {
                /* session expiry is surfaced by the next SDK request */
            });
        }, 30000);
    }

    function showPlayerError(message) {
        const status = document.getElementById("player-status");
        if (status) {
            status.hidden = false;
            status.textContent = message;
        }
    }

    function createBridge() {
        return new HostBridge({
            iframe: frame,
            iframeOrigin,
            sessionId,
            onMessage(type, payload, requestId) {
                if (type === "ba:hello") {
                    bridge.sendContext(currentContext, requestId);
                } else if (type === "ba:submit") {
                    void submitResult(requestId, payload);
                } else if (type === "ba:leaderboard") {
                    void leaderboard(requestId, payload);
                } else if (type === "ba:storage") {
                    void storage(requestId, payload);
                } else if (type === "ba:newSession") {
                    void newSession(requestId);
                } else if (type === "ba:exit") {
                    void exitSession();
                }
            },
        });
    }

    async function start() {
        try {
            const created = await createSession();
            bridge = createBridge();
            startHeartbeat();
            frame.src = `${runtimeUrl}&s=${encodeURIComponent(created.sessionId)}`;
        } catch (error) {
            showPlayerError(error.message || "Не удалось начать игру");
        }
    }

    document.addEventListener("visibilitychange", () => {
        if (!bridge) {
            return;
        }
        if (document.visibilityState === "visible") {
            bridge.sendResume({});
        } else {
            bridge.sendPause({});
        }
    });

    function closeOnPageHide() {
        if (!sessionId) {
            return;
        }
        // A submit in flight finishes the session itself; closing now would
        // race it and turn a valid result into E_SESSION_EXPIRED. Abandoned
        // sessions without a submit still get the best-effort close.
        if (submissionChains.get(sessionId)) {
            return;
        }
        const url = `/api/v1/sessions/${sessionId}/close`;
        // sendBeacon cannot attach the CSRF header required by the API;
        // keepalive fetch is the reliable same-origin close on pagehide.
        if (typeof fetch === "function") {
            void fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-CSRFToken": csrf },
                keepalive: true,
            }).catch(() => {
                /* pagehide close is best-effort */
            });
            return;
        }
        if (typeof navigator.sendBeacon === "function") {
            navigator.sendBeacon(
                url,
                new URLSearchParams({ csrfmiddlewaretoken: csrf }),
            );
        }
    }

    window.addEventListener("pagehide", closeOnPageHide);

    void start();
}
