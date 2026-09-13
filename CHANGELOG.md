## [0.11.11](https://github.com/lukislp/studylife-alexa/compare/v0.11.10...v0.11.11) (2026-09-13)


### Bug Fixes

* **k8s:** give probes a 5s timeout so load spikes stop killing pods ([#66](https://github.com/lukislp/studylife-alexa/issues/66)) ([f986ace](https://github.com/lukislp/studylife-alexa/commit/f986ace55f494420b309e1e6a6dde0dc57747221))

## [0.11.10](https://github.com/lukislp/studylife-alexa/compare/v0.11.9...v0.11.10) (2026-09-13)


### Bug Fixes

* **k8s:** close the open egress hole in this namespace ([#65](https://github.com/lukislp/studylife-alexa/issues/65)) ([3446d05](https://github.com/lukislp/studylife-alexa/commit/3446d051d07693e078c1dda3509fb573e253b621))

## [0.11.9](https://github.com/lukislp/studylife-alexa/compare/v0.11.8...v0.11.9) (2026-09-13)


### Bug Fixes

* **k8s:** read-only root filesystem for studylife-alexa ([#64](https://github.com/lukislp/studylife-alexa/issues/64)) ([7c9702e](https://github.com/lukislp/studylife-alexa/commit/7c9702e4dc2a9c657e0e1513ab13e3e8e3579d7a))

## [0.11.8](https://github.com/lukislp/studylife-alexa/compare/v0.11.7...v0.11.8) (2026-09-13)


### Bug Fixes

* **k8s:** add explicit egress policy for the skill pod ([#63](https://github.com/lukislp/studylife-alexa/issues/63)) ([eaa0c6a](https://github.com/lukislp/studylife-alexa/commit/eaa0c6aa7105558e1272ffccee3f5e25eb5e6c93))

## [0.11.7](https://github.com/lukislp/studylife-alexa/compare/v0.11.6...v0.11.7) (2026-09-13)


### Bug Fixes

* **docker:** apply Debian security updates at build time ([#62](https://github.com/lukislp/studylife-alexa/issues/62)) ([9431eb4](https://github.com/lukislp/studylife-alexa/commit/9431eb478136edd9be5f2458eff96d6d926d2e44))

## [0.11.6](https://github.com/lukislp/studylife-alexa/compare/v0.11.5...v0.11.6) (2026-09-13)


### Bug Fixes

* **k8s:** raise the studylife-alexa namespace from PSS baseline to restricted ([#61](https://github.com/lukislp/studylife-alexa/issues/61)) ([631b476](https://github.com/lukislp/studylife-alexa/commit/631b4766523a7df8078b96b63766169d621624fe))

## [0.11.5](https://github.com/lukislp/studylife-alexa/compare/v0.11.4...v0.11.5) (2026-09-12)


### Bug Fixes

* **handlers:** read slot values via get_slot instead of the deprecated get_slot_value ([#52](https://github.com/lukislp/studylife-alexa/issues/52)) ([ad27d94](https://github.com/lukislp/studylife-alexa/commit/ad27d944cc223d4fc55024ba3b3777bc985cb38d))

## [0.11.4](https://github.com/lukislp/studylife-alexa/compare/v0.11.3...v0.11.4) (2026-09-12)


### Bug Fixes

* **handlers:** tolerate offset-aware session timestamps in the intent helpers ([#50](https://github.com/lukislp/studylife-alexa/issues/50)) ([f0ee05d](https://github.com/lukislp/studylife-alexa/commit/f0ee05d3cd080e96390de135585a643b6d73fcc9))

## [0.11.3](https://github.com/lukislp/studylife-alexa/compare/v0.11.2...v0.11.3) (2026-09-12)


### Bug Fixes

* **deps:** bump ruff from 0.16.5 to 0.16.6 ([c189beb](https://github.com/lukislp/studylife-alexa/commit/c189beb606e007d3fd732f4cd34743d11dbb8d39))

## [0.11.2](https://github.com/lukislp/studylife-alexa/compare/v0.11.1...v0.11.2) (2026-09-12)


### Bug Fixes

* **ci:** bump the deployment image tag from the pipeline instead of Flux ([#41](https://github.com/lukislp/studylife-alexa/issues/41)) ([329d1e5](https://github.com/lukislp/studylife-alexa/commit/329d1e5d7c34325e4feb237409e27f6ebbcf0ff4))

## [0.11.1](https://github.com/lukislp/studylife-alexa/compare/v0.11.0...v0.11.1) (2026-09-11)


### Bug Fixes

* **ci:** read-only GITHUB_TOKEN in the Dependabot auto-merge workflow ([9b141d6](https://github.com/lukislp/studylife-alexa/commit/9b141d6268fc9abbfb7852f6bbc54c0d05fb87f0))

# [0.11.0](https://github.com/lukislp/studylife-alexa/compare/v0.10.3...v0.11.0) (2026-09-11)


### Features

* **oauth:** PKCE for the StudyLife account-linking round trip ([7341ac4](https://github.com/lukislp/studylife-alexa/commit/7341ac49cbe2dffce971a8cad716f5883daa3990))

## [0.10.3](https://github.com/lukislp/studylife-alexa/compare/v0.10.2...v0.10.3) (2026-09-11)


### Bug Fixes

* **ci:** push release commits as a deploy key so the default branch can be ruleset-protected ([e1e1a62](https://github.com/lukislp/studylife-alexa/commit/e1e1a62e642057a217d57c24685d300cf4a42775))

## [0.10.2](https://github.com/lukislp/studylife-alexa/compare/v0.10.1...v0.10.2) (2026-09-04)


### Bug Fixes

* **ci:** ignore base image major bumps in Dependabot ([bb8f6bf](https://github.com/lukislp/studylife-alexa/commit/bb8f6bfee09c81bc03b60d42f9d3b0dac81568ec))

## [0.10.1](https://github.com/lukislp/studylife-alexa/compare/v0.10.0...v0.10.1) (2026-09-04)


### Bug Fixes

* **ci:** bump aquasecurity/trivy-action ([eeedace](https://github.com/lukislp/studylife-alexa/commit/eeedace725965248d9a650917cf3c7a283e82eb6))
* **ci:** bump astral-sh/setup-uv from 9.0.0 to 10.0.1 ([a5b652a](https://github.com/lukislp/studylife-alexa/commit/a5b652ad3a743b97f1ae57a7b10d6b1961554b7c))
* **ci:** bump docker/setup-buildx-action from 4.2.0 to 4.3.0 ([1ebf8a1](https://github.com/lukislp/studylife-alexa/commit/1ebf8a1f251b6a37237f1634b8213fb5f5f57025))

# [0.10.0](https://github.com/lukislp/studylife-alexa/compare/v0.9.4...v0.10.0) (2026-09-03)


### Features

* expose Prometheus metrics for intents and HTTP requests ([46fe556](https://github.com/lukislp/studylife-alexa/commit/46fe556d99cc65be3e5529efe013a73fc76fdd04))

## [0.9.4](https://github.com/lukislp/studylife-alexa/compare/v0.9.3...v0.9.4) (2026-09-03)


### Bug Fixes

* **ci:** add Dependabot for github-actions, uv, docker ([8cde911](https://github.com/lukislp/studylife-alexa/commit/8cde911662d015a2af508ffd5df4742a0cd88ff0))

## [0.9.3](https://github.com/lukislp/studylife-alexa/compare/v0.9.2...v0.9.3) (2026-08-31)


### Bug Fixes

* add a dedicated AMAZON.NavigateHomeIntent handler ([a213cb7](https://github.com/lukislp/studylife-alexa/commit/a213cb797798c73f81e493870c4fa4ad7245838b))

## [0.9.2](https://github.com/lukislp/studylife-alexa/compare/v0.9.1...v0.9.2) (2026-08-31)


### Bug Fixes

* match StudyLife's own design system on the account-linking pages, stop mobile input zoom ([5bd4e96](https://github.com/lukislp/studylife-alexa/commit/5bd4e9688d6e9eb1b461d9aa680443a94f1994e1))

## [0.9.1](https://github.com/lukislp/studylife-alexa/compare/v0.9.0...v0.9.1) (2026-08-31)


### Bug Fixes

* remove the instance-URL pre-fill default entirely ([b6b4c38](https://github.com/lukislp/studylife-alexa/commit/b6b4c388452737acd325cd628308c52541ddf5ea))

# [0.9.0](https://github.com/lukislp/studylife-alexa/compare/v0.8.0...v0.9.0) (2026-08-31)


### Bug Fixes

* migrate the OAuth store schema in place for existing deployments ([70d0022](https://github.com/lukislp/studylife-alexa/commit/70d0022d22fa77f54c1251032a80955799bf4e92))


### Features

* multi-tenant account linking - each user picks their own instance ([ea2f513](https://github.com/lukislp/studylife-alexa/commit/ea2f5137ce925edc8c0e9ed5caf5baa714619b5b))

# [0.8.0](https://github.com/lukislp/studylife-alexa/compare/v0.7.2...v0.8.0) (2026-08-31)


### Features

* fetch built-in study program progress via Metrics.GetSummary ([f8b5632](https://github.com/lukislp/studylife-alexa/commit/f8b56322ca3625c03795a9918c4a68f31bd0dc5f)), closes [studylife#114](https://github.com/studylife/issues/114)

## [0.7.2](https://github.com/lukislp/studylife-alexa/compare/v0.7.1...v0.7.2) (2026-08-31)


### Bug Fixes

* pin container timezone to Europe/Berlin ([a356dfa](https://github.com/lukislp/studylife-alexa/commit/a356dfa06c5f72d38f5f0cc68cc0d5b71812a682))

## [0.7.1](https://github.com/lukislp/studylife-alexa/compare/v0.7.0...v0.7.1) (2026-08-31)


### Bug Fixes

* count in-progress sessions towards StudyTimeIntent's totals ([4cc3370](https://github.com/lukislp/studylife-alexa/commit/4cc33709e15fa1ddc9411716f6dd49a3b7a800e6))

# [0.7.0](https://github.com/lukislp/studylife-alexa/compare/v0.6.2...v0.7.0) (2026-08-31)


### Features

* add en-US locale support alongside de-DE ([8dabc7b](https://github.com/lukislp/studylife-alexa/commit/8dabc7bf7f82efdc00895fbcd587bce306f0ba54))

## [0.6.2](https://github.com/lukislp/studylife-alexa/compare/v0.6.1...v0.6.2) (2026-08-30)


### Bug Fixes

* distinguish "not found" from "built-in program has no detail endpoint" ([a8bfe91](https://github.com/lukislp/studylife-alexa/commit/a8bfe91c125bfd3e82a6f07262f8d4f8acb392d9))

## [0.6.1](https://github.com/lukislp/studylife-alexa/compare/v0.6.0...v0.6.1) (2026-08-30)


### Bug Fixes

* fuzzy-match program names, not just pure substring ([9bf733a](https://github.com/lukislp/studylife-alexa/commit/9bf733a492258221ac51ad56cca94ff65a0f0b97))

# [0.6.0](https://github.com/lukislp/studylife-alexa/compare/v0.5.2...v0.6.0) (2026-08-30)


### Features

* add NextSessionIntent, NotesOverviewIntent, ProgramProgressIntent ([5ad509d](https://github.com/lukislp/studylife-alexa/commit/5ad509d715e9913ab400524ff4a4b5070f056722))

## [0.5.2](https://github.com/lukislp/studylife-alexa/compare/v0.5.1...v0.5.2) (2026-08-30)


### Bug Fixes

* German singular/plural grammar, and "letzte Woche" as its own period ([0e56050](https://github.com/lukislp/studylife-alexa/commit/0e560507eac7deb914bb338cd35ff2c78ede0a74))

## [0.5.1](https://github.com/lukislp/studylife-alexa/compare/v0.5.0...v0.5.1) (2026-08-30)


### Bug Fixes

* keep the session open after answering, and fix hour/minute grammar ([aaf19ea](https://github.com/lukislp/studylife-alexa/commit/aaf19ea796ce8654402bc2d36c167820d2b81da4))

# [0.5.0](https://github.com/lukislp/studylife-alexa/compare/v0.4.3...v0.5.0) (2026-08-30)


### Features

* expose the rest of StudyLife's publicly-grantable data via voice ([d6172f8](https://github.com/lukislp/studylife-alexa/commit/d6172f81965696f992fd3459a06be147331e6250))

## [0.4.3](https://github.com/lukislp/studylife-alexa/compare/v0.4.2...v0.4.3) (2026-08-30)


### Bug Fixes

* expose the account-linking endpoints through the Tailscale Funnel ([2719d52](https://github.com/lukislp/studylife-alexa/commit/2719d527cfa015fa3dd16c8ed510da2cfdd85d66))

## [0.4.2](https://github.com/lukislp/studylife-alexa/compare/v0.4.1...v0.4.2) (2026-08-30)


### Bug Fixes

* accept any of Alexa's three regional Account Linking redirect URIs ([670338c](https://github.com/lukislp/studylife-alexa/commit/670338c8372e57dca100ab19200e377118bd1f91))

## [0.4.1](https://github.com/lukislp/studylife-alexa/compare/v0.4.0...v0.4.1) (2026-08-30)


### Bug Fixes

* two production startup crashes found via a real container test ([d118957](https://github.com/lukislp/studylife-alexa/commit/d118957468b698d02864d77959d6ca4d5caffe06))

# [0.4.0](https://github.com/lukislp/studylife-alexa/compare/v0.3.0...v0.4.0) (2026-08-30)


### Features

* account linking via a wrapper around StudyLife's connect flow ([4899f6c](https://github.com/lukislp/studylife-alexa/commit/4899f6c73e386f4e0cb9c30b0637fd0afed3fc93))

# [0.3.0](https://github.com/lukislp/studylife-alexa/compare/v0.2.0...v0.3.0) (2026-08-30)


### Features

* K8s deployment manifests - self-hosted via Flux + Tailscale Funnel ([2ff674d](https://github.com/lukislp/studylife-alexa/commit/2ff674d44d6c98a02e4823a580341cdeb525b227))

# [0.2.0](https://github.com/lukislp/studylife-alexa/compare/v0.1.0...v0.2.0) (2026-08-30)


### Bug Fixes

* call ldconfig by absolute path, add diagnostics ([b54dbf2](https://github.com/lukislp/studylife-alexa/commit/b54dbf2cdbb7e50718e2bada700e2eb5c60dc6e8))
* pin the test job to ubuntu-22.04 instead of patching oscrypto ([6c9505e](https://github.com/lukislp/studylife-alexa/commit/6c9505ea8a74eaabbd9ff8e65a4b8ea98f5d2ab3))
* set OSCRYPTO_USE_OPENSSL for the test job on ubuntu-latest ([e88c6bb](https://github.com/lukislp/studylife-alexa/commit/e88c6bbcc5858fc9593b167f6d084c55eb47a486))
* work around oscrypto's OpenSSL-3 version-detection failure properly ([f49d5c0](https://github.com/lukislp/studylife-alexa/commit/f49d5c0167896db5649b108f519cd494c76e2215))


### Features

* CI pipeline - lint, test, semantic-release, multi-arch Docker build ([98fb3ec](https://github.com/lukislp/studylife-alexa/commit/98fb3ecdb3eccd638a8159fa58eb756693d41858))
