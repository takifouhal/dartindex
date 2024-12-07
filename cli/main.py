#!/usr/bin/env python3
"""
Command-line interface for Dart project indexing.
Provides tools for indexing Dart projects and processing SCIP data.
"""

import os
import sys
from typing import Optional
import click
from pathlib import Path
import json
from cli.dart_indexer import DartIndexer
from cli.scip_processor import SCIPProcessor
from cli.sourcetrail_converter import ScipToSourcetrail

@click.group()
def cli() -> None:
    """DartIndex - A tool for indexing Dart/Flutter projects with SCIP and Sourcetrail support."""
    pass

@cli.command()
@click.argument(
    'project_path',
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True
    )
)
@click.option(
    '-o', '--output',
    'sourcetrail_db',
    type=click.Path(
        file_okay=True,
        dir_okay=False,
        resolve_path=True
    ),
    default=None,
    help='Path for the Sourcetrail database (default: <project_name>.srctrldb in project directory)'
)
def index(project_path: str, sourcetrail_db: Optional[str] = None) -> None:
    """Index a Dart/Flutter project and generate a Sourcetrail database.

    Creates a Sourcetrail-compatible index of your project's codebase.
    Automatically detects FVM if present.

    Example:
        $ dartindex index .
        $ dartindex index /path/to/project -o custom.srctrldb
    """
    try:
        # Determine database path if not provided
        if sourcetrail_db is None:
            project_name = Path(project_path).name
            sourcetrail_db = str(Path(project_path) / f"{project_name}.srctrldb")

        click.echo(f"Using database path: {sourcetrail_db}", err=True)

        # Initialize components
        indexer = DartIndexer()
        processor = SCIPProcessor()
        
        # Index the project and get SCIP data
        click.echo("Indexing Dart project...", err=True)
        click.echo("This may take a few minutes for large projects...", err=True)
        scip_data = indexer.index_project(project_path)
        
        # Convert SCIP to JSON format
        click.echo("Converting SCIP to JSON...", err=True)
        scip_json = processor.process_data(scip_data)
        
        # Parse JSON string back to dictionary
        scip_dict = json.loads(scip_json)
        
        # Convert to Sourcetrail DB
        click.echo("Creating Sourcetrail database...", err=True)
        converter = ScipToSourcetrail(sourcetrail_db)
        converter.convert(scip_dict)
        
        click.echo(f"\nSuccess! 🎉 Sourcetrail database created at: {sourcetrail_db}", err=True)
        click.echo("\nYou can now open this database with Sourcetrail to explore your project.", err=True)
        
    except Exception as e:
        click.echo("\n❌ Error occurred:", err=True)
        raise click.ClickException(str(e))

def main() -> None:
    """Entry point for the CLI application."""
    cli()

if __name__ == '__main__':
    main()
