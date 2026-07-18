# FVM troubleshooting

Start with `fvm doctor`, preserve the exact failure output, and keep all retries on FVM. Do not use a global Flutter/Dart command as a diagnostic fallback.

## `fvm flutter` or `fvm dart` is not found

Check in order:

1. Verify `fvm --version` and that the FVM executable directory is on `PATH`.
2. Check for a project or ancestor `.fvmrc`.
3. Run `fvm install` for the pinned project SDK when it is not cached.
4. Check whether `.fvm/flutter_sdk` exists; recreate it with `fvm use <configured-version>` from the project root.

Do not substitute bare `flutter` or `dart` when any step fails.

## Understand unexpected SDK selection

FVM checks the nearest project `.fvmrc`, then ancestor `.fvmrc` files, then `fvm global`, then the system Flutter on `PATH`. Use `fvm doctor` and `fvm api project --compress` to identify the active source. Add or correct a committed `.fvmrc` when team consistency is required.

## Upgrade a channel

FVM preserves normal Flutter behavior. `flutter upgrade` is blocked for immutable release versions. Select or use a channel, then run:

```bash
fvm flutter upgrade
```

Use `fvm use stable --pin` when the desired result is a concrete, shareable release rather than a moving channel.

## FVM Pub installation cannot update

`dart pub global activate fvm` chooses the latest FVM compatible with the Dart SDK that invoked Pub. Upgrade that Dart SDK or install FVM as a standalone executable, then reactivate. For invalid kernel binaries or SDK hash mismatch, deactivate and reactivate FVM with a compatible Dart SDK.

## Pub executable is missing

For a Pub-installed FVM, add the platform's Pub cache `bin` directory to `PATH`. On typical macOS/Linux installations this is `$HOME/.pub-cache/bin`; Windows commonly uses `%USERPROFILE%\AppData\Local\Pub\Cache\bin`.

## Windows command runs twice or Dart/Flutter conflicts

For Pub-installed tools on Windows, order `PATH` so the Pub cache comes first, a standalone Dart SDK comes next if present, and Flutter last. Restart terminals and IDEs after changes.

## Windows says Git is missing although `git --version` works

Git 2.35.2+ may reject an FVM-cached Flutter repository because Windows reports different ownership. Prefer trusting only the affected FVM cache path:

```bash
git config --global --add safe.directory "C:/Users/<user>/AppData/Local/fvm/versions"
git config --global --get-all safe.directory
fvm doctor
fvm flutter doctor
```

The broader `git config --global --add safe.directory "*"` restores pre-check behavior but weakens Git's ownership protection. Use it only when the user accepts that machine-wide tradeoff. Running as Administrator is only a temporary workaround.

## Android Studio uses a stale SDK

After `fvm use <version>`:

1. Confirm `.fvm/flutter_sdk` exists and points to the expected cache entry.
2. Reselect that path in the Flutter SDK setting because the IDE may have stored its resolved target.
3. Sync Gradle files and restart Dart Analysis.
4. Invalidate IDE caches only if the path remains stale.

## Dart MCP analyzes with the wrong SDK

Pass `--flutter-sdk .fvm/flutter_sdk` in project-scoped MCP configuration and start the server from the project root. Use the absolute cache path returned by `fvm list` when symlinks are unavailable.

## Uninstall or reset

Use the installer-specific uninstall command in [configuration.md](configuration.md). Treat `fvm remove --all` and `fvm destroy` as destructive; obtain explicit intent before removing cached SDKs.
