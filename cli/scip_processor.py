"""
SCIP data processing functionality.
This module handles the processing and formatting of SCIP index data.
"""

import json
from typing import List, Dict, Any, Union
from google.protobuf import text_format
from google.protobuf.json_format import MessageToDict
from cli import scip_pb2

class SCIPProcessor:
    """Processes SCIP (Source Code Intelligence Protocol) index data."""
    
    def process_data(self, scip_data: bytes, format_type: str = "json", symbols_only: bool = False) -> str:
        """
        Process SCIP binary data into the requested format.
        
        Args:
            scip_data: Raw SCIP binary data
            format_type: Output format (json, text, summary, or sourcetrail)
            symbols_only: Whether to only show symbol information
            
        Returns:
            str: Formatted output
        """
        # Parse the SCIP data
        index = scip_pb2.Index()
        index.ParseFromString(scip_data)
        
        if symbols_only:
            return self._format_symbols(index, format_type)
        
        format_handlers = {
            "json": self._format_json,
            "text": lambda idx: text_format.MessageToString(idx, as_utf8=True),
            "summary": self._format_summary,
            "sourcetrail": self._format_json  # Use JSON format for sourcetrail conversion
        }
        
        if format_type not in format_handlers:
            raise ValueError(f"Unsupported format type: {format_type}")
            
        return format_handlers[format_type](index)

    def _format_symbols(self, index: scip_pb2.Index, format_type: str) -> str:
        """
        Format symbol information.
        
        Args:
            index: SCIP index
            format_type: Output format (json or text)
            
        Returns:
            str: Formatted symbol information
        """
        symbols = [
            {
                'symbol': symbol.symbol,
                'kind': scip_pb2.SymbolInformation.Kind.Name(symbol.kind),
                'display_name': symbol.display_name,
                'documentation': symbol.documentation,
                'language': doc.language,
                'relationships': len(symbol.relationships)
            }
            for doc in index.documents
            for symbol in doc.symbols
        ]
        
        if format_type == "json":
            return json.dumps(symbols, indent=2)
        
        # Format as text
        lines = []
        for symbol in symbols:
            lines.extend([
                f"\nSymbol: {symbol['symbol']}",
                f"Kind: {symbol['kind']}",
                f"Display Name: {symbol['display_name']}",
                f"Language: {symbol['language']}",
                f"Relationships: {symbol['relationships']}"
            ])
            if symbol['documentation']:
                lines.append("Documentation:")
                lines.extend(f"  {doc}" for doc in symbol['documentation'])
        
        return "\n".join(lines)

    def _format_json(self, index: scip_pb2.Index) -> str:
        """
        Format full index as JSON.
        
        Args:
            index: SCIP index
            
        Returns:
            str: JSON-formatted index data
        """
        data = MessageToDict(
            index,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
            descriptor_pool=None,
            float_precision=None
        )
        return json.dumps(data, indent=2)

    def _format_summary(self, index: scip_pb2.Index) -> str:
        """
        Format index summary.
        
        Args:
            index: SCIP index
            
        Returns:
            str: Summary of the index
        """
        lines = [
            f"SCIP Index Summary:",
            f"Project root: {index.metadata.project_root}",
            f"Tool: {index.metadata.tool_info.name} {index.metadata.tool_info.version}",
            f"Number of documents: {len(index.documents)}",
            f"Number of external symbols: {len(index.external_symbols)}",
            "\nDocuments:"
        ]
        
        for doc in index.documents:
            lines.extend([
                f"- {doc.relative_path} ({doc.language})",
                f"  Symbols: {len(doc.symbols)}",
                f"  Occurrences: {len(doc.occurrences)}"
            ])
        
        return "\n".join(lines) 