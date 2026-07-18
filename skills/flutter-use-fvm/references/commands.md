# FVM command reference

Use this reference when selecting an FVM command or option. Examples use explicit FVM routing even when an IDE can make bare commands resolve to the same SDK.

## Version selectors

- Release: `3.19.0`
- Channel: `stable`, `beta`, `dev`, or `master` where supported
- Git commit: `fa345b1`
- Fork alias plus version: `mycompany/stable`
- Same release forced to a channel: `3.16.0@beta`

When the same release appears on multiple channels, FVM prefers `stable`, then `beta`, then `dev`. Add `@channel` to override that priority.

## Project and SDK lifecycle

### `fvm use [version] [options]`

Select the SDK for the current project. If the SDK is not cached, FVM installs it, writes project configuration, updates the project SDK link and supported IDE settings, and normally runs dependency resolution.

- `-f`, `--force`: bypass Flutter-project validation
- `-p`, `--pin`: resolve a channel to its current concrete release; do not use for `master`
- `--flavor <name>` or `--env <name>`: assign a version to a named flavor
- `-s`, `--skip-setup`: skip SDK setup
- `--skip-pub-get`: skip dependency resolution

Examples:

```bash
fvm use 3.19.0
fvm use stable --pin
fvm use 3.19.0 --flavor production
fvm use fa345b1
```

### `fvm install [version] [options]`

Cache an SDK. With no version, install the version resolved from project configuration.

- `-s`, `--setup`: prepare SDK dependencies; enabled by default
- `--no-setup`: cache faster without SDK setup
- `--skip-pub-get`: skip dependency resolution
- Alias: `fvm i`

```bash
fvm install 3.19.0
fvm install 3.19.0 --no-setup
fvm install
```

### `fvm list`

List cached SDKs and their paths. Alias: `fvm ls`.

### `fvm releases [options]`

List installable Flutter releases. Use `-c` or `--channel <stable|beta|dev|all>` to filter; the documented default is `stable`.

### `fvm remove [version] [options]`

Remove a cached SDK. Omit the version for an interactive selection. `-a` or `--all` removes every cached version and is destructive.

### `fvm destroy [options]`

Delete the entire FVM cache and all installed SDKs. `-f` or `--force` skips confirmation. Treat this as irreversible and require explicit intent.

## Execute commands with an SDK

### `fvm flutter <command> [args]`

Run the Flutter CLI through the resolved project SDK:

```bash
fvm flutter doctor
fvm flutter pub get
fvm flutter analyze
fvm flutter test
fvm flutter run
fvm flutter build apk
```

FVM prevents `flutter upgrade` for immutable release versions. Select a channel if the goal is to upgrade a channel checkout.

### `fvm dart <command> [args]`

Run the Dart CLI bundled with the resolved Flutter SDK:

```bash
fvm dart pub get
fvm dart analyze
fvm dart format .
fvm dart run build_runner build
```

### `fvm exec <command> [args]`

Run an arbitrary process with the project SDK environment:

```bash
fvm exec melos bootstrap
fvm exec ./scripts/build.sh
```

### `fvm spawn <version> <flutter-command> [args]`

Run one Flutter command on a specific SDK without changing the project pin:

```bash
fvm spawn 3.19.0 build apk
fvm spawn 3.16.0 test
```

### `fvm flavor <flavor> <flutter-command> [args]`

Run one Flutter command with the SDK assigned to a project flavor:

```bash
fvm flavor development build apk
fvm flavor staging test
```

## Global settings and diagnostics

### `fvm global [version]`

Link a default FVM SDK for the machine. Use `-f` or `--force` to bypass validation and `-u` or `--unlink` to remove the link. A global link is not a substitute for a committed project `.fvmrc`.

### `fvm config [options]`

With no options, show current global configuration.

- `--cache-path <path>`: set the SDK cache directory
- `--flutter-url <url>`: set the Flutter Git repository
- `--use-git-cache` / `--no-use-git-cache`: enable or disable Git reference caching
- `--git-cache-path <path>`: set the Git cache directory
- `--update-check` / `--no-update-check`: enable or disable FVM update notifications

### `fvm doctor`

Report project configuration, IDE integration, paths, environment, and FVM version. Prefer it as the first FVM-specific diagnostic.

## Custom repository aliases

```bash
fvm fork add <alias> <repository-url.git>
fvm fork list
fvm fork remove <alias>
```

Then install or use `<alias>/<version>`, for example `fvm use mycompany/stable`. The documented fork URL must end in `.git`.

## SDK resolution order

For `flutter`, `dart`, and `exec`, FVM resolves the SDK in this order:

1. The nearest project `.fvmrc`
2. An ancestor directory `.fvmrc`
3. The FVM global version
4. Flutter found on the system `PATH`

Explicit `fvm flutter` and `fvm dart` keep routing visible, but a project should still commit `.fvmrc` to prevent the final fallbacks from varying across machines.

## JSON API

Add `-c` or `--compress` for compact JSON.

```bash
fvm api list [--skip-size-calculation]
fvm api releases [--limit <n>] [--filter-channel <channel>]
fvm api context
fvm api project [--path <project-directory>]
```

- `list`: return installed SDK names, paths, Flutter/Dart versions, size, and setup status
- `releases`: return release metadata and channels
- `context`: return FVM paths, cache settings, project directory, update/CI state, and version
- `project`: return resolved project config, pinned version, flavor data, paths, and parsed `pubspec.yaml`

Example extraction:

```bash
fvm api project --compress | jq -r '.project.pinnedVersion'
fvm api list --compress | jq -r '.versions[].name'
```
