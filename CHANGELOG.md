# Changelog

## [0.1.0-beta8](https://github.com/AzmainMahatab/pyflared/compare/v0.1.0-beta7...v0.1.0-beta8) (2026-03-09)


### Bug Fixes

* **deps:** update dependency cloudflare/cloudflared to v2026.3.0 ([#38](https://github.com/AzmainMahatab/pyflared/issues/38)) ([016a6da](https://github.com/AzmainMahatab/pyflared/commit/016a6da5ecd84bd89a1a757b4c32952399907481))

## [0.1.0-beta7](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta7...v0.1.0-beta7) (2026-03-06)


### ⚠ BREAKING CHANGES

* **core:** ssh, reuse, multiple token management and cleanup improvements
* **parser:** update api and simplify logic

### Features

* **core:** ssh, reuse, multiple token management and cleanup improvements ([614c9ef](https://github.com/AzmainMahatab/pyflared/commit/614c9efb4b72a7a89852ac8d187f01dcb653c9e1))


### Bug Fixes

* **ci:** improve build logic ([631c78f](https://github.com/AzmainMahatab/pyflared/commit/631c78f1b4ca3aff4000b7106521b61a345083e7))
* **deps:** update dependency cloudflare/cloudflared to v2025.11.1 ([#20](https://github.com/AzmainMahatab/pyflared/issues/20)) ([198faea](https://github.com/AzmainMahatab/pyflared/commit/198faea7b9acf51e9af8bb5e41dc1ab8d629e628))
* **deps:** update dependency cloudflare/cloudflared to v2026 ([#26](https://github.com/AzmainMahatab/pyflared/issues/26)) ([a10d9e6](https://github.com/AzmainMahatab/pyflared/commit/a10d9e6f2598b753512f4f33eaa6aafe981d5889))
* **deps:** update dependency cloudflare/cloudflared to v2026.1.2 ([#27](https://github.com/AzmainMahatab/pyflared/issues/27)) ([d76853f](https://github.com/AzmainMahatab/pyflared/commit/d76853fddc4068fce10c105c6cb7b07ce28463b2))
* **deps:** update dependency cloudflare/cloudflared to v2026.2.0 ([#28](https://github.com/AzmainMahatab/pyflared/issues/28)) ([2585a4e](https://github.com/AzmainMahatab/pyflared/commit/2585a4e7c409daff6ae15c45f4e325606825f50f))
* made more backwards compatible ([82c78b0](https://github.com/AzmainMahatab/pyflared/commit/82c78b08edaf4676028f001c3a629ebcf7b7d977))
* **parser:** update api and simplify logic ([bc18b89](https://github.com/AzmainMahatab/pyflared/commit/bc18b89795f5d38a8ce49cab89adcbe55592bbe6))
* pydantic_typer_parse works as expected. ([3eb751e](https://github.com/AzmainMahatab/pyflared/commit/3eb751efdc0fcaedd0ebb3162c8d9bd2401e108b))
* renovate config ([5a0eb68](https://github.com/AzmainMahatab/pyflared/commit/5a0eb68b3bfa4e1d99fad02aadfa44b8b9e91e4c))
* **tunnel:** prompt user for token ([eb3e3a5](https://github.com/AzmainMahatab/pyflared/commit/eb3e3a5379b6d6f88e479ab3c903a93d5613f226))


### Performance Improvements

* **process:** replaced copyleft aiostream, with our own merger. that resulted in significant code reduction. ([554a956](https://github.com/AzmainMahatab/pyflared/commit/554a9561bbaafecbfc72b49af65377162f9927fe))


### Documentation

* add 525 troubleshooting ([42d495a](https://github.com/AzmainMahatab/pyflared/commit/42d495aaecd5054bd00516c9deef0773b5013421))
* update readme and src code docs. ([fbecf92](https://github.com/AzmainMahatab/pyflared/commit/fbecf92933304a04b106d23ae33f9dec46b7c21f))

## [0.0.1-beta7](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta6...v0.0.1-beta7) (2026-01-18)


### Bug Fixes

* massive fix for whl tagging ([5aaed91](https://github.com/AzmainMahatab/pyflared/commit/5aaed9108087fa80d2537764f5d1496d7924abbb))

## [0.0.1-beta6](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta5...v0.0.1-beta6) (2026-01-18)


### Bug Fixes

* docker fix build script 2 ([ee81201](https://github.com/AzmainMahatab/pyflared/commit/ee81201f303ee4fecb46060faedcc507d75bf8b9))

## [0.0.1-beta5](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta4...v0.0.1-beta5) (2026-01-18)


### Bug Fixes

* version bump ([c1cbb9d](https://github.com/AzmainMahatab/pyflared/commit/c1cbb9d1161e2e44c89932f3bcee71f082959f7a))

## [0.0.1-beta4](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta3...v0.0.1-beta4) (2026-01-18)


### Bug Fixes

* docker ci workflow fix ([c2c696c](https://github.com/AzmainMahatab/pyflared/commit/c2c696cd24e8b79b7e9ecb38a02d44a7ad6d4eb7))
* macros build script [#2](https://github.com/AzmainMahatab/pyflared/issues/2) ([c2c696c](https://github.com/AzmainMahatab/pyflared/commit/c2c696cd24e8b79b7e9ecb38a02d44a7ad6d4eb7))

## [0.0.1-beta3](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta2...v0.0.1-beta3) (2026-01-18)


### Bug Fixes

* fix linux build script ([574fda1](https://github.com/AzmainMahatab/pyflared/commit/574fda1679d4ab1f3674025d9f2739c6b4200541))

## [0.0.1-beta2](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta1...v0.0.1-beta2) (2026-01-18)


### Bug Fixes

* fix macOS build script ([9a07362](https://github.com/AzmainMahatab/pyflared/commit/9a07362a2b2e0bf15bd22c99bef60bf50e5535ef))

## [0.0.1-beta1](https://github.com/AzmainMahatab/pyflared/compare/v0.0.1-beta0...v0.0.1-beta1) (2026-01-18)


### Features

* ci/cd setup ([339f814](https://github.com/AzmainMahatab/pyflared/commit/339f814056a1ad5f6a9b2a8378bdb9432619186f))
* ci/cd setup ([c7f67f8](https://github.com/AzmainMahatab/pyflared/commit/c7f67f83040b7c62a9f9961dec0ca3a2b70581bf))


### Bug Fixes

* add build-sdist in cd ([339f814](https://github.com/AzmainMahatab/pyflared/commit/339f814056a1ad5f6a9b2a8378bdb9432619186f))
* add build-sdist in cd ([9fcd49e](https://github.com/AzmainMahatab/pyflared/commit/9fcd49e95cb6dd3602ea83483230545bbebbfba8))
* broken reference ([1ac3d24](https://github.com/AzmainMahatab/pyflared/commit/1ac3d242dca190eacf0ee1249bd3822700d52791))
* ci/cd workflow ([1ac3d24](https://github.com/AzmainMahatab/pyflared/commit/1ac3d242dca190eacf0ee1249bd3822700d52791))
* move to SemVer from PEP 440 for release-please ([ebf6d65](https://github.com/AzmainMahatab/pyflared/commit/ebf6d65c116024420337ad63c819a36069c8be9f))
* refactor cmd apis ([79d5c68](https://github.com/AzmainMahatab/pyflared/commit/79d5c68652714562d2f16d9ac5f300a35c23242f))
* refactor design and api ([339f814](https://github.com/AzmainMahatab/pyflared/commit/339f814056a1ad5f6a9b2a8378bdb9432619186f))
* refactor design and api ([c7f67f8](https://github.com/AzmainMahatab/pyflared/commit/c7f67f83040b7c62a9f9961dec0ca3a2b70581bf))


### Documentation

* Enhance README ([339f814](https://github.com/AzmainMahatab/pyflared/commit/339f814056a1ad5f6a9b2a8378bdb9432619186f))
* Enhance README ([b408158](https://github.com/AzmainMahatab/pyflared/commit/b408158bc8284cb3122bfc2e91ae42c3c9c97aca))
* improve documentation ([79d5c68](https://github.com/AzmainMahatab/pyflared/commit/79d5c68652714562d2f16d9ac5f300a35c23242f))
