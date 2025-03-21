# DartIndex

A command-line tool for indexing Dart projects using SCIP (Source Code Intelligence Protocol). This tool combines functionality from [scip-dart](https://github.com/Workiva/scip-dart) and [scip](https://github.com/sourcegraph/scip) into a single, easy-to-use binary.

## Features

- Index Dart projects using SCIP protocol
- Generate code intelligence data
- Create Sourcetrail-compatible databases
- No external dependencies required (everything is bundled)
- Single binary installation
- Support for Flutter Version Management (FVM)
- Automatic SDK detection and configuration
- Type-safe implementation
- Comprehensive error handling

## Prerequisites

For building from source:
- Python 3.7+ (Python 3.12+ recommended)
- protobuf 5.29.1 or higher
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

2. Set up the development environment:
```bash
# This will create a virtual environment and install all dependencies
./setup_dev.sh
```

3. Activate the virtual environment:
```bash
source .venv/bin/activate
```

4. Install the tool system-wide (optional):
```bash
make update
```

This will:
- Build the required native tools (scip-dart and scip)
- Package everything into a single binary
- Install it system-wide in `/usr/local/bin`

### Development Installation

For development work, use the virtual environment:
```bash
# First time setup
./setup_dev.sh

# Subsequent development sessions
source .venv/bin/activate
make install-dev
```

This will:
- Create a Python virtual environment in `.venv`
- Install all development dependencies
- Install the package in editable mode

## Usage

```bash
# Index a Dart project (creates <project_name>.srctrldb)
dartindex index .

# Specify custom output path
dartindex index /path/to/project -o custom.srctrldb
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
│   ├── tools/          # Built native tools (not in version control)
│   │   ├── dart/       # Built scip-dart binary
│   │   └── go/         # Built scip binary
│   ├── __init__.py
│   ├── main.py         # CLI entry point
│   ├── dart_indexer.py # Dart indexing logic
│   └── scip_processor.py # SCIP processing logic
├── setup.py            # Package configuration
├── requirements.txt    # Python dependencies
├── build_tools.py      # Tool build script
├── .venv/              # Virtual environment
└── Makefile           # Build automation
```

### Virtual Environment

The project uses a Python virtual environment to manage dependencies. The virtual environment is created in the `.venv` directory.

To set up the development environment:
```bash
./setup_dev.sh
```

To activate the virtual environment in a new terminal:
```bash
source .venv/bin/activate
```

To deactivate the virtual environment:
```bash
deactivate
```

### Installing Dependencies

All project dependencies are listed in `requirements.txt`. After activating the virtual environment, you can install them with:
```bash
pip install -r requirements.txt
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

### Code Organization

The codebase is organized into several key components:

- `cli/main.py`: Command-line interface using Click
- `cli/dart_indexer.py`: Core indexing functionality
- `cli/scip_processor.py`: SCIP data processing and formatting
- `build_tools.py`: Native tool build automation

Key features of the implementation:
- Type hints throughout the codebase
- Comprehensive error handling
- Clear separation of concerns
- Modular and testable design

## Troubleshooting

### Common Issues

1. **ImportError: cannot import name 'runtime_version' from 'google.protobuf'**
   - This error occurs when using an incompatible protobuf version
   - Solution: Upgrade protobuf to version 5.29.1 or higher:
     ```bash
     pip install --upgrade "protobuf>=5.29.1"
     ```

2. **Permission warnings during installation**
   - If you see pip cache permission warnings during installation
   - Solution: Use `sudo -H` when running make commands:
     ```bash
     sudo -H make update
     ```

## License

MIT License - See LICENSE file for details 