(function () {
    "use strict";

    const status = document.getElementById("probe-status");
    const contextNode = document.getElementById("probe-context");

    function setStatus(state, text) {
        status.dataset.state = state;
        status.textContent = text;
    }

    window.addEventListener("message", (event) => {
        if (event.source !== window.parent) {
            return;
        }
        const data = event.data;
        if (data?.source === "ba-host" && data.type === "ba:error") {
            setStatus("host-error", data.payload?.code || "E_INTERNAL");
        }
    });

    async function main() {
        try {
            const ba = await BreaktimeArcade.init({ timeoutMs: 5000 });
            window.__baProbe = ba;
            contextNode.textContent = JSON.stringify(ba.context, null, 2);
            setStatus("ready", `ready: ${ba.context.mode}`);
            ba.ready();
            ba.on("pause", () => setStatus("paused", "paused"));
            ba.on("resume", () => setStatus("ready", `ready: ${ba.context.mode}`));

            document.getElementById("probe-submit").addEventListener("click", async () => {
                try {
                    const result = await ba.submitResult({
                        value: 1,
                        durationMs: ba.context.limits.minPlaytimeSeconds * 1000,
                        eventLog: { v: 1, seed: ba.context.seed, events: [] },
                        seed: ba.context.seed,
                    });
                    setStatus("submitted", JSON.stringify(result));
                } catch (error) {
                    setStatus("error", `${error.code || "E_INTERNAL"}: ${error.message}`);
                }
            });

            document.getElementById("probe-leaderboard").addEventListener("click", async () => {
                try {
                    const top = await ba.leaderboard.top(10);
                    setStatus("leaderboard", JSON.stringify(top));
                } catch (error) {
                    setStatus("error", `${error.code || "E_INTERNAL"}: ${error.message}`);
                }
            });

            document.getElementById("probe-storage").addEventListener("click", async () => {
                try {
                    await ba.storage.set("probe.v1", { n: 1 });
                    const value = await ba.storage.get("probe.v1");
                    setStatus("storage", JSON.stringify(value));
                } catch (error) {
                    setStatus("error", `${error.code || "E_INTERNAL"}: ${error.message}`);
                }
            });

            document.getElementById("probe-bad").addEventListener("click", () => {
                parent.postMessage(
                    {
                        source: "ba-sdk",
                        protocol: 1,
                        type: "ba:storage",
                        requestId: crypto.randomUUID(),
                        sessionId: ba.context.sessionId,
                        payload: { op: "delete", key: "x" },
                    },
                    "*",
                );
            });

            document.getElementById("probe-exit").addEventListener("click", () => {
                ba.exit();
                setStatus("exited", "exited");
            });
        } catch (error) {
            setStatus("error", `${error.code || "E_INTERNAL"}: ${error.message}`);
        }
    }

    main();
})();
