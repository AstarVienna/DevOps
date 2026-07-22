# Version Bumping & Release Command Reference

*Companion to the workflow model document. Records every version-bump situation, the exact commands involved, and why the CI scripts ended up the way they did.
Intended as onboarding material and as ground truth when the automation needs debugging.*

All behavior below was verified empirically against **Poetry 2.3.0** (the version pinned in the CI workflows). Re-verify the rule matrix in §2 when that pin changes.

## 1. Ground rules
- Version numbers change **only on `main`** (or a maintenance branch, §9), and in the normal case **only via CI** (bot commits).
  Never bump versions on feature branches — this is what makes overlapping branches conflict-free.
- The repo is **always on a `.devN` version** between tags.
  Every tag is immediately followed by a dev-bump commit; the tagged version string never lingers.
- Poetry has no `dev` bump rule.
  The CI `dev` rule is our own: it computes the next dev version with `packaging` and passes it to `poetry version` as an explicit string (algorithm in §3).
- `poetry version <explicit-version>` accepts any valid PEP 440 string (verified: `0.11.5.dev0`, `0.12.0b0`, `1.0.0`, ...).
  When no rule does what you need, an explicit version is always a legitimate escape hatch.

## 2. Poetry rule matrix (empirical, Poetry 2.3.0)
What `poetry version <rule>` produces from each phase our scheme visits:

| from \ rule       | `patch`  | `minor`  | `major` | `prerelease`  | `prerelease --next-phase` | `preminor` |
|-------------------|----------|----------|---------|---------------|---------------------------|------------|
| `0.11.4` (stable) | `0.11.5` | `0.12.0` | `1.0.0` | `0.11.5a0`    | `0.11.5a0`                | `0.12.0a0` |
| `0.11.5.dev2`     | `0.11.5` | `0.12.0` | `1.0.0` | 💥 crash       | 💥 crash                 | `0.12.0a0` |
| `0.12.0b0`        | `0.12.0` | `0.12.0` | `1.0.0` | `0.12.0b1`    | `0.12.0rc0`               | `0.12.0a0` |
| `0.12.0b1.dev0`   | `0.12.0` | `0.12.0` | `1.0.0` | `0.12.0b2` ⚠️  | `0.12.0rc0`              | `0.12.0a0` |
| `0.12.0rc1.dev0`  | `0.12.0` | `0.12.0` | `1.0.0` | `0.12.0rc2` ⚠️ | `0.12.0`                 | `0.12.0a0` |

Three findings that shaped the conventions below:

1. **💥 `prerelease` crashes from a plain dev version** (unhandled `AssertionError` in poetry-core 2.x). Entering the freeze phase from `X.Y.Z.devN` therefore cannot use `prerelease`; use `preminor` / `premajor` (lands on `a0`) or an explicit version (to land on `b0` directly, per team convention).
3. **⚠️ `prerelease` from a dev-on-pre version skips a number**: from `0.12.0b1.dev0` (i.e. "working towards b1") it yields `b2`, not `b1`, because Poetry increments the pre-counter without knowing our "dev points at the *next* tag" convention.
   Tagging the version the repo is actually pointing at requires an explicit version (strip the `.devN`).
5. **Stable rules "complete" a pre-release instead of jumping past it** — with one asymmetry: from any `0.12.0*` pre/dev state, `patch` *and* `minor` both yield `0.12.0` (the minor-ness was already encoded when the freeze was entered via `preminor`), but **`major` does not complete — it jumps to `1.0.0`**.
   Rule of thumb: the real bump decision is made when *entering* the freeze; the final release always uses `patch`.

## 3. The `dev` rule (our addition)
Implemented in `DevOps/bump.yml`; the algorithm, for reference and manual reproduction:

| current version | next dev version | reasoning |
|-----------------|------------------|-----------|
| `X.Y.Z` (just tagged stable) | `X.Y.(Z+1).dev0` | Guess patch: sorts below *any* possible next release, so always safe. The real bump is decided at release time. |
| `X.Y.Z<pre>N` (just tagged pre-release, e.g. `0.12.0b0`) | `X.Y.Z<pre>(N+1).dev0` (e.g. `0.12.0b1.dev0`) | Guess next tag in the same phase; sorts below both `b1` and `rc0`, so safe whichever comes. |
| `...devN` (already dev) | `...dev(N+1)` | Plain counter increment, everything else preserved. |

Manual equivalent (rarely needed; e.g. if CI is down):
```bash
poetry version -s                 # inspect current state
poetry version 0.11.5.dev3        # explicit next version per the table above
git commit -am "Bumping version from 0.11.5.dev2 to 0.11.5.dev3"
git push                          # on main, with appropriate permissions
```

## 4. Situation: dependency PR merged into `main`
**Trigger:** PR with the `dependencies` label merges.
**Automation:** `bump_on_dependency.yml` → `bump.yml` with `rule: dev`, fully automatic.

Effect: `0.11.5.dev1 → 0.11.5.dev2`.
Purpose: "which version are you on?" has a useful answer when debugging cross-package dependency mismatches.
Deliberately *not* run on every merged PR (history noise without unique identification; see workflow model §3).

## 5. Situation: regular release from `main`
**Trigger:** human decision.
**Command:** run the **Prepare release** workflow (Actions UI) on `main` with rule `patch`, `minor`, or `major` — derived from the `minor`/`major` PR labels merged since the last tag (maximum wins; unlabelled = patch).

Under the hood, three steps (this is the whole reason `prepare_release.yml` exists — they must happen together, in order):

```bash
poetry version minor              # 1. e.g. 0.11.5.dev4 -> 0.12.0; commit ①
# 2. draft GitHub release created, tag v0.12.0 pinned to commit ①'s SHA
poetry version 0.12.1.dev0        # 3. dev rule; commit ② immediately after
```

Then: review the draft notes (link in the job summary), edit the manual section if desired, **publish**. Publishing creates the tag at the pinned SHA and triggers `publish_pypi.yml` (tag↔version guard → build → attach artifacts → PyPI upload).

Note from §2: these rules also work when releasing directly out of a freeze (`0.12.0rc1.dev0 + patch → 0.12.0`) — see §7 for why `patch` is the right rule there.

## 6. Situation: entering feature freeze
**Trigger:** team decision to stop merging features for the next release.
Team convention marks the freeze with a **`b0`** version.

Because of gotcha §2.1 (`prerelease` crashes from dev) and because `preminor` lands on `a0` rather than `b0`, entering the freeze at `b0` requires an **explicit version**:

```bash
poetry version 0.12.0b0           # explicit; encodes the minor-ness of the release
```

⚠️ This is the moment the patch/minor/major decision is actually made — choose the base version accordingly (check the `minor`/`major` PR labels merged since the last tag). Everything after this point only completes to that base (§2.3).

Whether the freeze point is *tagged* depends on the package:

- **Packages with pooch-managed data** (or downstream packages needing a pinnable snapshot): run **Prepare release** with the explicit version in the `version` input (which overrides the rule choice).
  The version is auto-detected as a pre-release: the GitHub release is marked "pre-release", PyPI upload is skipped, artifacts are still built and attached.
  CI then bumps to `0.12.0b1.dev0` automatically.
- **Everyone else:** a plain bump (no tag) suffices: run the **Bump** workflow with the explicit version in its `version` input, then bump to the dev version (rule `dev`), or do both locally.
  If untagged, remember pooch-style tag lookups don't apply anyway.

Note: the bare `prerelease` rule has been removed from all workflow choice lists on purpose — under the always-on-`.devN` scheme it either crashes (§2.1) or skips a number (§2.2), and its legitimate jobs are covered by the `dev` rule and explicit versions.

## 7. Situation: during and out of the freeze
**Tagging the next beta** (`b1` while on `0.12.0b1.dev0`): explicit version only — **Prepare release** with `version: 0.12.0b1` (or locally, `poetry version 0.12.0b1`).
The bare `prerelease` rule would skip to `b2` (gotcha §2.2) and has been removed from the workflow menus.

**Advancing the phase b → rc:** `poetry version prerelease --next-phase` works correctly from dev-on-pre states (`0.12.0b1.dev0 → 0.12.0rc0`) — this is why the rule remains in the workflow choice lists.
On reaching `rc`, the **replaceholder** workflow becomes runnable (it refuses to run on non-rc versions by design): it substitutes `PLACEHOLDER_NEXT_RELEASE_VERSION` in source files with the upcoming stable version.
This is also when packages with separate release notes integrate them.

**Final release:** **Prepare release** with rule **`patch`** — it completes `0.12.0rc1.dev0 → 0.12.0` (§2.3). Never use `major` here (it jumps to `1.0.0` instead of completing). Never return to plain `.devN` for a version that already has pre-release tags: `0.12.0.dev0` would sort *below* `0.12.0b0`, breaking ordering.

## 8. Situation: first 1.0 (or any major) release
Rule `major` via **Prepare release**, from any plain dev state: `0.11.5.dev4 + major → 1.0.0`.
(Explicit `poetry version 1.0.0` is equivalent.) If the 1.0 gets a freeze phase, enter it with `poetry version 1.0.0b0` explicitly (§6) and release with `patch` (§7).

Remember the workflow-model implication: from 1.0 on, "breaking ⇒ major ⇒ rare", so the first `major`-labelled merge after a release is the moment the old series can no longer be released from `main` — pause and confirm the team is ready for that before merging.

## 9. Situation: backport to a released series
Only needed once a breaking change has landed on `main` (otherwise: just release `main` as the next minor).
Fixes land on `main` **first**, then get cherry-picked out — never developed only on the maintenance branch.

### 9a. Cutting the maintenance branch
(once per major series, lazily, the day the first backport is needed)

- [ ] Branch from the **last tag** of the series, not from `main`:
      `git branch v2.x v2.1.0 && git push origin v2.x` (branching from a later `main` commit would smuggle unreleased feature work into a "critical patch")
- [ ] Verify CI workflow triggers cover the branch (add `"v*.x"` to the `branches:` lists if not already glob-covered)
- [ ] Repoint data-download fallbacks from `main` to `v2.x` (e.g. the pooch fallback-branch constant), so source installs from the branch fetch series-matching data
- [ ] Note the support window for the old series in README/docs

### 9b. The backport itself
```bash
# fix is merged into main as commit <sha>
git switch -c backport-fix v2.x
git cherry-pick -x <sha>          # -x records the origin commit in the message
# open PR against v2.x, let CI run, merge
```

### 9c. Releasing from the branch
Run **Prepare release** *with `v2.x` selected in the branch dropdown*, rule `patch`, and set **`previous-tag`** to the last tag of the series (e.g. `v2.1.0`) — releases now happen out of version order, and without it GitHub may generate the notes against the wrong comparison base.
Everything else is identical to §5: draft pinned to the branch commit, publish creates `v2.1.1`, PyPI accepts out-of-order uploads (users on `==2.1.*` get it; unconstrained users keep getting the newest release), and the branch is auto-bumped to `2.1.2.dev0`.

Patches go only to the **newest** release of a series (2.1.1, never 2.0.2).

### 9d. End of support
Delete the branch when the window closes — every released state is preserved by its tag.

## 10. One-time migration (transitional, delete this section later)
Repos still on the legacy pseudo-alpha scheme (e.g. `0.11.5a1`) transition by running the **Bump** workflow once with rule `dev`, yielding `0.11.5a2.dev0`.
Not pretty, but it sorts above everything already installed from `main` — unlike a manual reset to `0.11.5.dev0`, which would sort *below* the `a1` builds — and it vanishes at the next release.

## Quick reference

| Situation                   | Command / action                                                                          |
|-----------------------------|-------------------------------------------------------------------------------------------|
| Dependency PR merged        | automatic (`dev` rule)                                                                    |
| Manual dev bump             | Bump workflow, rule `dev`                                                                 |
| Regular release             | Prepare release, rule `patch`/`minor`/`major` (labels decide)                             |
| Enter freeze at `b0`        | Prepare release (tagged) or Bump (untagged), explicit `version: 0.12.0b0` (§6)            |
| Tag next beta from `bN.dev` | Prepare release, explicit `version: 0.12.0b1` (**not** `prerelease` — removed from menus) |
| Beta → release candidate    | rule `prerelease --next-phase`                                                            |
| Replace docs placeholders   | replaceholder workflow (requires rc)                                                      |
| Release out of freeze       | Prepare release, rule `patch` (**never** `major`)                                         |
| First 1.0                   | Prepare release, rule `major`                                                             |
| Cut maintenance branch      | checklist §9a                                                                             |
| Backport fix                | merge to `main`, `git cherry-pick -x` onto `v2.x` PR                                      |
| Backport release            | Prepare release from `v2.x`, rule `patch`, set `previous-tag`                             |
