# Hide DEEIX Chat Promotion

## Goal

Remove the DEEIX Chat promotion from the production Creative Console without running a frontend build on the low-memory production host.

## Design

The source JSX promotion block will be removed so any future frontend build is clean. The currently deployed image is pinned by digest, so production will also mount a host-owned `index.production.html` over `/app/frontend/dist/index.html`. That index matches the pinned image's asset names and contains a narrowly scoped CSS rule that hides only an `aside` whose direct child links to the DEEIX Chat repository.

The Compose production override owns this bind mount. The base Compose file and application data volumes remain unchanged.

## Safety

- No dependency installation, image build, or frontend compilation.
- The existing image digest and application bundle remain unchanged.
- The overlay can be removed by deleting its single Compose volume entry and recreating the container.
- A future image upgrade must refresh the index overlay because asset filenames may change.

## Verification

- Validate the merged Compose configuration.
- Recreate only `grok2api-v3` and wait for its existing health check.
- Verify the public HTML references the expected pinned assets and includes the promotion-hiding rule.
- Verify the promotion source block is absent from JSX.
- Verify public health, active key, legacy key, and invalid-key behavior after recreation.
- Verify the container mount and service logs.
