---
name: flutter-use-fvm
description: Enforce project-scoped Flutter and Dart command execution through FVM. Use whenever a task runs, suggests, documents, or embeds Flutter/Dart CLI commands in a repository that contains `.fvmrc` or `.fvm/`, whose instructions require FVM, or when the user mentions FVM, `fvm flutter`, `fvm dart`, Flutter SDK version pinning, flavors, monorepos, IDE/CI integration, custom SDK forks, or FVM troubleshooting. Also use alongside other Flutter skills so their bare `flutter` and `dart` examples are adapted to FVM. Never silently fall back to a global Flutter or Dart SDK.
---

# Use Flutter through FVM

Keep every project command on the SDK selected by FVM. Treat the explicit command form as a reproducibility contract, not as an optional convenience.

## Apply the command contract

1. Read repository instructions such as `AGENTS.md` before running tooling.
2. Look for `.fvmrc` and `.fvm/` in the project or an ancestor directory.
3. When this skill is active, use FVM unless repository instructions explicitly require another wrapper.
4. Run or present commands with these forms:

| Intent | Required form |
| --- | --- |
| Flutter CLI | `fvm flutter <subcommand> [args]` |
| Dart CLI | `fvm dart <subcommand> [args]` |
| Third-party command needing the pinned SDK on `PATH` | `fvm exec <command> [args]` |
| Flutter command on a specific SDK | `fvm spawn <version> <flutter-command> [args]` |
| Flutter command for an FVM flavor | `fvm flavor <flavor> <flutter-command> [args]` |

Translate bare commands before execution or before placing them in documentation, scripts, CI, task plans, or user-facing instructions:

```text
flutter pub get                       -> fvm flutter pub get
flutter analyze                       -> fvm flutter analyze
flutter test                          -> fvm flutter test
flutter build apk                     -> fvm flutter build apk
dart analyze                          -> fvm dart analyze
dart format .                         -> fvm dart format .
dart run build_runner build           -> fvm dart run build_runner build
melos bootstrap                       -> fvm exec melos bootstrap
```

Choose `fvm flutter pub get` for a Flutter application and `fvm dart pub get` for a pure Dart package. Preserve an existing repository wrapper such as `make test` after inspecting it; update bare commands inside the wrapper only when the task includes that file.

## Refuse silent fallback

- If `fvm` is unavailable, report that exact blocker and installation guidance. Do not retry with bare `flutter` or `dart`.
- If the configured SDK is missing, run `fvm install` or the non-mutating diagnostic requested by the user. Do not switch to the global SDK.
- If `.fvmrc` is absent, do not invent or pin a version during an unrelated task. Continue to use explicit FVM proxy commands when requested, and explain that FVM may resolve through an ancestor, global FVM setting, or system SDK until the project is pinned.
- Do not create aliases, PATH shims, global SDK links, or shell-profile changes unless the user asks for machine-level setup.

## Configure a project deliberately

When the user asks to set up or change FVM:

1. Reuse the requested version, channel, flavor, commit, or fork. Do not assume `stable` when the choice affects the project.
2. Run `fvm use <version>` from the intended project or monorepo root.
3. Commit `.fvmrc` for team consistency.
4. Let FVM manage the generated `.fvm/` directory and its SDK symlinks. For FVM 3+, keep `.fvm/` ignored unless repository policy says otherwise.
5. Verify with `fvm flutter --version`, `fvm doctor`, or the task-relevant command.

Do not edit generated FVM files by hand when `fvm use` or `fvm config` is the supported operation. Avoid destructive commands such as `fvm destroy`, `fvm remove --all`, or global configuration changes without explicit user intent.

## Load detailed references only as needed

- Read [references/commands.md](references/commands.md) for the complete documented CLI surface, options, version formats, proxy resolution, and JSON API.
- Read [references/configuration.md](references/configuration.md) for installation, `.fvmrc`, environment variables, cache/global settings, and generated files.
- Read [references/workflows.md](references/workflows.md) for flavors, monorepos, CI, VS Code, Android Studio/IntelliJ, Dart MCP, offline use, and custom Flutter forks.
- Read [references/troubleshooting.md](references/troubleshooting.md) when FVM, Flutter, Dart, PATH, symlink, upgrade, or Windows Git behavior fails.
- Read [references/sources.md](references/sources.md) when refreshing this skill against upstream documentation or checking provenance and coverage.

When official docs and the installed FVM version disagree, inspect `fvm <command> --help` through the installed binary and prefer its actual CLI behavior. Keep project commands on FVM throughout the investigation.
