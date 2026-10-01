# Documentation

This folder holds the project documentation. Start with the row that matches
what you want to do.

## I want to install or operate the suite

| Document | Content |
| --- | --- |
| [deployment.md](deployment.md) | Prerequisites, install, upgrade, rollback, configuration |
| [label-printing.md](label-printing.md) | Print agent setup, printer targets, troubleshooting |
| [compatibility.md](compatibility.md) | Where behaviour differs from stock Odoo 19 Community |
| [README_安装与验收.md](README_安装与验收.md) | 安装、使用入口、扫码规则速查、验收清单（中文，面向仓库团队） |

## I want to change the code

| Document | Content |
| --- | --- |
| [development.md](development.md) | Dev environment, test commands, conventions, testing pitfalls |
| [architecture.md](architecture.md) | Data model, scan engine, concurrency, offline queue, roles |
| [scanner-api.md](scanner-api.md) | The `bc_*` RPC methods and the state object |
| [PROJECT_HISTORY.md](PROJECT_HISTORY.md) | 设计决策、踩过的坑、验证结论（中文） |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | How to submit a change |
| [../CLAUDE.md](../CLAUDE.md) | Short guide for AI coding assistants working in this repository |

## Conventions for these documents

*   Documents are Markdown and follow the
    [Google Markdown style guide](https://google.github.io/styleguide/docguide/style.html).
*   A document describes the current behaviour of the `main` branch. History
    belongs in [../CHANGELOG.md](../CHANGELOG.md) and
    [PROJECT_HISTORY.md](PROJECT_HISTORY.md).
*   When code and documentation disagree, the code is right and the document
    has a bug. Fix it in the same pull request as the code change.
*   English is the primary language. The two Chinese documents are kept for the
    warehouse team and for the original design record.
