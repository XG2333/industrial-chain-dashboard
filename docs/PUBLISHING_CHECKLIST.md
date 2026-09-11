# GitHub publishing checklist

- [x] Choose and add an explicit open-source license (Apache-2.0).
- [ ] Confirm every retained dependency and bundled skill may be redistributed.
- [ ] Run `scripts/prepublish_check.ps1` with zero findings.
- [ ] Verify `git status` contains no `.env`, workbook, database, cache, log, or runtime output.
- [ ] Inspect the complete staged diff before the first push.
- [ ] Run Python and frontend tests.
- [ ] Build the frontend from source; do not publish local `node_modules` or stale `dist` artifacts.
- [ ] Confirm documentation contains no employee names, local paths, internal hosts, or customer references.
- [ ] Add repository ownership, support contact, and security policy as appropriate.
