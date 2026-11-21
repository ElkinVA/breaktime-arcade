# Runtime probe

Test-only game source for the App F runtime E2E. It is not a product game and
must not enter public aggregates.

The publish helper copies this directory plus the official
`sdk/1.1.0/ba-sdk.js` into the gitignored `var/runtime/` volume. The
management command `probe_seed` creates the matching published Game/Version.

```bash
make probe-seed
BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 make e2e
```
