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
