#!/usr/bin/env python3

import os
import sys
import click
from cli.dart_indexer import DartIndexer
from cli.scip_processor import SCIPProcessor

@click.group()
def cli():
    """CLI tool for working with Dart project indexing"""
    pass

@cli.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--format', type=click.Choice(['text', 'summary', 'json']), default='json',
              help='Output format: text for full protobuf text format, summary for high-level overview, json for JSON format')
@click.option('--symbols-only', is_flag=True, help='Show only symbol information')
def index(project_path, format, symbols_only):
    """Index a Dart project and output the results directly"""
    try:
        # Initialize the indexer and processor
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

def main():
    cli()

if __name__ == '__main__':
    main()
