/* Who's Undercover? — deterministic seeded random number generator.
 *
 * Every value that can influence the result is derived from the session seed
 * supplied by the platform through `ba.context.seed`. The generator uses an
 * FNV-1a/xmur3-style string hash followed by mulberry32. It never consumes
 * unseeded randomness.
 */
(function (global) {
    "use strict";

    const VERSION = "1.0.0";
    const TWO32 = 4294967296;

    function toUint32(value) {
        return value >>> 0;
    }

    /** Stable 32-bit string hash (FNV-1a mixed with a rotated additive pass). */
    function hashSeed(seed) {
        const text = String(seed === undefined || seed === null ? "" : seed);
        let hash = 0x811c9dc5;
        let salt = 0x9e3779b9;
        for (let index = 0; index < text.length; index += 1) {
            const code = text.charCodeAt(index);
            hash ^= code;
            hash = Math.imul(hash, 0x01000193);
            salt = Math.imul(salt ^ (code + index + 1), 0x85ebca6b);
            salt ^= salt >>> 13;
        }
        hash ^= salt;
        hash = Math.imul(hash ^ (hash >>> 16), 0x21f0aaad);
        hash = Math.imul(hash ^ (hash >>> 15), 0x735a2d97);
        return toUint32(hash ^ (hash >>> 15));
    }

    /** mulberry32 — small, fast and reproducible across ES2022 engines. */
    function mulberry32(state) {
        let value = toUint32(state);
        return function next() {
            value = (value + 0x6d2b79f5) | 0;
            let mixed = Math.imul(value ^ (value >>> 15), 1 | value);
            mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
            return ((mixed ^ (mixed >>> 14)) >>> 0) / TWO32;
        };
    }

    function create(seed) {
        const seedValue = toUint32(hashSeed(seed));
        const next = mulberry32(seedValue);

        function float() {
            return next();
        }

        function int(maxExclusive) {
            const limit = Math.max(0, Math.floor(Number(maxExclusive) || 0));
            if (limit <= 0) {
                return 0;
            }
            return Math.floor(next() * limit);
        }

        function range(min, maxExclusive) {
            return Math.floor(Number(min) || 0) + int(Math.max(0, Math.floor(Number(maxExclusive) || 0) - Math.floor(Number(min) || 0)));
        }

        function pick(list) {
            if (!Array.isArray(list) || list.length === 0) {
                return null;
            }
            return list[int(list.length)];
        }

        function shuffled(list) {
            const copy = Array.isArray(list) ? list.slice() : [];
            for (let index = copy.length - 1; index > 0; index -= 1) {
                const swap = int(index + 1);
                const current = copy[index];
                copy[index] = copy[swap];
                copy[swap] = current;
            }
            return copy;
        }

        return Object.freeze({
            seed: String(seed),
            seedValue,
            float,
            next: float,
            int,
            range,
            pick,
            shuffled,
        });
    }

    global.WhosUndercoverRng = Object.freeze({
        version: VERSION,
        hashSeed,
        mulberry32,
        create,
    });
})(typeof window !== "undefined" ? window : globalThis);
