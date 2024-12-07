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

class DartIndexer:
    def __init__(self):
        """Initialize the DartIndexer."""
        # Get the directory where the executable is located
        if getattr(sys, 'frozen', False):
            # Running in a PyInstaller bundle
            base_path = sys._MEIPASS
        else:
            # Running in a normal Python environment
            base_path = os.path.dirname(os.path.abspath(__file__))

        # Tools are now directly in the tools directory at the root
        self.tools_dir = os.path.join(base_path, "tools")
        self.scip_dart_exe = os.path.join(self.tools_dir, "dart", "scip_dart")
        self.scip_exe = os.path.join(self.tools_dir, "go", "scip")
        
        # Make executables executable
        if sys.platform != "win32":
            os.chmod(self.scip_dart_exe, 0o755)
            os.chmod(self.scip_exe, 0o755)

    def _get_fvm_version(self, project_path):
        """
        Get the Flutter version from FVM configuration.
        
        Args:
            project_path: Path to the project root
            
        Returns:
            str: Flutter version or None if not found
        """
        # First check .fvm/fvm_config.json
        fvm_config = os.path.join(project_path, ".fvm/fvm_config.json")
        if os.path.exists(fvm_config):
            try:
                with open(fvm_config, 'r') as f:
                    config = json.load(f)
                    version = config.get('flutterSdkVersion')
                    if version:
                        return version
            except:
                pass
        
        # Then check .fvm/version file
        version_file = os.path.join(project_path, ".fvm/version")
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r') as f:
                    version = f.read().strip()
                    if version:
                        return version
            except:
                pass
        
        return None

    def _setup_sdk_files(self, sdk_path, tools_dir):
        """
        Set up SDK files by copying them to the tools directory.
        
        Args:
            sdk_path: Path to the Dart SDK
            tools_dir: Path to the tools directory
        """
        try:
            # Create the target directories
            tools_lib = os.path.join(tools_dir, "lib")
            os.makedirs(tools_lib, exist_ok=True)
            internal_dir = os.path.join(tools_lib, "_internal")
            os.makedirs(internal_dir, exist_ok=True)
            
            # Copy the required SDK files
            sdk_lib = os.path.join(sdk_path, "lib")
            sdk_internal = os.path.join(sdk_lib, "_internal")
            
            # Copy version file
            version_file = os.path.join(sdk_path, "version")
            if os.path.exists(version_file):
                shutil.copy2(version_file, os.path.join(tools_dir, "version"))
            
            # Files to copy from lib/_internal
            internal_files = [
                ("sdk_library_metadata/lib/libraries.dart", "sdk_library_metadata/lib/libraries.dart"),
                ("libraries.dart", "libraries.dart"),
                ("allowed_experiments.json", "allowed_experiments.json"),
                ("sdk_library_metadata", "sdk_library_metadata"),
                ("sdk", "sdk"),
                ("release", "release"),
                ("specification", "specification"),
            ]
            
            for src_rel, dst_rel in internal_files:
                src = os.path.join(sdk_internal, src_rel)
                dst = os.path.join(internal_dir, dst_rel)
                
                if os.path.exists(src):
                    # Create parent directory if needed
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst, symlinks=True)
                    else:
                        shutil.copy2(src, dst)
            
            # Copy additional SDK metadata
            for item in ["version", "revision", "release"]:
                src = os.path.join(sdk_path, item)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(tools_dir, item))
            
        except Exception as e:
            print(f"Warning: Failed to set up SDK files: {str(e)}")

    def _get_dart_info(self, project_path):
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
                # Ensure we're using the right version
                subprocess.run(["fvm", "use", fvm_version], 
                             cwd=project_path,
                             check=True,
                             capture_output=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to set FVM version: {e.stderr.decode() if e.stderr else str(e)}")
            
            # Try to get the SDK path from FVM
            try:
                # Get the Flutter SDK path from FVM
                result = subprocess.run(
                    ["fvm", "flutter", "which", "flutter"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                flutter_path = result.stdout.strip()
                if flutter_path:
                    # The Dart SDK is in the cache directory of the Flutter SDK
                    sdk_path = os.path.abspath(os.path.join(
                        os.path.dirname(os.path.dirname(flutter_path)),
                        "bin/cache/dart-sdk"
                    ))
                    if os.path.exists(sdk_path):
                        return ["fvm", "dart"], sdk_path
            except:
                pass
            
            # Fallback to common FVM paths
            paths_to_try = [
                os.path.expanduser(f"~/.fvm/versions/{fvm_version}/bin/cache/dart-sdk"),
                os.path.join(project_path, ".fvm/flutter_sdk/bin/cache/dart-sdk"),
                os.path.abspath(os.path.join(project_path, f".fvm/versions/{fvm_version}/bin/cache/dart-sdk"))
            ]
            
            for path in paths_to_try:
                if os.path.exists(path):
                    return ["fvm", "dart"], path
        
        # For non-FVM projects, try to get system Dart SDK path
        try:
            result = subprocess.run(["dart", "--version"], 
                                 capture_output=True, 
                                 text=True)
            dart_path = subprocess.run(["which", "dart"], 
                                    capture_output=True, 
                                    text=True).stdout.strip()
            if dart_path:
                sdk_path = os.path.dirname(os.path.dirname(dart_path))
                if os.path.exists(os.path.join(sdk_path, "lib")):
                    return ["dart"], sdk_path
        except:
            pass
            
        return ["dart"], None

    def index_project(self, project_path):
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
                
                # Run pub get in the target project using the appropriate dart command
                subprocess.run(dart_cmd + ["pub", "get"], 
                             check=True,
                             cwd=project_path)
                
                # Run the SCIP-Dart indexer with SDK path if available
                env = os.environ.copy()
                if sdk_path and os.path.exists(sdk_path):
                    print(f"Using Dart SDK from: {sdk_path}")
                    env.update({
                        "DART_SDK": sdk_path,
                        "PATH": f"{os.path.join(sdk_path, 'bin')}:{env.get('PATH', '')}",
                    })
                    
                    # Set up SDK files in the tools directory
                    self._setup_sdk_files(sdk_path, self.tools_dir)
                
                subprocess.run([self.scip_dart_exe, "./"], 
                             env=env, 
                             check=True,
                             cwd=project_path)
                
                # Read the generated index.scip file
                with open("index.scip", "rb") as f:
                    scip_data = f.read()
                
                # Clean up the generated file
                os.remove("index.scip")
                
                return scip_data
                
            finally:
                os.chdir(original_dir) 