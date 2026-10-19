# Europe PMC citation discovery

A focused contribution toward the citation tool in [issue #13](https://github.com/SCIBASE-AI/SCIBASE.AI/issues/13).
This module retrieves actual publication metadata, optionally ranks candidates against local context, and exports explicitly selected references for citation managers. Python 3.10+; no dependencies or API key.

## Run

From this directory:

```sh
python citations.py search 'TITLE:"malaria"' --limit 5 --open-access \
  --context 'malaria vaccine prevention' > results.json
```

Inspect `items` in the JSON and choose source IDs. Export a selected ID from your own search results:

```sh
python citations.py export results.json --id MED:YOUR_SELECTED_ID --format csl > references.json
python citations.py export results.json --id MED:YOUR_SELECTED_ID --format ris > references.ris
```

Repeat `--id` to export several references in the specified order. Import RIS or CSL JSON into a citation manager; choose APA, MLA, Nature or another style there. This module does not claim to implement those style specifications itself. CLI output goes to stdout; errors go to stderr with exit code 2.

## What works

- Live Europe PMC `core` metadata search, including PubMed records, with source URLs and retrieval timestamps.
- Open-access filtering, bounded requests, a 15-second timeout per attempt and at most three HTTP attempts.
- Retry handling for rate limits and transient server errors; long Retry-After requests stop rather than retry early.
- Optional, transparent token-overlap ranking within the first 1–50 retrieved candidates. Matched terms are included. Context is processed locally and never placed in the provider request.
- DOI deduplication, Unicode and collective author handling, HTML-to-text conversion, missing-field warnings.
- Explicit selection before export; CSL JSON and RIS preserve returned metadata without fabricating authors, dates or DOIs.
- Provider retraction-related publication types trigger warnings. This is not a comprehensive retraction check.

## Scope and limitations

This is a retrieval/export building block, not the entire AI-assisted research MVP. It does not implement an LLM, semantic entailment, paper summarization, peer review, PDF extraction, a manuscript editor, or one-click insertion. Token overlap is not evidence that a reference supports a claim. Review the source and its publication type before citing. Generic article/journal types are used in exports; books, chapters, preprints and nonstandard records may require correction in a citation manager.

The query is sent to Europe PMC. Do not put confidential manuscript text into the query. `--context` stays local but command-line arguments may be visible in local shell history/process listings. The first page is searched; this is not an exhaustive literature review. Abstracts and metadata may be missing, outdated or contain errors. Records with invalid identity/title fields are skipped with warnings; an entirely invalid nonempty response fails. No automatic fallback invents citations.

## Validation

```sh
python -m unittest discover -s tests -v
python -m py_compile citations.py
```

The offline tests cover request encoding, context privacy, stable ranking, duplicate DOIs, invalid records, incomplete metadata, Unicode/collective authors, HTTP errors/retries, size limits, RIS record injection and selection/export behavior. They use synthetic fixtures and do not depend on provider availability.

`demo/live-search.json` is a live metadata response normalized by this module; its timestamp and request URL record provenance. `demo/references.json` and `demo/references.ris` were produced from its first selected candidate. `demo/demo.mp4` is a rendered replay of actual CLI output, not a desktop recording. The test fixtures are synthetic; the live demo search is not.

To regenerate the replay from the saved live search, run `python demo/build_demo.py`. Only this optional recording script needs Pillow, FFmpeg and the DejaVu fonts under `/usr/share/fonts/truetype/dejavu/`; the application and tests use the standard library alone.

Provider documentation: https://europepmc.org/RestfulWebService

## Integration

Import `search`, `csl_json`, and `ris` from `citations.py`. `search()` returns a packet with provenance, warnings and normalized `items`. Keep the human selection step before passing items to an export function. A future editor or model can consume this same packet without coupling discovery to a particular AI provider.

Locally tested. Bounty eligibility and acceptance remain a maintainer decision; this module makes no payment claim.
