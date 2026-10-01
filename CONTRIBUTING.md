# How to contribute

Thank you for your interest in this project. This page explains how to report
a problem, propose a change, and get a pull request merged.

## Before you start

*   For a bug, search the
    [existing issues](https://github.com/simplemind121/odoo19-barcode-ce/issues)
    first, then open a new one with the bug report template.
*   For a new feature or a behaviour change, open an issue and agree on the
    approach before you write code. Changes that alter stock semantics need a
    design discussion; see [Rules that reviewers enforce](#rules-that-reviewers-enforce).
*   For a security vulnerability, do **not** open an issue. Follow
    [SECURITY.md](SECURITY.md).

## Licensing of contributions

This project is licensed under the LGPL-3.0-or-later. By submitting a pull
request you agree that your contribution is licensed under the same terms and
that you have the right to submit it.

Never copy or adapt code from Odoo Enterprise (for example `stock_barcode`).
Enterprise code is under a proprietary licence and cannot be accepted here.

## Development setup

```bash
./dev-env.sh        # isolated Odoo 19 + PostgreSQL, ports 8169 / 5442
./scripts/test.sh   # full suite; must pass before and after your change
```

[docs/development.md](docs/development.md) describes the environment, the test
commands and the known testing pitfalls.

## Making a change

1.  Fork the repository and create a branch from `main`.
2.  Keep the change small and focused. One logical change per pull request.
3.  Add or update tests. New scanner behaviour needs a Python test; a browser
    tour alone is not enough.
4.  Update the documentation that your change makes stale:
    *   `CHANGELOG.md`, under **Unreleased**;
    *   `docs/compatibility.md`, if behaviour relative to stock Odoo changes;
    *   `docs/scanner-api.md`, if a `bc_*` method or the state object changes;
    *   `docs/README_安装与验收.md`, if what the warehouse team sees changes;
    *   `i18n/*.pot` and `i18n/zh_CN.po`, if user-visible strings change.
5.  Bump the module `version` in `__manifest__.py` when the data model changes,
    and add a migration script under `migrations/` if existing data must be
    converted.
6.  Run `./scripts/test.sh` and make sure CI is green.

## Code style

*   **Python:** follow the
    [Odoo coding guidelines](https://www.odoo.com/documentation/19.0/contributing/development/coding_guidelines.html)
    and the style of the surrounding code. Public scanner RPC methods are named
    `bc_*`; internal helpers are `_bc_*`.
*   **JavaScript:** OWL components, ES modules, no new third-party libraries
    without discussion.
*   **Strings:** source strings are English and translatable (`_()`, `_t()`).
    Chinese lives in `i18n/zh_CN.po`. Keep labels short enough for a phone.
*   **Markdown:** follow the
    [Google Markdown style guide](https://google.github.io/styleguide/docguide/style.html):
    one `#` title per file, ATX headings, lines wrapped at 80 characters, fenced
    code blocks with a language.
*   **Prose:** follow the
    [Google developer documentation style guide](https://developers.google.com/style):
    second person, present tense, active voice, sentence-case headings.

## Rules that reviewers enforce

These protect data integrity. A pull request that breaks one is not merged.

*   **Do not change stock semantics.** The scan engine must end with the
    standard `button_validate()` so that backorders, valuation and accounting
    stay Odoo's own.
*   **Do not write a shared row on the scan hot path.** Record quantities with
    `line._bc_add(delta)`, which only inserts an event.
*   **Every scanner entry point starts with `bc_guard(self)`.** Methods that
    change data also write to `stock.barcode.scan.log` and notify the bus.
*   **Validate ids that come from the client.** The scan context is stored in
    the browser; treat every id in it as untrusted input.
*   **Keep operator paths working.** Operators cannot open backend wizards.
    Either the scanner asks the question itself, or the feature is supervisor
    only.
*   **The scan log and scan events are append-only.** Do not add code that
    edits or deletes rows.

## Commit messages

*   First line: imperative mood, at most 72 characters, no trailing period.
    Prefix with the module when the change is local to one, for example
    `stock_barcode_ce: refuse serial numbers scanned twice`.
*   Body: explain what changed and why, not how. Reference the issue
    (`Fixes #12`).

## Pull request review

*   Fill in the pull request template.
*   All pull requests need a passing CI run and one approving review from a
    maintainer listed in [`.github/CODEOWNERS`](.github/CODEOWNERS).
*   Address review comments with new commits; do not force-push during review.
    The maintainer squashes on merge.

## Code of conduct

Participation in this project is governed by the
[code of conduct](CODE_OF_CONDUCT.md).
