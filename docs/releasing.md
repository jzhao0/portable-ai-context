# Alpha release procedure

This document defines the controlled publication path for Portable AI Context alpha releases.

The release workflow is `.github/workflows/release.yml`. It is manual (`workflow_dispatch`) and defaults to `dry-run`. Creating or pushing a tag by itself does **not** publish to PyPI.

## Version and tag convention

Alpha package versions use PEP 440-style alpha versions such as:

```text
0.1.0a2
```

The corresponding Git tag is exactly:

```text
v0.1.0a2
```

The release guard fails unless all of the following agree:

- `pyproject.toml` project version;
- `src/portable_ai_context/__init__.py` `__version__`;
- the version encoded in the requested `vX.Y.ZaN` tag;
- the exact wheel/sdist filenames produced by the tagged commit.

The workflow also requires the tagged commit to be contained in `origin/main` history.

Publish mode additionally refuses a `CHANGELOG.md` release heading that is still marked `Unreleased`. Changelog version matching is exact, so a heading for `0.1.0a20` cannot satisfy a release guard for `0.1.0a2`.

## Build provenance and artifact identity

The workflow checks out the existing release tag with full Git history and builds from that tagged commit. It does not accept locally uploaded wheel/sdist files as release inputs. Checkout credentials are not persisted.

The build job:

1. validates tag/version/changelog state;
2. builds wheel + sdist once on the controlled Ubuntu build runner;
3. runs `twine check`;
4. requires exactly the expected wheel and sdist filenames;
5. generates `SHA256SUMS`;
6. installs only the built wheel into an isolated virtual environment;
7. runs the installed-distribution package smoke;
8. uploads the verified build products as one short-lived GitHub Actions artifact.

The release workflow does **not** rebuild separate distributions on Windows or macOS. The same retained wheel/sdist/checksum bytes become the release candidate for every later gate.

## Exact cross-platform release-candidate smoke

After the build artifact exists, the `candidate-smoke` job expands to this six-child matrix:

```text
ubuntu-latest  × Python 3.10
ubuntu-latest  × Python 3.13
windows-latest × Python 3.10
windows-latest × Python 3.13
macos-latest   × Python 3.10
macos-latest   × Python 3.13
```

Every child:

1. checks out the exact immutable build commit only to obtain reviewed smoke tooling;
2. downloads the original `release-dists-${release_tag}` artifact;
3. runs `tools/verify_release_candidate.py` against the retained `dist/` files and `SHA256SUMS`;
4. requires exactly the version-derived `py3-none-any` wheel and sdist names;
5. recomputes both SHA256 values without modifying the candidate files or checksum file;
6. installs that exact retained wheel with `pip --no-deps --force-reinstall` into the disposable runner Python;
7. runs `tools/package_smoke.py` against the installed distribution.

`package_smoke.py` independently checks that the installed distribution version, package `__version__`, and `paic --version` agree with the checked-out tagged source version and that imports resolve from installed `site-packages` rather than the repository source tree.

`strategy.fail-fast` is disabled so one platform failure does not erase evidence from the other matrix children.

This is deliberately a **candidate-byte validation matrix**, not a six-build matrix. A passing result means the same candidate wheel retained from the build job installed and passed PAIC's package smoke on every matrix target.

`prepublish-tag-check` depends on the entire matrix, and PyPI publishing depends on both the matrix and the tag check. No candidate-smoke child has OIDC publishing, attestation, or repository-write permission.

### Evidence boundary

The matrix implementation can be reviewed and unit/static-tested in ordinary pull-request CI. That does **not** prove that a tagged release candidate has already passed the matrix.

The v1 Roadmap item `Cross-platform release matrix` remains incomplete until an intended future release runs the tagged `Release alpha` workflow and records a successful six-child candidate matrix under the actual release procedure.

The already-published `v0.1.0a2` release is not retroactively represented as having passed this future gate.

## Read-only retained-candidate verification

`tools/verify_release_candidate.py` is separate from `tools/release_guard.py` because their write authorities differ:

- `release_guard.py --artifacts-dir ... --checksums ...` belongs to the build job and **creates** `SHA256SUMS`;
- `verify_release_candidate.py` belongs to downstream verification and is strictly read-only.

The read-only verifier requires:

- an alpha version in `X.Y.ZaN` form;
- exactly the expected wheel and sdist in the candidate `dist/` directory;
- exactly two non-empty checksum entries;
- lowercase 64-hex SHA256 values;
- safe flat version-derived artifact filenames with no path separators/traversal;
- exact checksum filename-set equality with the expected candidate;
- recomputed hashes equal to the recorded hashes.

It does not rewrite, normalize, repair, rename, or regenerate any candidate artifact.

## Dry-run boundary

A dry-run still executes the tagged build **and the full six-child candidate matrix**. It stops only after those candidate validations succeed.

Dry-run does not:

- enter the protected PyPI environment;
- mint a PyPI publishing OIDC credential;
- upload to PyPI;
- create GitHub artifact provenance attestations;
- create a GitHub Release.

For a real publish, the build commit SHA becomes the immutable workflow identity for later validation. The workflow rechecks that the requested release tag still resolves to that same build commit:

- after the candidate matrix and immediately before the PyPI publishing job;
- immediately after PyPI publication, before hash/fresh-install verification;
- after PyPI verification and immediately before GitHub artifact attestation;
- immediately before creating the GitHub Release.

Post-publication verification checks out the exact build commit SHA rather than trusting the tag again. These checks reduce tag-retargeting risk inside the workflow, but protected release tags remain a required operational control because no CI workflow can prevent an authorized actor from moving an unprotected tag between checks.

## GitHub Actions supply-chain pinning

Every external action used by the release workflow is pinned to a **full 40-character commit SHA**, with the human-readable release version retained in a comment. The workflow policy tests fail if a mutable branch, major-version pointer, or version tag is introduced into a `uses:` line.

The currently reviewed pins are:

```text
actions/checkout
  3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1

actions/setup-python
  5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0

actions/upload-artifact
  043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1

actions/download-artifact
  3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1

actions/attest
  508db95dd578ae2727ebd6217d5ba78e4fbda05d # v4.2.1

pypa/gh-action-pypi-publish
  dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2
```

Updating one of these dependencies requires an explicit reviewed commit that changes the SHA and version comment together.

## PyPI Trusted Publishing setup

The repository intentionally stores no PyPI password or long-lived API token.

Before the first real publish, configure PyPI Trusted Publishing for these exact values:

```text
PyPI project:      portable-ai-context
GitHub owner:      jzhao0
GitHub repository: portable-ai-context
Workflow filename: release.yml
Environment:       pypi
```

If the PyPI project does not yet exist, PyPI supports a **pending publisher** that creates the project on first successful OIDC publication. A pending publisher does not reserve the project name before first publication.

Official references:

- https://docs.pypi.org/trusted-publishers/
- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- https://docs.pypi.org/trusted-publishers/using-a-publisher/

## GitHub `pypi` environment

Create a GitHub Actions environment named exactly:

```text
pypi
```

Recommended protections before a real publish:

- require manual approval by the repository owner/maintainer;
- restrict deployment to protected release tags where available;
- protect `v*` tag creation/modification so ordinary contributors cannot create release identities;
- keep the publishing job limited to artifact download + Trusted Publishing only.

The PyPI publishing OIDC permission (`id-token: write`) exists only on the `pypi-publish` job. A separate post-publication attestation job has its own `id-token: write` plus `attestations: write` permission for GitHub provenance. Neither permission is granted to the build job, candidate-smoke matrix, tag-continuity jobs, post-publication package verification job, or GitHub Release job.

## Trusted publication and attestations

### PyPI Trusted Publishing and PEP 740 attestations

The publish job uses the official PyPA action pinned to the reviewed commit for release `v1.14.2`:

```text
pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2
```

Trusted Publishing exchanges the GitHub Actions OIDC identity for a short-lived PyPI credential; no repository secret is required.

The PyPA action generates and uploads PEP 740-compatible PyPI attestations by default when used with Trusted Publishing. Those attestations bind uploaded distributions to the publishing workflow identity; they do not by themselves prove that the source code is trustworthy.

Official references:

- https://docs.pypi.org/attestations/
- https://docs.pypi.org/attestations/producing-attestations/

### GitHub artifact provenance for future releases

For future releases after this hardening was merged, PAIC adds a second provenance gate **after** PyPI hashes and a fresh exact-version install have both been verified.

The `attest-published` job:

1. downloads the original `release-dists-${release_tag}` Actions artifact produced by the build job;
2. requires exactly the original wheel, sdist, and `SHA256SUMS` files;
3. requires `SHA256SUMS` to contain exactly the expected wheel/sdist entries;
4. recomputes and verifies both distribution SHA256 hashes without changing any artifact bytes;
5. rechecks that the release tag still points to the original build commit;
6. runs the pinned GitHub `actions/attest` action over the wheel, sdist, and `SHA256SUMS`;
7. independently verifies each local subject with `gh attestation verify --repo "$GITHUB_REPOSITORY"`;
8. permits the GitHub Release job to proceed only if all three verifications succeed.

The attestation job has exactly:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
```

It does not check out repository source, rebuild distributions, upload a replacement Actions artifact, or receive a long-lived signing key. `create-storage-record: false` is set explicitly; PAIC does not request linked-artifact storage metadata authority for this file-release provenance step.

GitHub Artifact Attestations use GitHub OIDC and Sigstore. The attestation associates the verified artifact digest with provenance about the GitHub Actions workflow that made the attestation. Consumers can later verify a downloaded release asset with, for example:

```bash
gh attestation verify portable_ai_context-<version>-py3-none-any.whl --repo jzhao0/portable-ai-context
```

An attestation establishes artifact provenance and integrity; it does not guarantee that the artifact is secure or that provider conversation content is authentic.

This control is forward-looking. The already-published `v0.1.0a2` release is not rebuilt, republished, retagged, or retroactively presented as having passed this future provenance job.

Official references:

- https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- https://cli.github.com/manual/gh_attestation_verify
- https://github.com/actions/attest

## Dry-run procedure

A dry-run requires an **existing** release tag because the same tagged-build path is exercised as publish mode.

Before creating the tag:

1. merge the final release-preparation commit to `main`;
2. ensure normal CI is green;
3. update the changelog as appropriate for the intended stage;
4. create and protect the `vX.Y.ZaN` tag on the intended `main` commit.

Then open GitHub Actions → **Release alpha** → **Run workflow** and enter:

```text
release_tag: v0.1.0a2
mode:        dry-run
```

A successful future dry-run proves that the tagged commit builds the exact expected wheel/sdist pair, records their checksums, and that the **same retained wheel bytes** pass package smoke on Ubuntu, Windows, and macOS at Python 3.10 and 3.13. It does not mint a PyPI publishing OIDC credential, upload to PyPI, create a GitHub artifact attestation, or create a GitHub Release.

Do not retroactively infer this evidence for a release whose workflow ran before the candidate matrix existed.

## Publish procedure

Do not select `publish` until all release gates are satisfied, including any evidence limitations that the release notes must disclose.

Run:

```text
release_tag: vX.Y.ZaN
mode:        publish
```

The workflow performs these stages in order:

```text
Tagged main commit
→ build once + twine check + SHA256SUMS + isolated Ubuntu wheel smoke
→ download/re-hash/install/smoke the exact retained wheel on 3 OS × Python 3.10/3.13
→ recheck tag == build commit
→ protected `pypi` environment approval
→ OIDC Trusted Publishing to PyPI
→ recheck tag == build commit
→ compare PyPI-reported SHA256 hashes with original SHA256SUMS
→ fresh exact-version install from PyPI + package smoke
→ download original build artifact + revalidate exact files/checksums
→ recheck tag == build commit
→ GitHub/Sigstore provenance attest wheel + sdist + SHA256SUMS
→ `gh attestation verify` all three original subjects
→ recheck tag == build commit
→ create GitHub Release with the same wheel, sdist, and SHA256SUMS
```

The GitHub Release is created only after exact cross-platform candidate smoke, PyPI hash verification, fresh-install smoke, artifact/checksum revalidation, provenance generation, independent provenance verification, and the final tag-identity check succeed.

## Published artifact verification

`tools/verify_pypi_release.py` reads the PyPI release JSON API and compares the full published filename→SHA256 set against `SHA256SUMS`. Missing files, extra files, or hash mismatches fail closed.

The GitHub Release receives the original build-job wheel, sdist, and `SHA256SUMS`, not files downloaded back from PyPI. For future releases that exercise the attestation path, each of those three files must also pass `gh attestation verify` before the Release is created.

## Failure and recovery boundaries

### Candidate matrix fails before PyPI upload

No package has been published. Keep the matrix evidence and determine whether the failure is platform/Python-specific, a retained-artifact/checksum mismatch, or a package-smoke regression.

Do not bypass the failing matrix child and do not rebuild only for that OS. Fix the source/release preparation on a new commit and produce a new intended release identity according to the release plan. The purpose of the matrix is specifically to test one candidate artifact across targets.

### Other failure before PyPI upload

No package has been published. Fix the problem on a new commit. Do not move an already public release tag to a different commit; create the correct tag/version after the release state is fixed.

If the pre-publish tag-continuity check fails, treat the tag as compromised or incorrectly retargeted. Do not bypass the check; restore the release plan with a correctly protected tag/version.

### PyPI upload succeeds but post-publish verification fails

Treat the release as suspect. Do not create a normal GitHub Release claiming success. This includes a post-publish tag-continuity failure, a PyPI hash mismatch, or a fresh-install failure.

Inspect the failure and, when the release is broken or unsafe, **yank the entire PyPI release** from the PyPI project release-management page and provide a reason. PyPI recommends yanking as the non-destructive response for broken/incompatible/security-problem releases; deletion is more disruptive and should not be the default rollback mechanism.

Official reference:

- https://docs.pypi.org/project-management/yanking/

After remediation, publish a **new version** rather than attempting to overwrite an existing PyPI version.

### PyPI verification succeeds but provenance attestation fails

Do not create the GitHub Release yet. The PyPI files have already passed hash and fresh-install verification, but the release has not satisfied PAIC's future provenance gate.

Investigate the attestation/verification failure without rebuilding, replacing, retagging, or republishing the existing distributions. If retrying the failed workflow job, use the same retained `release-dists-${release_tag}` build artifact and confirm the tag still resolves to the original build commit. Do not claim provenance success until all three original subjects pass `gh attestation verify`.

### PyPI and provenance verification succeed but GitHub Release creation fails

The PyPI files and original build artifacts have already passed the required verification gates. Keep the evidence from the successful workflow run. Resolve the GitHub Release-specific problem without rebuilding or replacing the PyPI files. Any manually recovered GitHub Release must attach the exact stored artifacts/checksums from the successful build run and point to the same immutable tag/build commit.

## Security invariants

- No PyPI API token/password or artifact-signing private key is committed or stored as a repository secret for this workflow.
- `id-token: write` is granted only to the PyPI publishing job and the separate artifact-attestation job, each for a distinct short-lived OIDC purpose.
- `attestations: write` is granted only to the post-publication artifact-attestation job.
- Every external release-workflow action is pinned to a reviewed full commit SHA.
- The build job creates one candidate wheel/sdist/checksum set; the candidate-smoke matrix never rebuilds or rewrites it.
- Every candidate-smoke child downloads the original retained artifact, verifies it read-only, installs the exact retained wheel, and has only `contents: read` repository permission.
- The PyPI publishing job does not check out or execute repository code; it only downloads the prebuilt artifact and calls the pinned official PyPA publishing action.
- The attestation job does not check out repository code or rebuild artifacts; it only downloads the original build artifact, revalidates it, attests it, and verifies the resulting attestations.
- Checkout credentials are not persisted in jobs that check out the release source/build commit.
- The tagged commit must already be in `main` history.
- Tag identity is rechecked against the original build commit after the candidate matrix and before upload, after upload, before attestation, and before GitHub Release creation.
- Post-publication verification uses the exact build commit rather than re-trusting a movable tag.
- The release tag, project version, package version, built artifact names, candidate-matrix hashes, PyPI hashes, installed version, original checksums, and attested subject digests must remain one coherent release identity.
- The workflow defaults to `dry-run`; publish requires an explicit mode choice and the protected `pypi` environment.
- Dry-run runs the full exact-candidate matrix but never creates final-release attestations or uploads to PyPI.
- Existing PyPI versions and already-published release tags are never intentionally overwritten or retroactively rebuilt.
