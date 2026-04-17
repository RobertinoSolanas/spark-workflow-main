# Contributing Guide

Thank you for contributing to this project!

## Workflow

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a Pull Request

## Branch Naming

Use descriptive branch names:

feature/<name>  
fix/<name>  
docs/<name>

Examples:

feature/add-authentication  
fix/login-error  
docs/update-readme

## Commit Style

Use a clear commit message format:

type(scope): message

Examples:

feat(api): add authentication  
fix(auth): resolve token bug  
docs(readme): update documentation

Common commit types:

- feat – new feature
- fix – bug fix
- docs – documentation changes
- refactor – code improvements without behavior change
- test – adding or updating tests
- chore – maintenance or tooling

## Pull Requests

Before opening a Pull Request:

- Ensure the code builds successfully
- Ensure tests pass
- Update documentation if necessary

Pull Requests should:

- Be focused and small
- Contain clear commit messages
- Include a description of the change
- Reference related issues when applicable

Example PR description:

## Summary
Short explanation of the change.

## Changes
- Added feature X
- Fixed issue Y

## Related Issues
Closes #123

## Testing
Describe how the changes were tested.

## Code Style

Please follow the existing coding style of the project.

General guidelines:

- Write readable and maintainable code
- Prefer small and focused functions
- Use meaningful variable names
- Add comments for complex logic

If the repository includes a linter or formatter, run it before submitting changes.

## Testing

All new functionality should include tests when possible.

Before submitting a PR:

- Run all tests
- Ensure no existing tests break

Example:

make test

## Documentation

Please update documentation when:

- Adding new features
- Changing behavior
- Adding configuration options
- Improving developer experience

Clear documentation helps contributors and users understand the project.

## Questions

If you have questions about contributing:

- Open an issue
- Start a discussion

Contributions of all sizes are welcome.