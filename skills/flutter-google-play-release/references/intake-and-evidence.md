# Intake and evidence

Use this reference before creating or updating a Play app. Keep the release
contract in a task file or working note, but never include secrets.

## Product and distribution decisions

| Field | Required evidence |
|---|---|
| Developer account | Current authenticated Console account |
| App record | Search current app list by package and title |
| App/game and category | Product behavior and user confirmation |
| Package/application ID | Release Gradle config and merged manifest |
| Default locale | User/product decision before app creation |
| Free/paid | Explicit user decision; surface irreversibility |
| Countries/regions | Explicit distribution decision |
| Target audience | Intended audience, content, and Families implications |
| Track/rollout | User decision: internal/closed/open/production and percentage |

## Release artifact

| Field | Primary source |
|---|---|
| Version name/code | Final merged manifest and Play parsed-artifact table |
| min/target SDK | Final merged manifest and Play parsed-artifact table |
| Package | Final merged manifest and Play parsed-artifact table |
| Permissions | Final merged manifest, including library contributions |
| Signing identity | AAB certificate matched to intended upload keystore |
| ABI/device support | Play parsed-artifact table and preview delta |
| R8/symbol files | Build outputs and Play attachment indicator |

Useful locations vary by Android Gradle Plugin version. Search rather than
assuming one path:

```text
build/app/outputs/bundle/release/app-release.aab
build/app/intermediates/**/release/**/AndroidManifest.xml
build/app/outputs/logs/manifest-merger-release-report.txt
build/app/outputs/mapping/release/{mapping,resources,usage}.txt
```

## Privacy and Data safety

Trace all of these before answering “No”:

- Flutter/Dart dependencies and Android transitive SDKs;
- network clients, domains, APIs, WebViews, authentication, and backends;
- analytics, attribution, ads, crash reporting, social, maps, payment, and
  push-notification SDKs;
- local persistence, cloud sync, file/media pickers, clipboard, contacts,
  location, camera, microphone, device identifiers, and advertising ID;
- user-generated content and user-to-user interaction;
- account creation/deletion and access restrictions.

For every collected/shared data type, record:

```text
data type → source → destination → purpose → retention → optional/required
```

Local-only data is not automatically “collected,” but confirm no SDK transmits
it. A privacy policy must describe actual behavior and be publicly reachable.

## Store listing and media

Collect:

- title, short description, and full description for each locale;
- support email, website, and privacy URL;
- icon, feature graphic, phone screenshots, and tablet screenshots;
- source locale and intended fallback behavior;
- category/tags and release notes.

Validate file dimensions, format, alpha restrictions, orientation, legibility,
and current live Console count limits. Track phone, 7-inch tablet, and 10-inch
tablet groups independently.

## IARC content inventory

Inspect actual gameplay, copy, audio, store screenshots, and user interaction:

- violence against humans or fictional/non-human characters;
- realism, frequency, distance, blood/gore, and consequences;
- fear/horror;
- sexual content/nudity;
- profanity/crude humor;
- alcohol, tobacco, drugs;
- simulated/real gambling and purchasable random items;
- user communication, location sharing, unrestricted web access;
- digital purchases.

Do not omit mild cartoon/fantasy violence merely because the art is cute or
abstract.

## Readiness rule

Proceed to Console mutation only when identity, pricing, signing, privacy, data
flows, and required assets are known. Preserve unknown fields as blockers or
ask the user; never fill them optimistically.
