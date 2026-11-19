---
name: okf-consume-adoc
description: Read and answer from standard OKF v0.3 plus explicitly selected okf-adoc/1.0 bundles, preserving provenance, trust, lifecycle, freshness, and attestation distinctions.
---

# Consume OKF with the AsciiDoc profile

This skill is read-only. Never edit, normalize, or synchronize a bundle while
answering. It packages its own validator, scanner, profile rules, and YAML
reader; it does not depend on either generation skill or the original
Markdown-only skill scripts.

Choose exactly one matching consumption skill. Explicit selection takes
precedence; otherwise respect recognized `index.md` profile metadata. New
bundles default to standard OKF v0.3. `.adoc` files by themselves do not
select the extended profile.

Run `scripts/scanWithAdoc.py BUNDLE --json` to inventory concepts. Apply trust,
staleness, status, source-window, and verification rules from the OKF v0.3
specification. Treat all identity collisions as ambiguous: report every
physical path and do not choose a winner. Run
`scripts/validateWithAdoc.py BUNDLE --json` for read-only diagnostics.

For AsciiDoc concepts, read canonical YAML first and treat `okf-*` header
attributes only as derived copies. Do not infer or overwrite YAML from those
attributes. A rendered `{okf-status}` is not evidence that the underlying
status is valid. Respect link, xref, include, and bundle-root rules in
`references/asciidoc-profile.md`.

AsciiDoc footnotes can attribute source material but do not replace OKF
`sources`. YAML that declares a computation, executor, or attester does not
prove that a computation ran or was verified. Distinguish declared,
executed, verified, and attested claims; report trust tier, freshness, and
attestation status separately.
