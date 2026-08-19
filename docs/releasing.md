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
2. builds wheel + sdist;
3. runs `twine check`;
4. requires exactly the expected wheel and sdist filenames;
5. generates `SHA256SUMS`;
6. installs only the built wheel into an isolated virtual environment;
7. runs the installed-distribution package smoke;
8. uploads the verified build products as a short-lived GitHub Actions artifact.

`dry-run` stops after this stage.

For a real publish, the build commit SHA becomes the immutable workflow identity for later validation. The workflow rechecks that the requested release tag still resolves to that same build commit:

- immediately before the PyPI publishing job;
- immediately after PyPI publication, before hash/fresh-install verification;
- immediately before creating the GitHub Release.

Post-publication verification checks out the exact build commit SHA rather than trusting the tag again. These checks reduce tag-retargeting risk inside the workflow, but protected release tags remain a required operational control because no CI workflow can prevent an authorized actor from moving an unprotected tag between checks.

## GitHub Actions supply-chain pinning

Every external action used by the release workflow is pinned to a **full 40-character commit SHA**, with the human-readable release version retained in a comment. The workflow policy tests fail if a mutable branch, major-version pointer, or version tag is introduced into a `uses:` line.

The currently reviewed pins are:

```text
actions/checkout
  3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1

actions/setup-python
  5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0

actions/upload-artifact
  043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1

actions/download-artifact
  3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8.0.1

pypa/gh-action-pypi-publish
  dc37677b2e1c63e2034f94d8a5b11f265b73ba33  # v1.14.2
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

Recommended protections before the first real publish:

- require manual approval by the repository owner/maintainer;
- restrict deployment to protected release tags where available;
- protect `v*` tag creation/modification so ordinary contributors cannot create release identities;
- keep the publishing job limited to artifact download + Trusted Publishing only.

The PyPI OIDC permission (`id-token: write`) exists only on the `pypi-publish` job. Build, tag-continuity, verification, and GitHub Release jobs do not receive it.

## Trusted publication and attestations

The publish job uses the official PyPA action pinned to the reviewed commit for release `v1.14.2`:

```text
pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2
```

Trusted Publishing exchanges the GitHub Actions OIDC identity for a short-lived PyPI credential; no repository secret is required.

The PyPA action generates and uploads PEP 740-compatible PyPI attestations by default when used with Trusted Publishing. Those attestations bind uploaded distributions to the publishing workflow identity; they do not by themselves prove that the source code is trustworthy.

Official references:

- https://docs.pypi.org/attestations/
- https://docs.pypi.org/attestations/producing-attestations/

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

A successful dry-run proves the tagged commit builds the exact expected wheel/sdist pair, produces checksums, and the built wheel passes an isolated install smoke. It does not mint an OIDC credential and does not contact the PyPI upload endpoint.

## Publish procedure

Do not select `publish` until all release gates are satisfied, including any evidence limitations that the release notes must disclose.

Run:

```text
release_tag: v0.1.0a2
mode:        publish
```

The workflow performs these stages in order:

```text
Tagged main commit
→ build + twine check + SHA256SUMS + isolated wheel smoke
→ recheck tag == build commit
→ protected `pypi` environment approval
→ OIDC Trusted Publishing to PyPI
→ recheck tag == build commit
→ compare PyPI-reported SHA256 hashes with original SHA256SUMS
→ fresh exact-version install from PyPI + package smoke
→ recheck tag == build commit
→ create GitHub Release with the same wheel, sdist, and SHA256SUMS
```

The GitHub Release is created only after PyPI hash verification, fresh-install smoke, and the final tag-identity check succeed.

## Published artifact verification

`tools/verify_pypi_release.py` reads the PyPI release JSON API and compares the full published filename→SHA256 set against `SHA256SUMS`. Missing files, extra files, or hash mismatches fail closed.

The GitHub Release receives the original build-job wheel, sdist, and `SHA256SUMS`, not files downloaded back from PyPI.

## Failure and recovery boundaries

### Failure before PyPI upload

No package has been published. Fix the problem on a new commit. Do not move an already public release tag to a different commit; create the correct tag/version after the release state is fixed.

If the pre-publish tag-continuity check fails, treat the tag as compromised or incorrectly retargeted. Do not bypass the check; restore the release plan with a correctly protected tag/version.

### PyPI upload succeeds but post-publish verification fails

Treat the release as suspect. Do not create a normal GitHub Release claiming success. This includes a post-publish tag-continuity failure, a PyPI hash mismatch, or a fresh-install failure.

Inspect the failure and, when the release is broken or unsafe, **yank the entire PyPI release** from the PyPI project release-management page and provide a reason. PyPI recommends yanking as the non-destructive response for broken/incompatible/security-problem releases; deletion is more disruptive and should not be the default rollback mechanism.

Official reference:

- https://docs.pypi.org/project-management/yanking/

After remediation, publish a **new version** rather than attempting to overwrite an existing PyPI version.

### PyPI verification succeeds but GitHub Release creation fails

The PyPI files have already been verified against the original `SHA256SUMS`. Keep the evidence from the successful workflow run. Resolve the GitHub Release-specific problem without rebuilding or replacing the PyPI files. Any manually recovered GitHub Release must attach the exact stored artifacts/checksums from the successful build run and point to the same immutable tag/build commit.

## Security invariants

- No PyPI API token/password is committed or stored as a repository secret for this workflow.
- `id-token: write` is scoped only to the publishing job.
- Every external release-workflow action is pinned to a reviewed full commit SHA.
- The publishing job does not check out or execute repository code; it only downloads the prebuilt artifact and calls the pinned official PyPA publishing action.
- Checkout credentials are not persisted in jobs that check out the release source/build commit.
- The tagged commit must already be in `main` history.
- Tag identity is rechecked against the original build commit before upload, after upload, and before GitHub Release creation.
- Post-publication verification uses the exact build commit rather than re-trusting a movable tag.
- The release tag, project version, package version, built artifact names, PyPI hashes, and installed version must agree.
- The workflow defaults to `dry-run`; publish requires an explicit mode choice and the protected `pypi` environment.
- Existing PyPI versions are never intentionally overwritten.
