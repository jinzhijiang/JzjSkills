---
name: flutter-google-play-release
description: Prepare, audit, document, create, update, and safely hand off Flutter Android releases to Google Play. Use when Codex needs to maintain canonical multilingual store descriptions and release notes; plan a first Play launch or follow-up release; build, sign, or inspect an AAB; fill Play Console listings, media, app-content declarations, Data safety, advertising ID, target audience, or IARC questionnaires; resolve Android release-quality findings; save a release draft; hand the final review submission to the user; or commit and tag the exact build after submission.
---

# Release Flutter apps through Google Play

Treat a Play release as an evidence-backed workflow with separate local and
Console states. Never turn a successful build or a saved form into a claim that
the app has been submitted, approved, or published.

## Apply the safety contract

1. Use repository facts for product, privacy, data, permission, and content
   claims. Do not invent assurances such as encryption or no collection.
2. Recheck the current Play Console UI and policy requirements. Saved examples
   and field names may drift.
3. Separate these action classes:
   - read-only audit and planning;
   - reversible preparation such as saving forms, uploading media, and saving a
     release draft;
   - irreversible or externally consequential actions.
4. Obtain an explicit decision before creating an app when identity, package,
   default locale, type, or free/paid status is unresolved.
5. Obtain explicit authority before accepting developer, IARC, or other legal
   terms on the user's behalf.
6. Always stop immediately before **Send for review**, **Submit changes for
   review**, **Start rollout**, **Publish**, or an equivalent final action.
   The user performs this final action; do not click it on the user's behalf.
7. Never read out, paste into chat, log, or store keystore passwords, service
   credentials, browser session data, or signing secrets.

## 1. Establish the release contract and canonical docs

Read repository instructions first. For a substantial first launch, use the
project's planning/task workflow when one exists.

Before building, uploading, or editing Play Console, locate or create:

```text
docs/store/google-play-description.md
docs/store/google-play-release-notes.md
```

Treat these as the source of truth:

- `google-play-description.md`: title, short description, and full description
  for every active Play locale;
- `google-play-release-notes.md`: append-only sections keyed by version name and
  versionCode, with notes for every active Play locale.

Update them from shipped repository facts first, validate field lengths and
privacy claims, then copy their content into Play Console. Do not reconstruct
canonical copy from the Console after submission. If the repository already
uses equivalent canonical files, preserve its names instead of creating
duplicates.

Read [references/release-document-contract.md](references/release-document-contract.md)
when creating, migrating, or validating these files.

Capture the following facts before changing Play Console:

- developer account and whether the app record already exists;
- app name, package/application ID, app/game type, default locale, category;
- free/paid decision, countries/regions, target audience;
- version name/code, min/target SDK, Flutter/FVM/toolchain versions;
- account/login behavior, ads, IAP, analytics, crash reporting, backend,
  third-party SDKs, local/remote storage, permissions, and data flows;
- content requiring IARC disclosure: violence, fear, sexuality, language,
  gambling, drugs, user interaction, location sharing, or purchases;
- privacy URL, support email/site, listing copy, icon, feature graphic, and
  phone/tablet media.

Use [references/intake-and-evidence.md](references/intake-and-evidence.md) for
the full evidence matrix. Mark unknowns as unknown; do not convert them into
negative declarations.

## 2. Audit and build the release artifact

1. Inspect `pubspec.yaml`, Gradle files, dependency lockfiles, source data
   flows, main and merged manifests, signing configuration, and store assets.
2. In an FVM repository, invoke `$flutter-use-fvm` when available and use:

   ```bash
   fvm flutter analyze
   fvm flutter test
   fvm flutter build appbundle --release
   ```

   Otherwise follow the repository's pinned Flutter command contract.
3. Verify the actual release AAB, not only the command exit code:

   ```text
   build/app/outputs/bundle/release/app-release.aab
   ```

4. Run the bundled read-only verifier after building:

   ```bash
   python3 <skill-dir>/scripts/verify_flutter_play_release.py \
     <project-root> \
     --expect-package <application-id> \
     --expect-target-sdk <current-required-sdk> \
     --require-r8
   ```

5. Match the AAB signing certificate to the intended upload keystore using
   local certificate tooling without displaying secret values.
6. Treat the release merged/packaged manifest and Play's parsed-artifact table
   as authoritative for package, version, SDK, permissions, orientation, ABI,
   and device support.

Do not upload when package, version code, target SDK, signing identity, data
declarations, or required media are inconsistent.

## 3. Create or select the Play app

1. Use the authenticated Play Console surface requested by the user.
2. Search the developer account for the package/title before creating anything.
3. Reconfirm unresolved irreversible choices, especially package identity and
   free/paid status.
4. Create the app and save the initial declarations only within the authorized
   scope.
5. Verify the resulting Play app record and package binding after the first AAB
   is parsed.

Saving an app record is not submitting it for review.

## 4. Complete listing and media

1. Verify the canonical description document is current before changing the
   Console.
2. Fill the default locale first, then every locale present in the canonical
   document.
3. Source title, short/full description, contact data, and URLs from committed
   product materials or user-confirmed copy.
4. Enter full `https://` URLs and verify public accessibility.
5. Upload icon, feature graphic, phone screenshots, and each tablet group
   independently. Wait until processing finishes before judging success.
6. Inspect visible errors, preview/cropping, media counts, and disabled/enabled
   Save state after every group.
7. Do not claim a locale is complete merely because it falls back to the
   default locale; report fallback explicitly.

Verify current size/count limits in the live Console. Common historical values
are useful for preparation, not as permanent policy.

## 5. Complete app-content declarations

Answer each declaration from the release artifact and source evidence:

- app access/login instructions;
- ads and advertising ID, including SDK-injected `AD_ID`;
- Data safety collection/sharing and security practices;
- target audience and Families implications;
- government, finance, health, news, COVID-19, and other currently required
  forms;
- privacy policy;
- IARC content rating.

For target audience, distinguish “the content can be enjoyed by children” from
“children are a target audience.” Selecting under-13 groups can activate
Families requirements and is a product/policy decision, not a convenience.

Before agreeing to IARC terms, obtain explicit user consent. Then answer from
actual game content, including mild abstract/cartoon violence; do not answer
from the rating you hope to receive.

Use [references/play-console-workflow.md](references/play-console-workflow.md)
for detailed form and browser failure shields.

## 6. Prepare and validate the release draft

1. Use a new version code. Never reuse a code already uploaded to Play.
2. Upload the verified AAB and wait for Play processing to finish.
3. Confirm Play displays the expected version, min API, target SDK, device
   support, permissions, and attached mapping/native symbols.
4. Fill release notes for every active locale from the canonical release-notes
   document. Keep locale opening tag, content, and closing tag on separate lines
   when using Play's combined editor.
5. Save, preview, and classify findings:
   - **blocker/error**: must be resolved before review;
   - **warning/recommendation**: assess against product behavior and supported
     toolchain; do not make unsafe upgrades merely to silence it;
   - **processing**: wait and recheck.
6. For target SDK, edge-to-edge, orientation, R8, AGP, and large-screen
   findings, read
   [references/android-release-quality.md](references/android-release-quality.md).
7. Save the release into Publishing overview without sending it for review.

## 7. Hand final submission to the user

Present a compact final summary containing:

- app/package, version code/name, free/paid state, track, rollout percentage,
  and countries/regions;
- Play-parsed target SDK and device-support change;
- listing locales and media counts;
- access, ads/AD_ID, Data safety, target audience, privacy URL, and IARC result;
- remaining blockers, warnings, and automatic-check status;
- the exact final button/action that remains.

Leave the authenticated Console on the final confirmation page and tell the
user exactly which button remains. The user performs that click. Do not infer
permission from “create,” “upload,” “continue,” “publish,” or any earlier
confirmation.

After the user reports submission, read the Console status when available and
distinguish **submitted for review**, **in review**, **approved**,
**ready to publish**, and **live**.

## 8. Commit and tag the submitted build

Do not wait for approval or live publication. Once the user confirms that the
exact build was submitted for review:

1. Reconfirm the submitted version name and versionCode.
2. Run repository-required validation and inspect the scoped diff.
3. Commit only the release-related local changes, following the repository's
   commit convention.
4. Create an annotated tag:

   ```text
   v<versionName>(<versionCode>)
   ```

   Example: `v1.1.0(3)`.
5. Verify the tag resolves to the release commit.
6. Push the commit or tag only when explicitly requested.

If review is rejected and a replacement AAB is needed, increment versionCode
and create a new commit and tag such as `v1.1.0(4)`. Never move, delete, or
reuse the tag for the previously submitted build.

## Failure shields

- A Play page is dynamic: inspect the current page rather than relying on a
  memorized navigation path.
- If an AAB locator cannot upload, use the browser's file chooser event and set
  the file on the chooser.
- If release-note locale tags are rejected as duplicated, put each opening tag,
  text, and closing tag on separate lines.
- If direct AAB manifest inspection fails, use the release merged/packaged
  manifest plus Play's parsed-artifact table.
- Do not treat an intermediate Flutter/Gradle warning as the final result; wait
  for process completion and verify the output artifact.
- Do not force an unsupported AGP/Gradle/Kotlin combination solely because Play
  recommends a newer optimizer.
- Never leave the user believing that a saved draft was submitted or that a
  submitted release is already published.
- Never wait for the build to become live before creating its submission tag;
  the tag identifies the immutable build sent to review.
