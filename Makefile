PYTHON := $(shell which python3)

.PHONY: clean build install install-dev update update-dev test tools

clean:
	rm -rf -f build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/ .coverage cli/tools/

build: clean
	$(PYTHON) -m build

# Build the native tools (scip-dart and scip)
tools: clean
	mkdir -p cli/tools/dart cli/tools/go
	$(PYTHON) build_tools.py || exit 1

# Build the Python package and create executable
dist: install-dev
	$(PYTHON) -m pip install --upgrade pip build pyinstaller
	$(PYTHON) -m build
	$(PYTHON) -m PyInstaller dartindex.spec

# Development installation (editable mode)
install-dev:
	$(PYTHON) -m pip install -e .

# Production installation (system-wide)
install: dist
	# Create the target directory if it doesn't exist
	[ -d /usr/local/bin ] || sudo mkdir -p /usr/local/bin
	# Copy and set permissions
	sudo cp dist/dartindex /usr/local/bin/
	sudo chmod 755 /usr/local/bin/dartindex
	sudo chown root:wheel /usr/local/bin/dartindex

# Update development installation
update-dev:
	$(PYTHON) -m pip uninstall dartindex -y || true
	$(PYTHON) -m pip install -e .

# Update production installation (build tools once, then package and install)
update:
	$(MAKE) clean
	$(MAKE) tools
	$(MAKE) install

test:
	$(PYTHON) -m pytest tests/