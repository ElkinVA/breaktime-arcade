# ARCADE-P5 ARCHER — owner action list

**Date:** 2026-11-23
Only actions requiring the owner/external party.

## 1. Original prototype

- **What:** provide `index4(1).html` (or confirm that the written concept is
  the accepted source).
- **Why:** the file was not present in the workspace; the current game is a
  faithful implementation of the written mechanics, not a verified port.
- **If deferred:** prototype-specific behaviours cannot be compared.
- **How:** place the file outside Git or in a task attachment; no secrets.

## 2. Product acceptance and content rights

- **What:** accept Archer as a portal game and confirm rights/licence for
  AI-generated visuals and generated WebAudio.
- **Why:** technical/live E2E is not product or legal acceptance.
- **If deferred:** the game remains dev/demo content.
- **How:** written confirmation; if the original prototype is third-party,
  provide its licence/permission.

## 3. Staging / production

- **What:** `.env.staging`, staging window, domains/TLS, production secrets
  and deploy approval.
- **Why:** dev E2E does not prove staging/production; these are external and
  irreversible actions.
- **If deferred:** status remains dev-verified only.

## 4. Real device/performance acceptance

- **What:** optional acceptance on representative low/mid-range phones and
  Safari/Firefox if those browsers are in scope.
- **Why:** current browser evidence is Chromium; 60 FPS is not benchmarked
  on physical devices.
- **If deferred:** performance risk remains but simulation is fixed-step and
  particle-capped.

## 5. Legal/privacy/retention

- Existing portal legal/consent/retention decisions remain owner-level; no
  new personal data is collected by Archer beyond the existing session and
  result contract.
