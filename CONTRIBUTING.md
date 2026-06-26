# Contributing to juryrig

First off, thank you for considering contributing to `juryrig`! It's people like you that make it a great tool for auditing LLM judges.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs

If you find a bug, please create a new issue using our Bug Report template. Please include:
* Your Python version
* A minimal reproducible example
* The expected vs actual behavior

### Suggesting Enhancements

We welcome new feature suggestions! Please open an issue using the Feature Request template to discuss the change before implementing it.

### Pull Requests

To submit a contribution:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Install development dependencies
4. Make your changes and ensure tests pass
5. Commit your changes with descriptive messages
6. Push to your branch and open a Pull Request!

## Development Setup

`juryrig` is built with zero runtime dependencies. To run tests:

```bash
python -m unittest discover -s tests -v
```

Ensure all tests pass before making a pull request.
