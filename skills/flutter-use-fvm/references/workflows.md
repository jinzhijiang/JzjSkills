# FVM workflows and integrations

Use this reference for project setup patterns beyond a single proxy command.

## New or existing project

```bash
cd <project-root>
fvm use <version>
fvm flutter --version
fvm flutter pub get
```

For a channel whose exact release must remain stable across the team, use `fvm use stable --pin`. Do not repin a project merely to run an unrelated command.

## Test without changing the project pin

```bash
fvm flutter test
fvm spawn 3.19.0 test
fvm spawn 3.16.0 test
```

Use `spawn` for one-off compatibility checks. Use `fvm use` only when the project configuration should change.

## Project flavors

Assign SDKs:

```bash
fvm use stable --flavor development
fvm use 3.19.0 --flavor staging
fvm use 3.16.0 --flavor production
```

Activate a configured flavor as the project version with `fvm use <flavor-name>`, or run a Flutter command without switching:

```bash
fvm flavor development build apk
fvm flavor production test
```

FVM flavors choose an SDK version; they do not replace Flutter application `--flavor` build semantics. Pass Flutter's own flavor arguments after the Flutter command when both concepts are needed.

## Monorepos and Melos

Place `.fvmrc` at a common ancestor when all packages share one SDK. A nearer nested `.fvmrc` overrides the ancestor.

Since documented FVM 3.3 behavior, `fvm use` can detect `melos.yaml` up to the Git root and manage `sdkPath: .fvm/flutter_sdk`, including relative paths for nested projects. Control this with `updateMelosSettings` in `.fvmrc`.

For manual Melos setup:

```yaml
name: my_workspace
packages:
  - packages/**
sdkPath: .fvm/flutter_sdk
```

Run Melos through the selected SDK environment:

```bash
fvm exec melos bootstrap
```

## CI/CD

A minimal flow is:

```bash
dart pub global activate fvm
fvm install
fvm flutter pub get
fvm flutter analyze
fvm flutter test
fvm flutter build apk --release
```

Prefer the platform's standalone FVM install method when practical. Cache the FVM SDK directory between runs, commit `.fvmrc`, and run `fvm install` before build steps. Environment variables such as `FVM_CACHE_PATH` can isolate or share the CI cache.

## Offline or shared cache

```bash
fvm config --cache-path /shared/flutter-cache
fvm config --no-use-git-cache
fvm install 3.19.0
```

Confirm the required SDK already exists in the selected cache before treating an offline install as reliable.

## VS Code

FVM detects VS Code from a project `.vscode/` directory or `TERM_PROGRAM=vscode` and can update `.vscode/settings.json` when `updateVscodeSettings` is enabled. Let `fvm use` write the SDK path because generated paths can be selector-specific.

The FVM docs show generated paths such as:

```json
{
  "dart.flutterSdkPath": ".fvm/versions/stable"
}
```

The Dart Code extension can then make bare terminal commands resolve to that SDK. Still emit explicit `fvm flutter` and `fvm dart` commands in agent work, documentation, and CI so behavior does not depend on an IDE terminal.

## Android Studio and IntelliJ

Point the Flutter SDK setting at the project `.fvm/flutter_sdk` path. Some IDE/plugin versions resolve the symlink to its absolute cache target; after `fvm use` switches versions, reselect the project SDK path and refresh:

- Sync Gradle files for Android projects.
- Restart Dart Analysis if diagnostics are stale.
- Invalidate IDE caches only when the lighter refresh does not work.
- Run `fvm doctor` and verify `ls -l .fvm/flutter_sdk`.

In a multi-module repository, give each independently pinned module its own `.fvmrc` and `.fvm/flutter_sdk`.

## Dart MCP server

Make AI tooling use the same SDK as FVM:

```json
{
  "mcpServers": {
    "dart": {
      "command": "dart",
      "args": ["mcp-server", "--flutter-sdk", ".fvm/flutter_sdk"]
    }
  }
}
```

Start the MCP server from the project root so the relative link resolves. For user-level/shared configuration, use an absolute SDK path. If Windows cannot create symlinks because privileged access is disabled, locate the cached SDK with `fvm list` and pass its absolute path.

## Custom Flutter SDK forks

Prefer fork aliases:

```bash
fvm fork add mycompany https://github.com/mycompany/flutter.git
fvm install mycompany/stable
fvm use mycompany/3.19.0
```

Alternatives:

- Set a global repository with `fvm config --flutter-url <url>`.
- Set `FVM_FLUTTER_URL` for a machine or CI process.
- Set project `flutterUrl` in `.fvmrc` when one repository intentionally uses a different Flutter source.
- For a manually cloned SDK, clone the full repository into the FVM versions cache using a `custom_<name>` directory and select it with `fvm use custom_<name>`. Do not use shallow or single-branch clones because Flutter tooling needs Git history and refs for version detection.

Existing cached SDKs do not automatically change origin after `flutterUrl` changes; reinstall the affected versions. Avoid reusing the same selector for incompatible repositories because cache collisions can result.

## Optional convenience aliases and shims

The official docs describe shell aliases such as `alias f="fvm flutter"` and OS-level shims that reroute bare `flutter`/`dart`. Do not create them automatically: they mutate the user's machine, can conflict with package-manager binaries, and make scripts less explicit. Configure them only on request and keep repository commands in full FVM form.
