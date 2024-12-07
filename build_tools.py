#!/usr/bin/env python3

import os
import subprocess
import shutil
import tempfile
import json
from pathlib import Path
import requests

def run_command(cmd, cwd=None, env=None):
    """Run a command with proper error handling."""
    try:
        env = env or os.environ.copy()
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(cmd)}:")
        print(f"Exit code: {e.returncode}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise

def get_download_url(repo_url):
    """Get the download URL for a GitHub repository."""
    # Extract owner and repo from the URL
    if repo_url.endswith('.git'):
        repo_url = repo_url[:-4]
    owner_repo = repo_url.split('github.com/')[-1]
    owner, repo = owner_repo.split('/')
    
    # Get repository info from GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    print(f"Querying GitHub API: {api_url}")
    response = requests.get(api_url)
    response.raise_for_status()
    repo_info = response.json()
    
    # Get the default branch
    default_branch = repo_info['default_branch']
    print(f"Default branch is: {default_branch}")
    
    # Return the tarball URL
    tarball_url = f"https://github.com/{owner}/{repo}/archive/{default_branch}.tar.gz"
    return tarball_url

def download_repo(url, target_dir):
    """Download a repository using HTTPS."""
    print(f"Downloading {url}...")
    
    try:
        # Get the correct download URL
        download_url = get_download_url(url)
        print(f"Downloading from {download_url}...")
        
        # Create target directory's parent if it doesn't exist
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        
        # Download the tarball
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            tmp_file_path = tmp_file.name
        
        try:
            # Extract the tarball
            extract_dir = os.path.dirname(target_dir)
            print(f"Extracting to {extract_dir}...")
            run_command(['tar', 'xzf', tmp_file_path], cwd=extract_dir)
            
            # List the extracted contents
            contents = os.listdir(extract_dir)
            print(f"Directory contents: {contents}")
            
            # Find the extracted directory - it should be the only directory
            extracted_dirs = [d for d in contents if os.path.isdir(os.path.join(extract_dir, d))]
            if len(extracted_dirs) != 1:
                raise Exception(f"Expected exactly one extracted directory, found: {extracted_dirs}")
            
            extracted_dir = extracted_dirs[0]
            print(f"Found extracted directory: {extracted_dir}")
            source_path = os.path.join(extract_dir, extracted_dir)
            print(f"Moving {source_path} to {target_dir}")
            
            # Remove target directory if it exists
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            
            # Rename to target directory
            os.rename(source_path, target_dir)
            print(f"Successfully moved to {target_dir}")
            
        finally:
            # Clean up temporary file
            os.unlink(tmp_file_path)
            
    except requests.exceptions.RequestException as e:
        print(f"Error downloading repository: {str(e)}")
        raise
    except Exception as e:
        print(f"Error processing repository: {str(e)}")
        raise

def build_tools():
    """Build SCIP and SCIP-Dart tools during package build."""
    tools_dir = Path("cli/tools")
    dart_tools_dir = tools_dir / "dart"
    go_tools_dir = tools_dir / "go"
    
    # Build SCIP-Dart
    print("Building SCIP-Dart...")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Download SCIP-Dart
            scip_dart_url = "https://github.com/Workiva/scip-dart.git"
            scip_dart_dir = os.path.join(temp_dir, "scip-dart")
            download_repo(scip_dart_url, scip_dart_dir)
            
            # Create pubspec.lock with correct format
            pubspec_lock = {
                "packages": {
                    "watcher": {
                        "dependency": "direct main",
                        "description": {
                            "name": "watcher",
                            "sha256": "3d2ad6751b3c16cf07c7753bd163639c5420178cd8ab0b4f3714d71968480485",
                            "url": "https://pub.dev"
                        },
                        "source": "hosted",
                        "version": "1.1.0"
                    }
                },
                "sdks": {
                    "dart": ">=2.19.0 <4.0.0"
                }
            }
            with open(os.path.join(scip_dart_dir, "pubspec.lock"), "w") as f:
                json.dump(pubspec_lock, f, indent=2)
            
            # Build SCIP-Dart
            print("Running dart pub get...")
            env = os.environ.copy()
            env["PUB_CACHE"] = os.path.join(temp_dir, ".pub-cache")  # Use local pub cache
            run_command(["dart", "pub", "get"], cwd=scip_dart_dir, env=env)
            
            print("Compiling scip_dart...")
            run_command(
                ["dart", "compile", "exe", "--output=scip_dart", "bin/scip_dart.dart"],
                cwd=scip_dart_dir,
                env=env
            )
            
            # Copy the built binary
            print("Copying scip_dart binary...")
            binary_path = os.path.join(scip_dart_dir, "scip_dart")
            if not os.path.exists(binary_path):
                raise Exception(f"Binary not found at {binary_path}")
            
            # Copy the binary and set permissions
            target_path = dart_tools_dir / "scip_dart"
            shutil.copy2(binary_path, target_path)
            os.chmod(target_path, 0o755)
            
        except Exception as e:
            print(f"Error building SCIP-Dart: {str(e)}")
            raise
    
    # Build SCIP
    print("\nBuilding SCIP...")
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Download SCIP
            scip_url = "https://github.com/sourcegraph/scip.git"
            scip_dir = os.path.join(temp_dir, "scip")
            download_repo(scip_url, scip_dir)
            
            # Build SCIP
            print("Building SCIP binary...")
            run_command(
                ["go", "build", "-o", "scip", "./cmd/scip"],
                cwd=scip_dir
            )
            
            # Copy the binary and set permissions
            target_path = go_tools_dir / "scip"
            shutil.copy2(
                os.path.join(scip_dir, "scip"),
                target_path
            )
            os.chmod(target_path, 0o755)
            
        except Exception as e:
            print(f"Error building SCIP: {str(e)}")
            raise

    print("\nBuild completed successfully!")

if __name__ == "__main__":
    build_tools() 