# Contributing

Keep business-rule documentation and executable rules synchronized. Add or update tests whenever classification, selection, sorting, workbook schema, or frontend grouping behavior changes.

Before submitting a change:

1. Run the Python and frontend test suites documented in `README.md`.
2. Run `scripts/prepublish_check.ps1`.
3. Verify no private data, generated workbook, database, cache, log, or credential is staged.
4. Describe any data-contract or ordering change explicitly.
