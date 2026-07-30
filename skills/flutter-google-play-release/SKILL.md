---
name: flutter-google-play-release
description: Prepare, audit, create, update, and safely submit Flutter Android apps to Google Play. Use when Codex needs to plan a first Play launch or follow-up release; build, sign, or inspect an AAB; fill Play Console store listings, media, app-content declarations, Data safety, advertising ID, target audience, or IARC questionnaires; resolve target SDK, edge-to-edge, orientation, R8, AGP, or device-compatibility findings; save a release draft; or submit changes for review. Supports authenticated Play Console browser work while preserving explicit confirmation gates for irreversible app/pricing choices, legal terms, and final review or publication actions.
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
   Execute it only after a fresh, action-time confirmation.
7. Never read out, paste into chat, log, or store keystore passwords, service
   credentials, browser session data, or signing secrets.

## 1. Establish the release contract

Read repository instructions first. For a substantial first launch, use the
project's planning/task workflow when one exists.

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

1. Fill the default locale first, then add approved localizations.
2. Source title, short/full description, contact data, and URLs from committed
   product materials or user-confirmed copy.
3. Enter full `https://` URLs and verify public accessibility.
4. Upload icon, feature graphic, phone screenshots, and each tablet group
   independently. Wait until processing finishes before judging success.
5. Inspect visible errors, preview/cropping, media counts, and disabled/enabled
   Save state after every group.
6. Do not claim a locale is complete merely because it falls back to the
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
4. Fill release notes for every approved locale.
5. Save, preview, and classify findings:
   - **blocker/error**: must be resolved before review;
   - **warning/recommendation**: assess against product behavior and supported
     toolchain; do not make unsafe upgrades merely to silence it;
   - **processing**: wait and recheck.
6. For target SDK, edge-to-edge, orientation, R8, AGP, and large-screen
   findings, read
   [references/android-release-quality.md](references/android-release-quality.md).
7. Save the release into Publishing overview without sending it for review.

## 7. Stop at the final confirmation gate

Present a compact final summary containing:

- app/package, version code/name, free/paid state, track, rollout percentage,
  and countries/regions;
- Play-parsed target SDK and device-support change;
- listing locales and media counts;
- access, ads/AD_ID, Data safety, target audience, privacy URL, and IARC result;
- remaining blockers, warnings, and automatic-check status;
- the exact final button/action that remains.

Ask for a fresh explicit confirmation such as `确认提交审核`. Do not infer it
from earlier requests such as “create,” “upload,” “continue,” or “publish the
app.”

After confirmation, execute only the described final action, then record the
Console status and time. Distinguish **submitted for review**, **in review**,
**approved**, **ready to publish**, and **live**.

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
