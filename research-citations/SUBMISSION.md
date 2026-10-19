# Proposed pull request

Title: Add live Europe PMC citation discovery and portable reference exports

## Why

Issue #13 requests a citation tool that retrieves relevant research and makes references usable in manuscripts. This change adds an executable retrieval/export component using real Europe PMC metadata and stable publication identifiers.

## Changes

- Dependency-free Python CLI and importable functions for live search.
- Local, explainable context matching within returned candidates.
- DOI deduplication and missing-metadata/retraction-type warnings.
- Explicit source selection and CSL JSON/RIS exports for citation-manager workflows.
- Bounded response sizes, timeouts and rate-limit handling.
- Offline regression tests, a live search example and a short CLI-output replay video in `research-citations/demo/demo.mp4`.

## Validation

18 offline unit tests passed. Live Europe PMC search and selected-reference exports were also exercised. See the module README for reproduction commands.

## Boundaries

This is a partial implementation of the citation tool, not a claim to complete all of issue #13. Context matching is lexical, not AI inference or verification of scientific support. Citation styles are delegated to citation managers through standard exports. No summarizer, PDF ingestion or peer-review UI is included.

AI-assisted with ChatGPT/Codex; tests and live retrieval were run locally.

## Bounty registration (pending submission)

Before opening a claim, confirm that this partial scope is eligible with the maintainer. The issue's prescribed attempt comment is `/attempt #13` with a plan; the PR must include `/claim #13` and a demo video. No attempt, PR, claim or payment has been registered by this local document.

Suggested plan: implement live Europe PMC citation retrieval with source provenance, local context ranking, selected-reference CSL JSON/RIS export, failure handling, tests and a reproducible demo. This does not replace the full AI-assisted tools request.
