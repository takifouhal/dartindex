"""
SCIP data processing functionality.
This module handles the processing and formatting of SCIP index data.
"""

import json
from google.protobuf import text_format
from google.protobuf.json_format import MessageToDict
from cli import scip_pb2

class SCIPProcessor:
    def __init__(self):
        """Initialize the SCIP processor."""
        pass

    def process_data(self, scip_data, format_type="json", symbols_only=False):
        """
        Process SCIP binary data into the requested format.
        
        Args:
            scip_data: Raw SCIP binary data
            format_type: Output format (json, text, or summary)
            symbols_only: Whether to only show symbol information
            
        Returns:
            str: Formatted output
        """
        # Parse the SCIP data
        index = scip_pb2.Index()
        index.ParseFromString(scip_data)
        
        if symbols_only:
            return self._format_symbols(index, format_type)
        elif format_type == "json":
            return self._format_json(index)
        elif format_type == "text":
            return text_format.MessageToString(index, as_utf8=True)
        else:
            return self._format_summary(index)

    def _format_symbols(self, index, format_type):
        """Format symbol information."""
        symbols = []
        for doc in index.documents:
            for symbol in doc.symbols:
                symbols.append({
                    'symbol': symbol.symbol,
                    'kind': scip_pb2.SymbolInformation.Kind.Name(symbol.kind),
                    'display_name': symbol.display_name,
                    'documentation': symbol.documentation,
                    'language': doc.language,
                    'relationships': len(symbol.relationships)
                })
        
        if format_type == "json":
            return json.dumps(symbols, indent=2)
        else:
            output = []
            for symbol in symbols:
                output.extend([
                    f"\nSymbol: {symbol['symbol']}",
                    f"Kind: {symbol['kind']}",
                    f"Display Name: {symbol['display_name']}",
                    f"Language: {symbol['language']}",
                    f"Relationships: {symbol['relationships']}"
                ])
                if symbol['documentation']:
                    output.append("Documentation:")
                    for doc in symbol['documentation']:
                        output.append(f"  {doc}")
            return "\n".join(output)

    def _format_json(self, index):
        """Format full index as JSON."""
        data = MessageToDict(
            index,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
            descriptor_pool=None,
            float_precision=None
        )
        return json.dumps(data, indent=2)

    def _format_summary(self, index):
        """Format index summary."""
        output = [
            f"SCIP Index Summary:",
            f"Project root: {index.metadata.project_root}",
            f"Tool: {index.metadata.tool_info.name} {index.metadata.tool_info.version}",
            f"Number of documents: {len(index.documents)}",
            f"Number of external symbols: {len(index.external_symbols)}",
            "\nDocuments:"
        ]
        
        for doc in index.documents:
            output.extend([
                f"- {doc.relative_path} ({doc.language})",
                f"  Symbols: {len(doc.symbols)}",
                f"  Occurrences: {len(doc.occurrences)}"
            ])
        
        return "\n".join(output) 