# Contributing

## Branching

`main` is always releasable and only changes through pull requests.

Create a short-lived branch per change, named `<type>/<short-description>`:

```
feat/vendor-master-matching
fix/spend-cube-currency-rounding
docs/architecture-overview
```

## Commits and pull-request titles

Pull requests are **squash-merged**, so the PR title becomes the single
commit on `main`. Titles follow
[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <summary in lower case, imperative mood>
```

| Type       | Use for                                         |
| ---------- | ----------------------------------------------- |
| `feat`     | New user-facing capability                      |
| `fix`      | Bug fix                                         |
| `docs`     | Documentation only                              |
| `test`     | Adding or correcting tests                      |
| `refactor` | Code change that neither fixes nor adds         |
| `perf`     | Performance improvement                         |
| `build`    | Build system or dependencies                    |
| `ci`       | CI configuration                                |
| `chore`    | Repository maintenance                          |

CI checks the title on every pull request.

## Pull requests

- Keep each PR to one logical change; split unrelated work.
- Describe what changed, why, and how it was verified.
- All CI checks must pass before merging.
- Never commit secrets, credentials or client data.
