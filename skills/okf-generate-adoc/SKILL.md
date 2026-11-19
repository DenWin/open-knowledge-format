---
name: okf-generate-adoc
description: Create, update, migrate, and validate OKF v0.3 bundles using the opt-in okf-adoc/1.0 profile. Use for AsciiDoc concepts or explicit extended-profile selection; never infer profile from .adoc files alone.
---

# Generate OKF with the AsciiDoc profile

Use the self-contained `scripts/` tools and `references/asciidoc-profile.md`.
This is an opt-in extension to OKF v0.3, not an official OKF version. The
ordinary `okf-generate` skill remains the standard Markdown-only path.

## Profile routing

Choose exactly one generation/consumption skill pair for a bundle operation:

| Profile | Generation | Consumption |
|---|---|---|
| Standard OKF v0.3 | `okf-generate` | `okf-consume` |
| Extended OKF + AsciiDoc | `okf-generate-adoc` | `okf-consume-adoc` |

Honor explicit profile selection. For an existing bundle, honor a recognized
root `index.md` declaration (`okf_version: "0.3"` and
`x-okf-profile: "okf-adoc/1.0"`). For a new bundle, default to standard OKF
unless extended mode is explicitly selected. Do not mix skill pairs, silently
downgrade, or infer extended mode from file extensions.

## Authoring and migration

1. Inventory all non-hidden `.md` and `.adoc` documents, reserved root files,
   links, includes, IDs, unknown YAML fields, and source/evidence history.
2. Derive IDs exactly as documented in the profile reference. Resolve all
   collisions before migration; do not select a winning path automatically.
3. Keep OKF YAML canonical. Preserve authorship, verification history, unknown
   extension fields, line endings, and bodies. Do not invent sources,
   identities, dates, or confirmations.
4. For significant migrations, present a dry-run plan containing the current
   and target profile, files and IDs, collisions, mappings, body/index/log
   impacts, proposed attributes, validator findings, and unresolved decisions.
5. Leave included partials without frontmatter. Preserve unrelated existing
   `index.md` and `log.md`; they are optional and must never be overwritten.
6. Normalize structural headers only in an explicitly authorized migration.
   Run attribute synchronization in `--dry-run` first, then `--write` only
   after approval.
7. Run read-only validation before and after the operation. Attribute-only
   edits must not change `generated.at`.

Use explicit mappings for legacy fields or extension properties. In
particular, do not silently map legacy `id`, concept-level `version`, or
`status: accepted` into canonical OKF metadata. Preserve all unknown YAML
keys. Profile changes from standard to extended preserve Markdown IDs and do
not require conversion. Moving back to standard requires a loss and impact
plan for `.adoc` concepts.

## Tools

`scripts/validateWithAdoc.py BUNDLE [--json] [--strict] [--now RFC3339]`
validates both formats without writing. Exit codes follow the original
validator: 0 success, 1 validation failure, 2 usage/setup failure.

`scripts/scanWithAdoc.py BUNDLE` discovers concepts and trust/freshness.
Existing `--type`, `--tag`, `--grep`, `--current`, `--stale`,
`--deprecated`, `--unverified`, `--now`, and `--json` filters are supported.
An identity collision is listed with all physical paths and exits nonzero.

`scripts/syncAttributes.py FILE_OR_BUNDLE` requires one of `--check`,
`--dry-run`, or `--write`. It only reconciles generated header attributes;
it never updates YAML and never writes below a late title.

See `references/asciidoc-profile.md` for link/include resolution, header
structure, conversions, and profile semantics.
