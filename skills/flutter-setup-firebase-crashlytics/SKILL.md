---
name: flutter-setup-firebase-crashlytics
description: Configure Flutter apps with Firebase Core, Google Analytics, and Firebase Crashlytics using the Firebase CLI and FlutterFire CLI. Use when creating or reusing a Firebase project, registering selected Flutter platforms, generating Firebase configuration, initializing Firebase before runApp, wiring uncaught Flutter and platform errors to Crashlytics, verifying Analytics DebugView and test crash delivery, or repairing an incomplete FlutterFire integration. Default to all three SDKs; omit Analytics only when the caller explicitly requests it.
---

# Flutter Firebase And Crashlytics Setup

Integrate Firebase Core, Google Analytics, and Crashlytics into an existing Flutter project. Carry the work through configuration, code changes, builds, device verification, cleanup, and repository validation after remote changes are approved.

## Required References

Read [integration-contract.md](references/integration-contract.md) before changing dependencies, source files, native projects, or Firebase resources.

Read [verification.md](references/verification.md) before running builds or claiming that Analytics or Crashlytics works.

## Defaults And Boundaries

- Install `firebase_core`, `firebase_analytics`, and `firebase_crashlytics` by default.
- Omit Analytics only when the caller explicitly excludes it. Explain that Crashlytics breadcrumb context will then be reduced.
- Configure only platforms the app ships or the caller requests. A dependency-generated desktop registrant does not authorize creating a remote Firebase app for that platform.
- Use `flutterfire configure` to create client configuration. Never handwrite Firebase app IDs, API keys, sender IDs, or measurement IDs.
- Treat generated client configuration as non-secret and normally commit it. Never commit service-account JSON, private keys, server credentials, access tokens, or downloaded admin credentials.
- Preserve the target repository's startup behavior, error handlers, command wrappers, architecture, formatting, and generated-file policy.
- Do not add unrelated Firebase products.

## Workflow

### 1. Inspect The Target Project

1. Read `AGENTS.md`, repository skills, Trellis or other workflow files, and layer-specific specifications before editing.
2. Inspect `pubspec.yaml`, entrypoints, flavors, platform folders, bundle/application IDs, minimum deployment targets, existing Firebase files, native build configuration, and Git status.
3. Determine whether commands must use `fvm flutter` and `fvm dart` or standard `flutter` and `dart`. Use one command family consistently.
4. Record the clean baseline and preserve unrelated modifications.
5. Identify the exact shipped/requested platforms. Do not infer remote platform scope from generated plugin registrants.

### 2. Refresh Tool And Product Knowledge

1. Read the current official FlutterFire setup, Analytics, Crashlytics, DebugView, and symbol-upload documentation.
2. Inspect the installed `firebase --version`, relevant `firebase ... --help`, `flutterfire --version`, and `flutterfire configure --help` output through the target project's Dart command environment.
3. Verify current platform support, minimum OS requirements, native plugin wiring, symbol requirements, and CLI flags. Do not reuse versions or native paths from another project.
4. Install or upgrade a global CLI only when necessary and compatible with repository policy. Report any environment change.

### 3. Establish The Remote Change Gate

Before a command can create or mutate remote resources, present or derive all applicable values:

- authenticated Firebase account;
- existing project or proposed immutable project ID and display name;
- Google Analytics enablement and required property settings;
- selected platforms;
- Android application IDs and Apple bundle IDs for every flavor being configured.

Prefer an existing matching Firebase project and app registration. If an immutable ID, account, Analytics choice, or platform identifier remains ambiguous, ask one focused question and do not perform the affected remote write. Once the caller approves the concrete plan, continue without repeated confirmation unless the plan changes.

### 4. Configure Dependencies And Firebase Apps

1. Add the default three packages with the selected Flutter command. Let pub resolve versions compatible with the project.
2. Run `flutterfire configure` with explicit project and platform arguments supported by the installed CLI. Reuse matching remote apps where possible.
3. Re-run configuration after adding Crashlytics so required product-specific native wiring is generated.
4. Review every generated or modified file. Confirm that identifiers match the intended project, flavor, and platform.
5. Keep generated platform files and `lib/firebase_options.dart` consistent with repository policy.

### 5. Integrate Runtime Error Reporting

1. Call `WidgetsFlutterBinding.ensureInitialized()` before Firebase initialization.
2. Initialize Firebase with generated `DefaultFirebaseOptions.currentPlatform` before `runApp` on configured platforms only.
3. Install Crashlytics handlers only on platforms currently supported and configured for Crashlytics.
4. Report fatal Flutter framework errors and uncaught asynchronous platform errors.
5. Preserve and compose with existing `FlutterError.onError`, `PlatformDispatcher.instance.onError`, zones, logging, startup guards, and app bootstrap behavior. Avoid duplicate reporting.
6. Do not silently swallow initialization failures or change production collection policy without an explicit product decision.
7. Inspect the generated native wiring and build output. Apply manual Android or Apple changes only when current official documentation and concrete build evidence require them.

### 6. Verify End To End

Follow [verification.md](references/verification.md). At minimum:

1. Format changed Dart files and run dependency resolution, analysis, and relevant tests.
2. Build every selected release platform supported by the local environment.
3. Run a development build on a device or emulator and verify Analytics events in device logs and Firebase DebugView.
4. Add a clearly temporary test-crash trigger, produce one crash, relaunch the app, and verify delivery in device logs and the Crashlytics console.
5. Remove the temporary trigger, disable Analytics debug mode, rebuild a normal package, and repeat static checks.
6. Review the final diff and scan for credentials and values copied from unrelated projects.

Do not treat package resolution, compilation, or a successful app launch as proof that telemetry reached Firebase.

## Completion Contract

- Report the Firebase project, registered platforms, packages, generated files, runtime handler changes, and native wiring actually applied.
- Separate verified results from blocked or deferred checks. Include the exact blocker and the command or console step still required.
- Remind the caller to update the App Store App Privacy disclosure, Google Play Data safety form, and privacy policy for Analytics and crash diagnostics before release.
- Leave the repository with no temporary crash entrypoint, debug property, test-only launch argument, credential, or unrelated edit introduced by this integration.

## Official Sources

- [Add Firebase to a Flutter app](https://firebase.google.com/docs/flutter/setup)
- [Get started with Google Analytics for Flutter](https://firebase.google.com/docs/analytics/flutter/get-started)
- [Get started with Crashlytics for Flutter](https://firebase.google.com/docs/crashlytics/flutter/get-started)
- [Analytics DebugView](https://firebase.google.com/docs/analytics/debugview)
- [Readable Crashlytics reports for Flutter](https://firebase.google.com/docs/crashlytics/flutter/get-deobfuscated-reports)
