# esp-pylib

Python library for logging, utils and constants for Espressif Systems' Python projects.

## Installation

```bash
pip install esp-pylib
```

## How to Contribute

First, set up the development environment:

```bash
git clone https://github.com/espressif/esp-pylib.git
cd esp-pylib
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```
## How to Release (For Maintainers Only)

```bash
python -m venv venv
source venv/bin/activate
pip install commitizen czespressif
git fetch
git checkout -b update/release_v1.1.0
git reset --hard origin/master
cz bump
git push -u
git push --tags
```

Create a pull request and edit the automatically created draft [release notes](https://github.com/espressif/esp-pylib/releases).

## License

This document and the attached source code are released under Apache License Version 2. See the accompanying [LICENSE](./LICENSE) file for a copy.
