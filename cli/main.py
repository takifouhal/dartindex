#!/usr/bin/env python3

import os
import sys
import json
import click
from google.protobuf import text_format
from google.protobuf.json_format import MessageToDict

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import scip_pb2

@click.group()
def cli():
    """CLI tool for working with SCIP index files"""
    pass

@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--format', type=click.Choice(['text', 'summary', 'json']), default='text',
              help='Output format: text for full protobuf text format, summary for high-level overview, json for JSON format')
@click.option('--symbols-only', is_flag=True, help='Show only symbol information')
@click.option('--filter-language', help='Filter results by programming language')
def deserialize(input_file, format, symbols_only, filter_language):
    """Deserialize a SCIP index file and display its contents"""
    try:
        # Read the binary protobuf file
        with open(input_file, 'rb') as f:
            data = f.read()
        
        # Parse the protobuf message
        index = scip_pb2.Index()
        index.ParseFromString(data)
        
        if symbols_only:
            _display_symbols(index, format, filter_language)
        elif format == 'json':
            _display_json(index)
        elif format == 'text':
            print(text_format.MessageToString(index, as_utf8=True))
        else:
            _display_summary(index, filter_language)

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--language', help='Filter by programming language')
def analyze(input_file, language):
    """Analyze a SCIP index file and show detailed statistics"""
    try:
        with open(input_file, 'rb') as f:
            index = scip_pb2.Index()
            index.ParseFromString(f.read())
        
        stats = {
            'total_documents': len(index.documents),
            'total_symbols': len(index.external_symbols),
            'languages': {},
            'symbol_kinds': {},
            'relationships': 0
        }

        for doc in index.documents:
            if language and doc.language != language:
                continue
                
            lang = doc.language or 'unknown'
            if lang not in stats['languages']:
                stats['languages'][lang] = {
                    'documents': 0,
                    'symbols': 0,
                    'occurrences': 0
                }
            
            stats['languages'][lang]['documents'] += 1
            stats['languages'][lang]['symbols'] += len(doc.symbols)
            stats['languages'][lang]['occurrences'] += len(doc.occurrences)

            for symbol in doc.symbols:
                kind = scip_pb2.SymbolInformation.Kind.Name(symbol.kind)
                stats['symbol_kinds'][kind] = stats['symbol_kinds'].get(kind, 0) + 1
                stats['relationships'] += len(symbol.relationships)

        # Display statistics
        click.echo("\n=== SCIP Index Analysis ===")
        click.echo(f"\nProject: {index.metadata.project_root}")
        click.echo(f"Tool: {index.metadata.tool_info.name} {index.metadata.tool_info.version}")
        
        click.echo("\nOverall Statistics:")
        click.echo(f"- Total Documents: {stats['total_documents']}")
        click.echo(f"- Total External Symbols: {stats['total_symbols']}")
        click.echo(f"- Total Relationships: {stats['relationships']}")
        
        click.echo("\nLanguage Statistics:")
        for lang, lang_stats in stats['languages'].items():
            click.echo(f"\n{lang}:")
            click.echo(f"  - Documents: {lang_stats['documents']}")
            click.echo(f"  - Symbols: {lang_stats['symbols']}")
            click.echo(f"  - Occurrences: {lang_stats['occurrences']}")
        
        click.echo("\nSymbol Kinds:")
        for kind, count in stats['symbol_kinds'].items():
            click.echo(f"- {kind}: {count}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

def _display_symbols(index, format, filter_language):
    """Display symbol information in the specified format"""
    symbols = []
    for doc in index.documents:
        if filter_language and doc.language != filter_language:
            continue
        for symbol in doc.symbols:
            symbols.append({
                'symbol': symbol.symbol,
                'kind': scip_pb2.SymbolInformation.Kind.Name(symbol.kind),
                'display_name': symbol.display_name,
                'documentation': symbol.documentation,
                'language': doc.language,
                'relationships': len(symbol.relationships)
            })
    
    if format == 'json':
        print(json.dumps(symbols, indent=2))
    else:
        for symbol in symbols:
            print(f"\nSymbol: {symbol['symbol']}")
            print(f"Kind: {symbol['kind']}")
            print(f"Display Name: {symbol['display_name']}")
            print(f"Language: {symbol['language']}")
            print(f"Relationships: {symbol['relationships']}")
            if symbol['documentation']:
                print("Documentation:")
                for doc in symbol['documentation']:
                    print(f"  {doc}")

def _display_json(index):
    """Convert the index to JSON format with all nested fields"""
    # Convert protobuf message to dict using the official protobuf JSON formatter
    data = MessageToDict(
        index,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
        descriptor_pool=None,
        float_precision=None
    )
    
    print(json.dumps(data, indent=2))

def _display_summary(index, filter_language):
    """Display a summary of the index"""
    print(f"SCIP Index Summary:")
    print(f"Project root: {index.metadata.project_root}")
    print(f"Tool: {index.metadata.tool_info.name} {index.metadata.tool_info.version}")
    
    if filter_language:
        docs = [d for d in index.documents if d.language == filter_language]
    else:
        docs = index.documents
    
    print(f"Number of documents: {len(docs)}")
    print(f"Number of external symbols: {len(index.external_symbols)}")
    
    print("\nDocuments:")
    for doc in docs:
        print(f"- {doc.relative_path} ({doc.language})")
        print(f"  Symbols: {len(doc.symbols)}")
        print(f"  Occurrences: {len(doc.occurrences)}")

if __name__ == '__main__':
    cli()
