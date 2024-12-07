#!/usr/bin/env python3
"""
Command-line interface for Dart project indexing.
Provides tools for indexing Dart projects and processing SCIP data.
"""

import os
import sys
from typing import Optional
import click
from cli.dart_indexer import DartIndexer
from cli.scip_processor import SCIPProcessor

@click.group()
def cli() -> None:
    """CLI tool for working with Dart project indexing."""
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
    '--format',
    type=click.Choice(['text', 'summary', 'json']),
    default='json',
    help='Output format: text for full protobuf text format, summary for high-level overview, json for JSON format'
)
@click.option(
    '--symbols-only',
    is_flag=True,
    help='Show only symbol information'
)
def index(project_path: str, format: str, symbols_only: bool) -> None:
    """
    Index a Dart project and output the results.
    
    Args:
        project_path: Path to the Dart project root
        format: Output format (text, summary, or json)
        symbols_only: Whether to show only symbol information
    """
    try:
        # Initialize components
        indexer = DartIndexer()
        processor = SCIPProcessor()
        
        # Index the project
        click.echo("Indexing Dart project...", err=True)
        scip_data = indexer.index_project(project_path)
        
        # Process and output the results
        click.echo("Processing results...", err=True)
        output = processor.process_data(scip_data, format, symbols_only)
        click.echo(output)
        
    except Exception as e:
        raise click.ClickException(str(e))

def main() -> None:
    """Entry point for the CLI application."""
    cli()

if __name__ == '__main__':
    main()
