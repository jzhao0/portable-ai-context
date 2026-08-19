# Future release artifact provenance

Tracking issue: #73

Portable AI Context's release workflow already uses a protected immutable tag, PyPI Trusted Publishing, SHA256 checksums, PyPI hash comparison, and a fresh exact-version install smoke. Future published versions add one more gate before the GitHub Release is created: GitHub Artifact Attestations for the exact original build subjects.

This document describes the workflow contract. It does **not** retroactively add an attestation to the already-published `v0.1.0a2` release, and it does not mark the v1 `Signed releases / checksums` roadmap item complete.

## Why provenance is after publication verification

The publish chain is intentionally ordered:

```text
build tagged artifacts
→ recheck immutable tag
→ PyPI Trusted Publishing
→ verify PyPI hashes against original build artifact
→ fresh exact-version install smoke
→ attest the exact original build subjects
→ verify those attestations against this repository
→ create GitHub Release
```

A dry-run stops after the build/validation stage. A candidate that was never intentionally published, or a publication whose PyPI verification failed, therefore does not receive the project's final-release provenance gate.

## Attested subjects

The attestation job downloads the existing `release-dists-${release_tag}` Actions artifact. It does not rebuild.

The exact subjects are:

```text
portable_ai_context-<version>-py3-none-any.whl
portable_ai_context-<version>.tar.gz
SHA256SUMS
```

Before signing, `tools/verify_release_subjects.py` independently requires:

- exactly those three files;
- exact versioned wheel/sdist filenames;
- exactly two checksum entries;
- only the expected wheel and sdist in `SHA256SUMS`;
- recomputed wheel and sdist SHA256 values equal the recorded checksums.

The job also re-fetches the release tag and requires it still to resolve to the build job's immutable commit.

## Attestation implementation

The workflow pins the official unified GitHub action to the full reviewed commit:

```text
actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d
v4.2.1
```

The job grants only the permissions needed for repository provenance:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
```

It explicitly uses:

```yaml
create-storage-record: false
```

PAIC does not need an organization Linked Artifacts storage record for this gate, so the workflow does not request `artifact-metadata: write`.

The action uses GitHub's OIDC/Sigstore attestation path; no long-lived signing private key or repository signing secret is introduced.

## Independent verification before GitHub Release

After the attestation action succeeds, the same local wheel, sdist, and checksum file are each checked with:

```text
gh attestation verify <subject> --repo "$GITHUB_REPOSITORY"
```

The `github-release` job depends on the successful `attest-published` job. A failed attestation or verification therefore prevents GitHub Release creation.

## Evidence boundary

Normal pull-request CI can verify only the workflow and local subject-validation contract. It intentionally cannot mint a real release provenance attestation because `attest-published` runs only when the release workflow is explicitly dispatched with:

```text
mode = publish
```

A future release must therefore record live evidence that:

- the attestation job actually ran;
- all three subjects were accepted;
- `gh attestation verify` succeeded for every subject;
- the GitHub Release was created only afterward.

Until that happens, documentation should say that provenance is **configured for future releases**, not that every PAIC release is already signed/attested.

## What provenance does and does not prove

A valid GitHub artifact attestation provides cryptographically verifiable build provenance binding an artifact digest to the GitHub Actions workflow identity that produced the attestation.

It does not prove:

- that an imported AI conversation came from the claimed provider/account;
- that transcript text itself is true or authentic;
- that a self-consistent `.aicb` bundle was authored by a particular person;
- that every historical PAIC release has an attestation;
- that v1 signing/backward-compatibility policy is finalized.

The existing SHA256 and `.aicb` integrity model remains an internal consistency mechanism; provenance is a separate release-supply-chain layer.
