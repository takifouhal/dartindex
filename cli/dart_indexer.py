"""
Internal implementation of SCIP-Dart indexing functionality.
This module contains the core logic for indexing Dart projects without external dependencies.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List

class DartIndexer:
    # SDK files that need to be copied from lib/_internal
    INTERNAL_SDK_FILES = [
        ("sdk_library_metadata/lib/libraries.dart", "sdk_library_metadata/lib/libraries.dart"),
        ("libraries.dart", "libraries.dart"),
        ("allowed_experiments.json", "allowed_experiments.json"),
        ("sdk_library_metadata", "sdk_library_metadata"),
        ("sdk", "sdk"),
        ("release", "release"),
        ("specification", "specification"),
    ]
    
    # SDK metadata files to copy from root
    SDK_METADATA_FILES = ["version", "revision", "release"]

    def __init__(self):
        """Initialize the DartIndexer."""
        # Get the directory where the executable is located
        base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

        # Tools are directly in the tools directory at the root
        self.tools_dir = os.path.join(base_path, "tools")
        self.scip_dart_exe = os.path.join(self.tools_dir, "dart", "scip_dart")
        self.scip_exe = os.path.join(self.tools_dir, "go", "scip")
        
        # Make executables executable on non-Windows systems
        if sys.platform != "win32":
            os.chmod(self.scip_dart_exe, 0o755)
            os.chmod(self.scip_exe, 0o755)

    def _read_file_content(self, file_path: str) -> Optional[str]:
        """Safely read file content."""
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except:
            return None

    def _get_fvm_version(self, project_path: str) -> Optional[str]:
        """
        Get the Flutter version from FVM configuration.
        
        Args:
            project_path: Path to the project root
            
        Returns:
            str: Flutter version or None if not found
        """
        # Check .fvm/fvm_config.json
        fvm_config = os.path.join(project_path, ".fvm/fvm_config.json")
        if os.path.exists(fvm_config):
            content = self._read_file_content(fvm_config)
            if content:
                try:
                    version = json.loads(content).get('flutterSdkVersion')
                    if version:
                        return version
                except:
                    pass
        
        # Check .fvm/version file
        version_file = os.path.join(project_path, ".fvm/version")
        if os.path.exists(version_file):
            version = self._read_file_content(version_file)
            if version:
                return version
        
        return None

    def _setup_sdk_files(self, sdk_path: str, tools_dir: str) -> None:
        """
        Set up SDK files by copying them to the tools directory.
        
        Args:
            sdk_path: Path to the Dart SDK
            tools_dir: Path to the tools directory
        """
        try:
            # Create the target directories
            tools_lib = os.path.join(tools_dir, "lib")
            internal_dir = os.path.join(tools_lib, "_internal")
            os.makedirs(internal_dir, exist_ok=True)
            
            # Copy SDK internal files
            sdk_internal = os.path.join(sdk_path, "lib", "_internal")
            for src_rel, dst_rel in self.INTERNAL_SDK_FILES:
                src = os.path.join(sdk_internal, src_rel)
                dst = os.path.join(internal_dir, dst_rel)
                
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst, symlinks=True)
                    else:
                        shutil.copy2(src, dst)
            
            # Copy SDK metadata files
            for item in self.SDK_METADATA_FILES:
                src = os.path.join(sdk_path, item)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(tools_dir, item))
            
        except Exception as e:
            print(f"Warning: Failed to set up SDK files: {str(e)}")

    def _get_fvm_sdk_path(self, project_path: str, fvm_version: str) -> Optional[Tuple[List[str], str]]:
        """Get SDK path for FVM installation."""
        try:
            # Try getting SDK path from FVM command
            result = subprocess.run(
                ["fvm", "flutter", "which", "flutter"],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True
            )
            flutter_path = result.stdout.strip()
            if flutter_path:
                sdk_path = os.path.abspath(os.path.join(
                    os.path.dirname(os.path.dirname(flutter_path)),
                    "bin/cache/dart-sdk"
                ))
                if os.path.exists(sdk_path):
                    return ["fvm", "dart"], sdk_path
        except:
            pass
        
        # Try common FVM paths
        paths = [
            os.path.expanduser(f"~/.fvm/versions/{fvm_version}/bin/cache/dart-sdk"),
            os.path.join(project_path, ".fvm/flutter_sdk/bin/cache/dart-sdk"),
            os.path.abspath(os.path.join(project_path, f".fvm/versions/{fvm_version}/bin/cache/dart-sdk"))
        ]
        
        for path in paths:
            if os.path.exists(path):
                return ["fvm", "dart"], path
        
        return None

    def _get_system_sdk_path(self) -> Optional[Tuple[List[str], str]]:
        """Get SDK path for system Dart installation."""
        try:
            dart_path = subprocess.run(
                ["which", "dart"],
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()
            
            if dart_path:
                sdk_path = os.path.dirname(os.path.dirname(dart_path))
                if os.path.exists(os.path.join(sdk_path, "lib")):
                    return ["dart"], sdk_path
        except:
            pass
        
        return None

    def _get_dart_info(self, project_path: str) -> Tuple[List[str], Optional[str]]:
        """
        Get Dart command and SDK path based on whether FVM is being used.
        
        Args:
            project_path: Path to the project root
            
        Returns:
            tuple: (dart_command, sdk_path) where dart_command is a list of command parts
                  and sdk_path is the path to the Dart SDK
        """
        # Check for FVM
        fvm_version = self._get_fvm_version(project_path)
        if fvm_version:
            print(f"FVM detected, using Flutter version: {fvm_version}")
            
            # Set FVM to use the correct version
            try:
                subprocess.run(
                    ["fvm", "use", fvm_version],
                    cwd=project_path,
                    check=True,
                    capture_output=True
                )
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to set FVM version: {e.stderr.decode() if e.stderr else str(e)}")
            
            # Try to get FVM SDK path
            result = self._get_fvm_sdk_path(project_path, fvm_version)
            if result:
                return result
        
        # Try system SDK
        result = self._get_system_sdk_path()
        if result:
            return result
            
        return ["dart"], None

    def index_project(self, project_path: str) -> bytes:
        """
        Index a Dart project and return the SCIP index data.
        
        Args:
            project_path: Path to the Dart project root
            
        Returns:
            bytes: The raw SCIP index data
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Ensure we're in the project directory
            original_dir = os.getcwd()
            project_path = os.path.abspath(project_path)
            os.chdir(project_path)
            
            try:
                # Get the appropriate dart command and SDK path
                dart_cmd, sdk_path = self._get_dart_info(project_path)
                
                # Run pub get in the target project
                subprocess.run(
                    dart_cmd + ["pub", "get"],
                    check=True,
                    cwd=project_path
                )
                
                # Set up environment for SCIP-Dart
                env = os.environ.copy()
                if sdk_path and os.path.exists(sdk_path):
                    print(f"Using Dart SDK from: {sdk_path}")
                    env.update({
                        "DART_SDK": sdk_path,
                        "PATH": f"{os.path.join(sdk_path, 'bin')}:{env.get('PATH', '')}",
                    })
                    self._setup_sdk_files(sdk_path, self.tools_dir)
                
                # Run SCIP-Dart indexer
                subprocess.run(
                    [self.scip_dart_exe, "./"],
                    env=env,
                    check=True,
                    cwd=project_path
                )
                
                # Read and clean up the index file
                with open("index.scip", "rb") as f:
                    scip_data = f.read()
                os.remove("index.scip")
                
                return scip_data
                
            finally:
                os.chdir(original_dir) 