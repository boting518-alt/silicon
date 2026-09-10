# R1/R2 real browser verification

Real HTTPS, existing trusted project certificate; independent PG17.11 and Keycloak26.7.3. No trust or resident service changes. Start from repository root with:

```bash
SILICON_BROWSER_PUBLICATION=1 SILICON_BROWSER_CATALOG=1 SILICON_BROWSER_CATALOG_SEED=1 SILICON_BROWSER_QUOTES=1 SILICON_TEST_PG_BIN="$PG_BIN" SILICON_TEST_KEYCLOAK_HOME="$KEYCLOAK_HOME" .venv/bin/python infra/browser_stack.py
```

Use the preparation steps in the review manifest (own Java21, locked dependencies, test font, trusted certificate). All data fictional. Alice/Fictional-alice-17! logs in via Keycloak, selects A, opens seeded TASK-006 draft and submits. Date widget ArrowUp produced actual 2028-11-01 12:00 local, recorded in DOM. Alice logs out through IdP; Bob/Fictional-bob-17! logs in, confirms each UNKNOWN with explanation/evidence and approves/issues Q-000001, 49660.01 CNY.

Bob reopens original draft: submission form is replaced with explicit independent revision guidance. Captured 1440x900 and 390x844 viewports; raw IAB exports remain 1425x891 and 375x812. No resize or visual-template change. Initial guidance DOM read occurred before async detail resolved; final-named DOM is authoritative, original intermediate output retained.

Bob navigates to publication history, creates independent revision, reopens and submits it; Alice logs back in, approves the other person's submission and issues Q-000001-R2. Original Q-000001 content hash remains d879dc3a23438cec737aa16cb27143ce9dd0303305490ba5d2bcd6cde68101ec with the same amount. See browser-*.txt.

Actual React tests at /tests/publication-component.html: 5 passed (including published draft transition). /tests/quote-component.html: original 3 passed. These use HTTP fixtures, not a PG/OIDC substitute. Cross-source same-key/concurrent revision and server rejection are verified by real PG/API tests, not claimed as same-key browser requests. Initial tab opened before stack READY returned connection refused; a new tab after readiness succeeded, no TLS bypass.

Stack terminated via its cleanup handler; BROWSER_STACK_CLEANED recorded. Browser tabs closed and viewport reset. Full old browser suite, Docker, remote CI and other browsers not_run/unverified; no deployment. Formal business policies remain unconfigured as before.
