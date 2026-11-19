# OKF v0.3 AsciiDoc profile (`okf-adoc/1.0`)

This is an opt-in extension profile. It does not create a new official OKF
version and does not change Markdown-only OKF v0.3. A bundle opts in with
`okf_version: "0.3"` and `x-okf-profile: "okf-adoc/1.0"` in its root
`index.md`, or by an explicit caller selection when no index is present.
Explicit selection takes precedence; a recognized index declaration is used
for an existing bundle; new bundles default to standard OKF v0.3. `.adoc`
files alone never select this profile.

## Concepts and paths

Markdown identity is its bundle-relative path with only the final `.md`
removed (`metrics/revenue.md` → `metrics/revenue`). AsciiDoc identity retains
the `.adoc` suffix (`metrics/revenue.adoc` → `metrics/revenue.adoc`). Thus
`a.adoc` and `a.adoc.md` have the same ID and are a collision, not a choice
between formats. Only the exact lowercase `.adoc` and `.md` extensions are
concept candidates; `.asciidoc` and `.ADOC` are assets.

Paths are bundle-relative unless they start with `/`, in which case they are
resolved from the bundle root, matching OKF v0.3 §6. Query and fragment
components do not participate in file lookup. Percent escapes are decoded
before lookup. Resolution must remain inside the bundle root; traversal and
symlink escapes are rejected. A target that matches more than one concept ID
is ambiguous and must be reported with every physical path.

AsciiDoc `link:target[]` denotes a downloadable/navigation link; `xref:target[]`
and `<<target#fragment,label>>` are cross-references. Fragments are not file
paths. Escaped macros are literal text. Root-relative `/` targets are valid
bundle paths but are warned on in `xref:` and `<<…>>`: Asciidoctor renders
`xref:/tables/x.adoc[]` as `/tables/x.html`, a web-root URL, so the two
interpretations agree only when the bundle root is published as the site
root. Prefer relative targets. Asciidoctor rewrites `.adoc` xref targets to
the rendered output extension.

`include::path[]` is resolved with the same root containment rules. Includes
are for partials, not concepts; including a recognized concept document is an
error. Partials need not have OKF frontmatter. No link or include may escape
the bundle.

## Frontmatter, header, and body

An AsciiDoc concept uses the same OKF YAML frontmatter as Markdown. After
frontmatter is removed by Asciidoctor's `skip-front-matter` functionality, the
document header is the block at the start of the body through its first empty
line. It can contain an optional `= Title`, optional author and revision
lines, and attribute entries. A header containing only attribute entries is
valid. Body text before a title/header is a structural error; a title later
in the file is not a header. Plain text directly below a title is parsed as
an author line by Asciidoctor and should be reported as a warning.

Header attributes are document metadata, not content. Existing unrelated
attributes and all body text are preserved. `okf-` is reserved for generated
metadata. A manually authored `okf-*` attribute is never canonical input.
Generated attributes may be referenced in the body, e.g. `{okf-status}`.
Never infer canonical YAML from rendered or authored attributes.

## One-way metadata synchronization

Canonical YAML and the path-derived Concept ID map only to explicitly
configured AsciiDoc attributes. Defaults:

| Canonical source | Attribute | Conversion |
|---|---|---|
| Derived Concept ID | `okf-concept-id` | string |
| `type` | `okf-type` | string |
| `title` | `okf-title` | string |
| `description` | `okf-description` | single-line string |
| `status` | `okf-status` | string |
| `tags` | `okf-tags` | ordered RFC 4180 fields |

Optional absent/null values are omitted. Absence of `status` retains standard
OKF semantics; it is not materialized as a guessed value. A scalar `tags`
value is one tag, never split at commas. Lists keep their order and use a
comma with no following space. Fields containing commas or quotes are quoted
per RFC 4180, with embedded quotes doubled. One trailing newline from YAML
block-scalar chomping is removed from description; any remaining newline is
unsupported. No folding, placeholder substitution, null emission, or
arbitrary nested-value flattening is allowed. Additional namespaced mappings
must be explicit and reproducible. `id`, concept-level `version`, and
`status: accepted` are not silently treated as OKF fields.

Attribute values that can inject a line, trigger AsciiDoc attribute expansion,
or otherwise cannot be represented safely are unsupported and reported.
The `--check` and `--dry-run` modes are read-only. `--write` reconciles only
generated header attributes, is idempotent, preserves original YAML and text,
and must not insert anything beneath a late title or a structurally invalid
header. Attribute-only changes do not update `generated.at`.

## OKF v0.3 semantics

Provenance, actors, lifecycle status (`draft`, `stable`, `deprecated`),
verification history, trust, staleness, and attestation retain their OKF v0.3
meaning. AsciiDoc footnotes may attribute source material but do not replace
the canonical `sources` metadata. A source-citing footnote uses
`footnote:<source-id>[citation]` where `<source-id>` matches `sources[].id`;
an unlabelled `footnote:[text]` is prose, not machine-readable provenance.
`footnoteref:[id]` must refer to a preceding named footnote. Attested computations are discovered in
AsciiDoc source blocks in the `Computation` section or by the canonical
`computation` file reference. YAML declarations alone do not prove execution,
verification, or attestation.
