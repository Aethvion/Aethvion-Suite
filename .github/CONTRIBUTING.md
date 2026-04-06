# Contributing to Aethvion Suite

First off, thank you for considering contributing to Aethvion Suite! It's people like you that make this self-evolving AI suite better for everyone.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [issue list](https://github.com/Aethvion/Aethvion-Suite/issues) as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

* **Use a clear and descriptive title** for the issue
* **Describe the exact steps to reproduce the problem**
* **Provide specific examples** to demonstrate the steps
* **Describe the behavior you observed** and what behavior you expected to see
* **Include screenshots or logs** if relevant
* **Note your environment**: OS, Python version, etc.

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

* **Use a clear and descriptive title**
* **Provide a detailed description** of the suggested enhancement
* **Explain why this enhancement would be useful** to most users
* **List any similar features** in other projects if applicable

### Pull Requests

* Fill in the pull request template
* Follow the Python coding style (PEP 8)
* Include comments in your code where necessary
* Update documentation to reflect your changes
* Write clear commit messages
* Ensure all tests pass

## Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Aethvion-Suite.git
   cd Aethvion-Suite
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -e ".[memory]"
   ```

5. Create a branch for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Code Style

* Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) Python style guide
* Use meaningful variable and function names
* Add docstrings to functions and classes
* Keep functions focused and concise
* Write comments for complex logic

### Naming Conventions

Aethvion Suite follows the **Aethvion Naming Standard** for tools and agents:

**Format:** `[Domain]_[Action]_[Object]`

**Examples:**
* `Security_Scan_Prompt`
* `Memory_Store_Episodic`
* `Finance_Fetch_StockPrice`
* `Analytics_Generate_Report`

Please follow this convention when creating new tools or agents.

## Testing

Before submitting a pull request:

1. Test your changes locally:
   ```bash
   python -m core.main --test
   ```

2. Test in CLI mode:
   ```bash
   python -m core.main --cli
   ```

3. Test in web mode:
   ```bash
   python -m core.main
   # Visit http://localhost:8080
   ```

## Documentation

* Update relevant documentation in `/documentation/` if you change functionality
* Update the README.md if you add new features
* Keep documentation clear and concise
* Include code examples where helpful

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Pull Request Process

1. Ensure your code follows the style guidelines
2. Update documentation as needed
3. Add tests if applicable
4. Ensure all tests pass
5. Update CHANGELOG.md with your changes (if applicable)
6. Submit your pull request with a clear description

### PR Title Format

Use clear, descriptive titles:
* `feat: Add new tool generation validator`
* `fix: Resolve memory leak in agent factory`
* `docs: Update installation instructions`
* `refactor: Improve provider failover logic`

## Review Process

* Maintainers will review your PR as soon as possible
* You may be asked to make changes
* Once approved, a maintainer will merge your PR

## Development Tips

### Working with The Forge (Tool Generation)

When contributing to the Forge system:
* Ensure generated tools follow Aethvion naming
* Add security validation for tool code
* Test tool generation with various prompts

### Working with The Factory (Agent Spawning)

When contributing to the Factory:
* Ensure agents are stateless
* Implement proper lifecycle management
* Test agent spawning and termination

### Working with Nexus Core (Orchestration)

When contributing to Nexus Core:
* Maintain single point of entry pattern
* Preserve trace_id throughout execution
* Test provider failover logic

## Getting Help

* [Start a discussion](https://github.com/Aethvion/Aethvion-Suite/discussions)
* [Open an issue](https://github.com/Aethvion/Aethvion-Suite/issues)
* Read the [documentation](/documentation/)

## License

By contributing to Aethvion Suite, you agree to the [Contributor License Agreement (CLA)](../LICENSE) defined in the main LICENSE file.

---

**Thank you for contributing to Aethvion Suite!**

Every contribution, no matter how small, helps make this system better for everyone.
