# DartIndex

A command-line tool for indexing Dart projects using SCIP (Source Code Intelligence Protocol). This tool combines functionality from [scip-dart](https://github.com/Workiva/scip-dart) and [scip](https://github.com/sourcegraph/scip) into a single, easy-to-use binary.

## Features

- Index Dart projects using SCIP protocol
- Generate code intelligence data
- No external dependencies required (everything is bundled)
- Single binary installation
- Support for Flutter Version Management (FVM)
- Automatic SDK detection and configuration

## Prerequisites

For building from source:
- Python 3.7+
- Dart SDK
- Go 1.16+
- Make

For using the tool:
- Dart SDK (system-wide or via FVM)

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/yourusername/dartindex.git
cd dartindex
```

2. Install the tool system-wide:
```bash
sudo make update
```

This will:
- Build the required native tools (scip-dart and scip)
- Package everything into a single binary
- Install it system-wide in `/usr/local/bin`

### Development Installation

For development work:
```bash
make install-dev
```

## Usage

```bash
# Index a Dart project and output JSON
dartindex index /path/to/dart/project

# Get a summary view
dartindex index /path/to/dart/project --format summary

# Get only symbol information
dartindex index /path/to/dart/project --symbols-only
```

### FVM Support

The tool automatically detects and uses FVM when available:

- If a project uses FVM, it will use the project's configured Flutter/Dart version
- FVM configuration is detected from:
  - `.fvm/fvm_config.json`
  - `.fvm/version`
- The tool will automatically use the correct SDK version for indexing

Example with FVM:
```bash
# In a project with FVM
dartindex index .  # Automatically uses project's FVM version
```

## Build Process

The build process consists of several steps:

1. `make tools`: Builds the native tools
   - Downloads and builds scip-dart
   - Downloads and builds scip
   - Places binaries in `cli/tools/`

2. `make dist`: Creates the Python package and executable
   - Installs the package in development mode
   - Creates a PyInstaller executable

3. `make install`: Installs the executable
   - Copies the binary to `/usr/local/bin`
   - Sets proper permissions

4. `make update`: Complete build and installation
   - Runs clean, tools, and install in sequence
   - Recommended for production installation

## Development

### Directory Structure
```
dartindex/
├── cli/
│   ├── tools/
│   │   ├── dart/       # Built scip-dart binary
│   │   └── go/         # Built scip binary
│   ├── __init__.py
│   ├── main.py         # CLI entry point
│   ├── dart_indexer.py # Dart indexing logic
│   └── scip_processor.py # SCIP processing logic
├── setup.py
├── requirements.txt
└── Makefile
```

### Make Commands

- `make clean`: Remove all build artifacts
- `make tools`: Build native tools only
- `make install-dev`: Install in development mode
- `make update-dev`: Update development installation
- `make update`: Full production build and install
- `make test`: Run tests

### Environment Support

The tool is designed to work with various Dart/Flutter development environments:

- System-wide Dart SDK installation
- FVM-managed Flutter/Dart versions
- Project-specific FVM configurations
- Multiple Flutter versions on the same system

## License

MIT License - See LICENSE file for details 