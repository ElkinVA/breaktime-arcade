/* Portal-side player host. Owns the launch ticket and talks to the APIs. */
import { HostBridge } from "./host_protocol.js";

const frame = document.getElementById("game-frame");
if (frame) {
    const context = JSON.parse(frame.dataset.context || "{}");
    const gameId = frame.dataset.gameId;
    const csrf = frame.dataset.csrf || "";
    const runtimeUrl = frame.dataset.src;
    const iframeOrigin = new URL(runtimeUrl).origin;
    let sessionId = frame.dataset.sessionId;
    let currentContext = context;

    function headers(extra = {}) {
        return {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            ...extra,
        };
    }

    async function api(path, options = {}) {
        let lastError;
        for (let attempt = 0; attempt < 3; attempt += 1) {
            try {
                const response = await fetch(path, {
                    credentials: "same-origin",
                    ...options,
                });
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
                if (response.status < 500 || attempt === 2) {
                    throw error;
                }
                lastError = error;
            } catch (error) {
                if (error.status && error.status < 500) {
                    throw error;
                }
                lastError = error;
                if (attempt === 2) {
                    throw error;
                }
            }
            await new Promise((resolve) => globalThis.setTimeout(resolve, 200 * 2 ** attempt));
        }
        throw lastError;
    }

    async function createSession() {
        const created = await api("/api/v1/sessions", {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ game_id: gameId }),
        });
        const createdPayload = created.payload;
        const nonce = crypto.randomUUID().replaceAll("-", "");
        const activated = await api(
            `/api/v1/sessions/${createdPayload.session_id}/activate`,
            {
                method: "POST",
                headers: headers(),
                body: JSON.stringify({
                    ticket: createdPayload.ticket,
                    binding_nonce: nonce,
                }),
            },
        );
        sessionId = createdPayload.session_id;
        currentContext = activated.payload.context;
        bridge.setSession(sessionId);
        return { sessionId, seed: currentContext.seed, context: currentContext };
    }

    async function submitResult(requestId, payload) {
        try {
            const { payload: result } = await api(
                `/api/v1/sessions/${sessionId}/result`,
                {
                    method: "POST",
                    headers: headers({ "Idempotency-Key": crypto.randomUUID() }),
                    body: JSON.stringify({
                        value: payload.value,
                        durationMs: payload.durationMs,
                        eventLog: payload.eventLog,
                        seed: payload.seed,
                        ...(payload.clientMeta ? { clientMeta: payload.clientMeta } : {}),
                    }),
                },
            );
            bridge.sendResult(requestId, {
                status: result.status,
                rank: result.rank ?? null,
                isPersonalBest: Boolean(result.is_personal_best),
                isRecord: Boolean(result.is_record),
                trustLevel: result.trust_level ?? "client_reported",
            });
        } catch (error) {
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
        try {
            if (payload.bestOnly) {
                const { payload: best } = await api(
                    `/api/v1/games/${gameId}/me/best`,
                    { headers: { Accept: "application/json" } },
                );
                bridge.sendLeaderboardData(requestId, {
                    value: best.value ?? null,
                    achievedAt: best.achieved_at ?? null,
                    rank: best.rank ?? null,
                });
                return;
            }
            const limit = payload.limit ?? 10;
            const { payload: board } = await api(
                `/api/v1/games/${gameId}/leaderboard?limit=${encodeURIComponent(limit)}`,
                { headers: { Accept: "application/json" } },
            );
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
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function storage(requestId, payload) {
        try {
            const { response, payload: current } = await api(
                `/api/v1/games/${gameId}/storage`,
                { headers: { Accept: "application/json" } },
            );
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
            bridge.sendStorageData(requestId, {
                value: payload.op === "set" ? saved.data?.[payload.key] : null,
                revision: saved.revision ?? 0,
            });
        } catch (error) {
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function newSession(requestId) {
        try {
            const created = await createSession();
            bridge.sendSession(requestId, created);
        } catch (error) {
            bridge.sendError(requestId, error.code || "E_INTERNAL", error.message);
        }
    }

    async function closeSession() {
        try {
            await api(`/api/v1/sessions/${sessionId}/close`, {
                method: "POST",
                headers: headers(),
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

    const bridge = new HostBridge({
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
                void closeSession();
            }
        },
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            bridge.sendResume({});
        } else {
            bridge.sendPause({});
        }
    });

    startHeartbeat();
    frame.src = runtimeUrl;
}
