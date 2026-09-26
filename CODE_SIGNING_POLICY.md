# Code signing policy

This policy covers official Windows release installers for Shiguang Gallery.

Free code signing provided by SignPath.io, certificate by SignPath Foundation. The project is applying for this service. Releases remain unsigned unless and until SignPath Foundation accepts the project and a specific artifact completes signing.

## Release artifacts

Official installers are built from this repository's `main` branch and published through the [release repository](https://github.com/zhongguodecainiao/shiguang-gallery-updates/releases). Only artifacts built from reviewed source in this repository may be submitted for signing.

## Team roles

- Committer and reviewer: [zhongguodecainiao](https://github.com/zhongguodecainiao)
- Signing approver: [zhongguodecainiao](https://github.com/zhongguodecainiao)

All maintainers must use multi-factor authentication for repository and signing-service access.

## Privacy policy

The application does not transfer photos, albums, or other user content to networked systems. A public update manifest is fetched only when the user explicitly requests an update check.

## Signing status

This project is applying for free code signing through SignPath Foundation. Until an application is accepted and an artifact is signed, released files are not represented as SignPath-signed.
