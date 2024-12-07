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
from numbat import SourcetrailDB

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
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'text', 'summary', 'sourcetrail']),
    default='sourcetrail',
    help='Output format (json, text, summary, or sourcetrail)'
)
@click.option(
    '--symbols-only',
    is_flag=True,
    help='Only show symbol information'
)
def index(project_path: str, sourcetrail_db: Optional[str] = None, output_format: str = 'sourcetrail', symbols_only: bool = False) -> None:
    """Index a Dart/Flutter project and generate a Sourcetrail database.

    Creates a Sourcetrail-compatible index of your project's codebase.
    Automatically detects FVM if present.

    Example:
        $ dartindex index .
        $ dartindex index /path/to/project -o custom.srctrldb
        $ dartindex index . --format json --symbols-only  # Get JSON output of symbols
    """
    try:
        # Initialize components
        indexer = DartIndexer()
        processor = SCIPProcessor()
        
        # Index the project and get SCIP data
        click.echo("Indexing Dart project...", err=True)
        click.echo("This may take a few minutes for large projects...", err=True)
        scip_data = indexer.index_project(project_path)
        
        # Convert SCIP to requested format
        click.echo(f"Converting SCIP to {output_format}...", err=True)
        output = processor.process_data(scip_data, format_type=output_format, symbols_only=symbols_only)
        
        # Print the output directly if not creating Sourcetrail DB
        if output_format != 'sourcetrail':
            click.echo(output)
            return

        # Only create Sourcetrail DB if no format specified
        click.echo("Creating Sourcetrail database...", err=True)
        
        # Determine database path if not provided
        if sourcetrail_db is None:
            project_name = Path(project_path).name
            sourcetrail_db = str(Path(project_path) / f"{project_name}.srctrldb")
        click.echo(f"Using database path: {sourcetrail_db}", err=True)
        
        # Parse JSON string back to dictionary and convert to Sourcetrail DB
        scip_dict = json.loads(output)
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

class SourcetrailConverter:
    def __init__(self, db_path: str):
        self.db = SourcetrailDB.open(Path(db_path), clear=True)
        self.file_id_map = {}  # Map file paths to file_ids
        self.symbol_id_map = {}  # Map SCIP symbol IDs to Sourcetrail IDs

    def convert_file(self, file_path: str, language: str):
        """Record a source file and its language"""
        file_id = self.db.record_file(Path(file_path))
        self.db.record_file_language(file_id, language)
        self.file_id_map[file_path] = file_id
        return file_id

    def convert_symbol(self, symbol_info):
        """Convert SCIP symbol to Sourcetrail symbol"""
        symbol_id = None
        
        # Handle different symbol types
        if symbol_info.symbol_type == "class":
            symbol_id = self.db.record_class(
                name=symbol_info.name,
                prefix="class",
                postfix=":")
        elif symbol_info.symbol_type == "method":
            parent_id = self.symbol_id_map.get(symbol_info.parent_id)
            symbol_id = self.db.record_method(
                name=symbol_info.name,
                parent_id=parent_id)
        elif symbol_info.symbol_type == "field":
            parent_id = self.symbol_id_map.get(symbol_info.parent_id)
            symbol_id = self.db.record_field(
                name=symbol_info.name,
                parent_id=parent_id)

        if symbol_id:
            self.symbol_id_map[symbol_info.id] = symbol_id
        return symbol_id

    def record_location(self, symbol_id: int, file_id: int, location):
        """Record symbol location in source code"""
        # Record symbol location
        self.db.record_symbol_location(
            symbol_id,
            file_id,
            location.start_line,
            location.start_column,
            location.end_line,
            location.end_column
        )

        # Record symbol scope if applicable
        if hasattr(location, 'scope'):
            self.db.record_symbol_scope_location(
                symbol_id,
                file_id,
                location.scope.start_line,
                location.scope.start_column,
                location.scope.end_line,
                location.scope.end_column
            )

    def record_relationship(self, source_id: int, target_id: int, rel_type: str):
        """Record relationships between symbols"""
        if rel_type == "usage":
            self.db.record_ref_usage(source_id, target_id)
        elif rel_type == "call":
            self.db.record_ref_call(source_id, target_id)
        elif rel_type == "inheritance":
            self.db.record_ref_inheritance(source_id, target_id)
        elif rel_type == "override":
            self.db.record_ref_override(source_id, target_id)
        elif rel_type == "type_usage":
            self.db.record_ref_type_usage(source_id, target_id)

    def convert_scip_index(self, scip_index):
        """Convert entire SCIP index to Sourcetrail DB"""
        # Record all files first
        for file_info in scip_index.files:
            file_id = self.convert_file(file_info.path, file_info.language)
            
        # Record all symbols
        for symbol in scip_index.symbols:
            symbol_id = self.convert_symbol(symbol)
            if symbol_id and symbol.location:
                file_id = self.file_id_map[symbol.location.file_path]
                self.record_location(symbol_id, file_id, symbol.location)
        
        # Record all relationships
        for rel in scip_index.relationships:
            source_id = self.symbol_id_map[rel.source_id]
            target_id = self.symbol_id_map[rel.target_id]
            self.record_relationship(source_id, target_id, rel.type)

    def finalize(self):
        """Commit changes and close the database"""
        self.db.commit()
        self.db.close()
