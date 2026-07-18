# Integration Contract

Use this contract to adapt the Firebase integration to the target Flutter repository. Treat placeholders as values to discover, never as literal configuration.

## Preflight Inventory

Collect the following before editing:

| Area | Required evidence |
| --- | --- |
| Repository | Instructions, workflow, dirty files, generated-file policy, command wrapper |
| Flutter | SDK constraint, package manager, entrypoints, flavors, build modes |
| Platforms | Shipped/requested platforms and local build capability |
| Identifiers | Android application IDs and Apple bundle IDs per flavor |
| Existing Firebase | Dependencies, `firebase_options.dart`, platform config, `.firebaserc`, native plugins/scripts |
| Startup | `main`, binding initialization, zones, error handlers, logging, dependency injection |
| Release | Obfuscation, `--split-debug-info`, symbol upload, CI/CD, privacy declarations |

Search the full repository for existing Firebase identifiers before creating apps. Distinguish an intentional multi-environment setup from stale generated files.

## Command Contract

Choose `<flutter-command>` as `fvm flutter` when the repository is FVM-managed; otherwise use `flutter`. Choose `<dart-command>` the same way. Do not mix a global Flutter SDK into an FVM project.

Refresh current CLI behavior before using examples:

```sh
firebase --version
firebase login:list
firebase projects:list
firebase projects:create --help
<dart-command> pub global run flutterfire_cli:flutterfire --version
<dart-command> pub global run flutterfire_cli:flutterfire configure --help
```

If the activated `flutterfire` executable already resolves through the correct Dart SDK, direct `flutterfire` commands are acceptable. Prefer the explicit `<dart-command> pub global run ...` form when PATH would select the wrong or missing Dart executable.

Add the default SDKs without pinning versions copied from another project:

```sh
<flutter-command> pub add firebase_core firebase_analytics firebase_crashlytics
```

Invoke configuration with only flags supported by current `--help`. Supply explicit values instead of relying on an interactive default when automation is required:

```sh
<dart-command> pub global run flutterfire_cli:flutterfire configure \
  --project=<firebase-project-id> \
  --platforms=<comma-separated-platforms>
```

Add current platform-specific identifier flags when the CLI supports them and when automatic discovery is ambiguous. Never assume a single application ID applies to every flavor.

## Remote Resource Review

Present this table before creating remote resources:

| Field | Planned value | Evidence or approval |
| --- | --- | --- |
| Firebase account | `<account-email>` | authenticated CLI account |
| Project mode | reuse or create | project list and caller intent |
| Project ID | `<firebase-project-id>` | explicit approval if new; immutable |
| Display name | `<display-name>` | caller or product metadata |
| Analytics | enabled by default | explicit exclusion required to disable |
| Analytics region/settings | `<country-timezone-currency>` | console values or caller approval |
| Platforms | `<platform-list>` | release configuration |
| Android IDs | `<application-id-per-flavor>` | Gradle configuration |
| Apple IDs | `<bundle-id-per-flavor>` | Xcode project configuration |

Do not create a speculative project just to continue local code work. When a remote project already exists, verify account ownership and identifiers before registration.

## Generated Configuration

Expect FlutterFire CLI to generate or update `lib/firebase_options.dart` and platform/native integration files. Current tools may also modify Gradle plugins or Apple build phases.

- Inspect generated changes instead of recreating them manually.
- Commit client Firebase options unless repository policy intentionally injects them in CI.
- Treat Firebase web/mobile API keys and app IDs as identifiers, not server secrets. Still restrict API keys according to Firebase guidance.
- Reject service-account files, private key material, refresh tokens, admin SDK credentials, and CI secrets from Git.
- Re-run configuration whenever platforms or Firebase products change.

## Runtime Initialization

Adapt initialization to the app's architecture. For a typical Android/iOS-only app, the essential order is:

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  installCrashReporting();
  runApp(const App());
}
```

For a multi-platform app, derive guards from the platforms actually generated in `firebase_options.dart` and from the current plugin support matrix. Do not call `DefaultFirebaseOptions.currentPlatform` on an unconfigured platform.

Compose with existing handlers instead of overwriting them blindly:

```dart
void installCrashReporting() {
  final previousFlutterError = FlutterError.onError;
  FlutterError.onError = (details) {
    previousFlutterError?.call(details);
    FirebaseCrashlytics.instance.recordFlutterFatalError(details);
  };

  final previousPlatformError = PlatformDispatcher.instance.onError;
  PlatformDispatcher.instance.onError = (error, stack) {
    unawaited(
      FirebaseCrashlytics.instance.recordError(error, stack, fatal: true),
    );
    return previousPlatformError?.call(error, stack) ?? true;
  };
}
```

Import `dart:async` for `unawaited` and `dart:ui` for `PlatformDispatcher` when not already available. Adapt the example when an app uses guarded zones, custom reporters, or deliberate propagation semantics. Ensure one error is not sent twice through overlapping handlers.

Keep collection behavior explicit. Do not disable or conditionally enable production collection merely to make local testing convenient. If consent-based collection is required, treat it as a separate product/privacy decision and verify both consent states.

## Native Wiring

Let current FlutterFire tooling create product wiring, then verify rather than guessing.

### Android

- Confirm application IDs match the registered Firebase apps.
- Confirm Google Services and Crashlytics Gradle plugins are applied where the current build system expects them.
- Check every requested flavor/build type, not only the default debug variant.
- When obfuscating with `--split-debug-info`, follow the current Firebase symbol-upload command using the Firebase App ID, not the package name.

### Apple Platforms

- Confirm bundle IDs and deployment targets match current SDK requirements.
- Inspect dependency-manager state and the generated Crashlytics symbol-upload build phase.
- Verify build-phase input files and script paths against the installed Firebase Apple SDK layout and current documentation.
- Do not copy a CocoaPods, Swift Package Manager, Homebrew, DerivedData, or tool-cache path from another machine.
- Verify dSYM and Flutter symbol behavior for release, obfuscated, and split-debug-info builds.

## Failure Classification

| Symptom | First checks | Classification rule |
| --- | --- | --- |
| CLI cannot authenticate | active account, token state, network | environment or permission until proven code-related |
| App already exists | project, platform, exact identifier | reuse matching app; do not create a suffix variant silently |
| Generated options lack a platform | requested flags, CLI output, app registration | configuration incomplete |
| Android plugin/build failure | generated Gradle diff, versions, repository mirrors | fix configuration; classify transient network only with retry evidence |
| Apple script not found | dependency manager, build phase, resolved SDK path | derive from build evidence; never paste a machine path |
| App launches but no Analytics | collection settings, debug mode, device logs, DebugView | delivery unverified, not successful |
| Crash absent from console | fatal flag, relaunch, debug logs, symbols, app ID | delivery unverified until logs and console agree |

## Privacy And Release Contract

Before release, flag these external tasks even if they cannot be completed from source code:

- update Apple App Privacy disclosures for analytics and diagnostics;
- update Google Play Data safety declarations;
- describe Analytics and crash reporting in the privacy policy;
- review user consent requirements for target regions and audiences;
- verify production symbol upload in local release builds and CI/CD.
