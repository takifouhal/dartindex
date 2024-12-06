# DartIndex

A command-line tool for indexing and analyzing Dart/Flutter codebases.

## Development Setup

### Prerequisites
- Python 3.x
- Git

### Quick Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd dartindex
   ```

2. Run the setup script:
   ```bash
   ./setup_dev.sh
   ```

   This script will:
   - Create a Python virtual environment (.venv)
   - Install all required dependencies
   - Set up the package in development mode

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

### Manual Setup
If you prefer to set up manually:

1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```

2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install the package in development mode:
   ```bash
   pip install -e .
   ```

## Usage

After installation, you can use the `dartindex` command directly:

```bash
dartindex <command> [options]
```

## Building from Source

To build the executable:

```bash
make build
```

To update your system-wide installation:

```bash
make update
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 