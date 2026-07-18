# Verification And Cleanup

Use the repository's required Flutter command wrapper throughout. Substitute real package and app identifiers discovered from the target project.

## Static And Repository Checks

1. Run the repository formatter on changed Dart files.
2. Resolve dependencies and inspect the lockfile diff.
3. Run analysis and all relevant tests.
4. Search for stale identifiers, duplicate Firebase initialization, duplicate top-level handlers, temporary crash code, and credentials.
5. Review generated native diffs and verify every selected platform appears in `firebase_options.dart`.
6. Run `git diff --check` and compare final status with the recorded baseline.

Do not hide analyzer findings by broadly excluding generated or build directories. Add a narrow exclusion only when the analyzer demonstrably traverses third-party generated sources and the repository accepts that policy.

## Build Matrix

Build every selected release platform supported by the machine and repository. At minimum for a mobile-only app, run the relevant Android release build and an unsigned or otherwise locally valid iOS release build.

Record skipped builds with the concrete missing SDK, signing, network, or host-platform constraint. One successful platform does not validate another.

When the app uses flavors, repeat configuration and builds for every Firebase-backed flavor. Check that artifacts contain the intended project/app identifiers.

## Analytics Delivery

Use a development device or emulator and current Firebase DebugView instructions.

### Android

Enable Analytics debug mode for the exact application ID:

```sh
adb shell setprop debug.firebase.analytics.app <android-application-id>
```

Launch and interact with the app. Check device logs for Analytics initialization, accepted events, and upload/network success. Confirm the same device and events appear in Firebase Console > Analytics > DebugView.

Disable debug mode after verification:

```sh
adb shell setprop debug.firebase.analytics.app .none.
```

### Apple Platforms

Add `-FIRDebugEnabled` to the temporary Xcode scheme launch arguments, run the app, inspect device logs, and confirm events in DebugView. Remove it or run with `-FIRDebugDisabled` after verification. Do not commit a shared scheme with debug collection forced on unless the repository explicitly requires it.

### Evidence Standard

Require both local delivery evidence and console evidence. A logged `screen_view`, `session_start`, or explicit test event plus a matching DebugView entry is sufficient. Normal Analytics batching without debug mode is not a practical immediate verification signal.

## Crashlytics Delivery

Create the smallest temporary crash trigger that fits the app. Keep it inaccessible in production through a debug-only or temporary local path, and mark every changed line for removal.

Examples include a temporary debug button that throws an uncaught exception or a one-time local debug branch that invokes the supported Crashlytics test crash API. Do not commit or ship the trigger.

Verify this sequence:

1. Install and launch a development build on the intended Firebase app.
2. Trigger exactly one fatal crash.
3. Relaunch the app so pending crash data can upload.
4. Inspect platform logs with current Crashlytics debug logging enabled when necessary.
5. Confirm the report appears in Firebase Console > Crashlytics for the correct app, version, and build.
6. Confirm stack frames are readable. If obfuscation or split debug info is used, verify symbol upload using the same release settings.

Do not substitute a caught exception or a non-fatal record when validating fatal crash collection.

## Normal-Package Restoration

After console verification:

1. Remove the test-crash trigger and all temporary UI/routes/flags.
2. Disable Android Analytics debug properties.
3. Remove Apple debug launch arguments and temporary verbose logging.
4. Remove test-only imports and dependencies.
5. Reformat, analyze, and retest.
6. Rebuild normal release artifacts for every selected platform.
7. Re-run secret and stale-identifier scans.
8. Review Git status against the baseline and retain only intended integration files.

## Final Report Template

Report results using these headings:

- **Remote:** account, project, Analytics state, registered apps and identifiers.
- **Code:** packages, generated configuration, initialization, handlers, native wiring.
- **Verified:** analysis, tests, builds, Analytics device/DebugView evidence, Crashlytics device/console evidence.
- **Cleaned:** crash trigger, debug properties/arguments, normal rebuild, secret scan.
- **Deferred:** exact unverified item, blocker, and next command or console action.
- **Release:** privacy disclosures, policy, consent, and symbol-upload follow-ups.

Use `verified`, `blocked`, or `not run` precisely. Never label telemetry integration complete solely because code compiles.
