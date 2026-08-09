# AAAK bounded semantic-adequacy evaluation

Date: 2026-08-09

Status: bounded independent review, standalone-only, not a production quality gate.

## Scope and method

This is a fresh-context independent review of the nine-case benchmark corpus.
It is separate from structural literal checks and deterministic semantic
probes. Each output was reviewed for four dimensions:

1. intent/task preservation;
2. polarity and negation preservation;
3. named entities and literal preservation;
4. operational meaning for a reader who knows the configured abbreviation map.

Ratings are `adequate`, `borderline`, or `inadequate`. This review is an independent model assessment, not an independent human
study, user study, or reader task-completion benchmark. It therefore cannot
establish general semantic adequacy.

## Review matrix

| Case | Rating | Finding |
|---|---|---|
| prose-preference | borderline | Preference, dark mode, vim bindings, and rationale remain recoverable; `USR`, `PROJ`, and `IMP` make the causal relation less self-evident outside the configured map. |
| tool-output | borderline | Migration completion, path, and continuation remain present; `LOC DB DONE` and especially `SESS` are less readable outside the map. |
| structured-literals | adequate | URL, commit, identifier, and preservation instruction remain exact. |
| code-and-negation | adequate | `Do not rewrite` and both protected values remain exact; code-comment context is retained. |
| json-config | adequate | JSON is unchanged and remains parseable; all keys and values retain their original meaning. |
| shell-command | adequate | Command, working path, and exit code remain exact; `+` is readable as conjunction in this context. |
| date-and-number | adequate | Deadline, timestamp, negated rounding instruction, decimal, and percentage remain exact. |
| unicode-prose | borderline | Preference, Unicode text, emoji, preservation instruction, and filler-trimming intent remain recoverable, but unexplained `USR` weakens standalone readability. |
| log-line | adequate | Timestamp, severity, request ID, status, and path remain exact; the `LOG:` label adds useful type context. |

## Findings

- No concrete polarity inversion, literal corruption, JSON corruption, date
  alteration, number alteration, identifier alteration, or operational-command
  alteration was found in this corpus.
- The principal semantic risk is reader dependence on the abbreviation map,
  especially `LOC`, `DB`, `SESS`, `USR`, `PROJ`, and `IMP`.
- Cases 1, 2, and 8 are borderline because shorthand weakens standalone
  readability even when the source facts remain technically recoverable.
- The result supports continued investigation of a bounded opt-in provider; it
  does not support a production integration recommendation or the historical
  `~30x` claim.

## Not covered

- Independent human inter-rater agreement
- Model-reader recall or task-completion accuracy
- Long-context interactions across multiple compressed summaries
- Ambiguous pronouns, conflicting instructions, or multi-turn state updates
- Non-English-only prose beyond the Unicode preservation case
- Adversarial prompt injection and hostile markup
- Reader behavior without the abbreviation map
- Hermes-LCM lineage, rollback, provider precedence, or runtime behavior

## Independent-review result

The independent reviewer rated six cases adequate, three borderline, and none
inadequate. Its recommendation was acceptable with a readability caveat: cases
1, 2, and 8 should expand or document the shorthand when outputs must stand
alone for readers unfamiliar with the abbreviation map.

## Decision impact

Semantic adequacy remains an open evidence gate. The next required evidence is
an independently reviewed, larger corpus with reader-oriented comprehension
questions or task completion checks. Do not design or activate a Hermes-LCM
adapter until that gate and the host-contract gate are separately satisfied.
