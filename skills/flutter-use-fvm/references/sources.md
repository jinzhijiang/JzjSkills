# Upstream documentation coverage

This skill paraphrases the public FVM documentation rather than copying it verbatim.

- Official documentation: <https://fvm.app/documentation/getting-started/overview>
- Official source repository: <https://github.com/leoafarias/fvm>
- Documentation snapshot commit: `45815007fb89928647686c9615a17ed66fe00d3e`
- Snapshot date: 2026-07-18

## Covered documentation

### Getting started

- Overview
- Installation
- Configuration
- FAQ

### Guides

- Quick Reference
- Common Workflows
- Commands Reference
- Running Flutter
- Project Flavors
- Monorepo Support
- Global Configuration
- VS Code Configuration
- Dart MCP Server

### Advanced and troubleshooting

- JSON API
- Custom Flutter SDK/Forks
- Release Multiple Channels
- Troubleshooting Overview
- Git Safe Directory on Windows

The upstream `Manual Branch Smoke Test` page targets contributors changing FVM itself, not agents operating on Flutter application repositories, so it is intentionally not reproduced as an app-development workflow.

## Refresh procedure

1. Review the current navigation and source files under `docs/pages/documentation/` in the official repository.
2. Compare command options with the current installed CLI using `fvm <command> --help`.
3. Update the smallest relevant reference file; keep the command contract in `SKILL.md` stable.
4. Update the snapshot commit/date in this file.
5. Run the skill validator and forward-test command rewriting plus missing-FVM behavior.
