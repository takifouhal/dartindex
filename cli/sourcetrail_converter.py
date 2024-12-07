"""
Module for converting SCIP data to Sourcetrail database format.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from numbat import SourcetrailDB
import os


class ScipToSourcetrail:
    """Converts SCIP JSON data to Sourcetrail database format."""
    
    def __init__(self, db_path: str):
        """Initialize the converter with path to create Sourcetrail DB.
        
        Args:
            db_path: Path where the Sourcetrail database should be created
        """
        self.db = SourcetrailDB.open(Path(db_path), clear=True)
        self.symbol_id_map: Dict[str, int] = {}  # Map SCIP symbol IDs to Sourcetrail IDs
        self.file_id_map: Dict[str, int] = {}  # Map file paths to file IDs
        # Track issues
        self.unregistered_symbols = []
        self.failed_relationships = []
        self.skipped_local_symbols = 0
        self.missing_parent_symbols = 0
        # Add stats tracking
        self.stats = {
            "classes": 0,
            "interfaces": 0,
            "methods": 0,
            "fields": 0,
            "enums": 0,
            "namespaces": 0,
            "typedefs": 0,
            "functions": 0,
            "variables": 0,
        }
        # Add call graph statistics
        self.call_stats = {
            "direct_calls": 0,
            "async_calls": 0,
            "callback_registrations": 0,
            "indirect_calls": 0,
            "interface_calls": 0,
            "total_calls": 0,
            "calls_by_file": {},
            "most_called_methods": {},
            "most_calling_methods": {},
            "async_methods": set(),
            "callback_methods": set(),
        }
        self.symbol_definitions = {}  # Map symbol definitions for method call detection
        
    def convert(self, scip_json: Dict[str, Any]) -> None:
        """Convert SCIP JSON data to Sourcetrail DB format.
        
        Args:
            scip_json: Dictionary containing SCIP index data
        """
        documents = scip_json.get("documents", [])
        
        # First record all files
        self._record_files(documents)
        
        # Record external symbols first
        external_symbols = scip_json.get("external_symbols", [])
        if external_symbols:
            self._record_symbols(external_symbols)
        
        # Then record document symbols
        for document in documents:
            symbols = document.get("symbols", [])
            if symbols:
                self._record_symbols(symbols)
                
            # Process all occurrences for relationships
            occurrences = document.get("occurrences", [])
            if occurrences:
                self._record_relationships(occurrences)
        
        # Commit and close
        self.db.commit()
        self.db.close()
        
        # Report aggregate issues
        if any([self.unregistered_symbols, self.failed_relationships, self.skipped_local_symbols, self.missing_parent_symbols]):
            print("\nRegistration Issues Summary:")
            if self.skipped_local_symbols:
                print(f"- Skipped {self.skipped_local_symbols} local symbols")
            if self.missing_parent_symbols:
                print(f"- {self.missing_parent_symbols} symbols had missing parent symbols")
            if self.unregistered_symbols:
                print("\nFailed to register symbols:")
                for sym in self.unregistered_symbols[:10]:  # Show first 10
                    print(f"- {sym}")
                if len(self.unregistered_symbols) > 10:
                    print(f"  ... and {len(self.unregistered_symbols) - 10} more")
            if self.failed_relationships:
                print("\nFailed to register relationships:")
                for rel in self.failed_relationships[:10]:  # Show first 10
                    print(f"- {rel}")
                if len(self.failed_relationships) > 10:
                    print(f"  ... and {len(self.failed_relationships) - 10} more")
        
        print("\nSymbol Registration Summary:")
        print(f"Classes: {self.stats['classes']}")
        print(f"Interfaces: {self.stats['interfaces']}")
        print(f"Methods: {self.stats['methods']}")
        print(f"Fields: {self.stats['fields']}")
        print(f"Enums: {self.stats['enums']}")
        print(f"Namespaces: {self.stats['namespaces']}")
        print(f"Typedefs: {self.stats['typedefs']}")
        print(f"Functions: {self.stats['functions']}")
        print(f"Variables: {self.stats['variables']}")

        print("\nCall Graph Summary:")
        print(f"Total Call Relationships: {self.call_stats['total_calls']}")
        print(f"- Direct Method Calls: {self.call_stats['direct_calls']}")
        print(f"- Async Method Calls: {self.call_stats['async_calls']}")
        print(f"- Callback Registrations: {self.call_stats['callback_registrations']}")
        print(f"- Indirect Calls: {self.call_stats['indirect_calls']}")
        print(f"- Interface/Implementation Calls: {self.call_stats['interface_calls']}")
        print(f"\nAsync Methods: {len(self.call_stats['async_methods'])}")
        print(f"Methods with Callbacks: {len(self.call_stats['callback_methods'])}")
        
        # Show top 5 most called methods
        print("\nTop 5 Most Called Methods:")
        for method, count in sorted(self.call_stats['most_called_methods'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"- {method}: {count} calls")
        
        # Show top 5 most calling methods
        print("\nTop 5 Most Active Callers:")
        for method, count in sorted(self.call_stats['most_calling_methods'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"- {method}: {count} outgoing calls")
        
        # Show files with most calls
        print("\nTop 5 Files with Most Calls:")
        for file, count in sorted(self.call_stats['calls_by_file'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"- {file}: {count} calls")
        
    def _record_files(self, documents: List[Dict[str, Any]]) -> None:
        """Record source files in Sourcetrail DB."""
        for doc in documents:
            file_path = Path(doc["relative_path"])
            file_id = self.db.record_file(file_path)
            
            # Record language if available
            language = doc.get("language", "unknown")
            self.db.record_file_language(file_id, language)
            self.file_id_map[str(file_path)] = file_id

    def _get_safe(self, obj, key, default=None):
        """Safely get a value from either a dict or list."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        elif isinstance(obj, list) and len(obj) > 0:
            # For lists, try to find an item that has the key
            for item in obj:
                if isinstance(item, dict) and key in item:
                    return item[key]
        return default

    def _get_documentation(self, symbol):
        """Extract documentation from symbol data."""
        doc = self._get_safe(symbol, "documentation", {})
        if isinstance(doc, dict):
            return doc.get("text", "")
        elif isinstance(doc, list) and len(doc) > 0:
            return doc[0].get("text", "") if isinstance(doc[0], dict) else ""
        return ""

    def _get_signature(self, symbol):
        """Extract signature from symbol data."""
        sig = self._get_safe(symbol, "signature_documentation", {})
        if isinstance(sig, dict):
            return sig.get("text", "")
        elif isinstance(sig, list) and len(sig) > 0:
            return sig[0].get("text", "") if isinstance(sig[0], dict) else ""
        return ""

    def _get_range_data(self, symbol):
        """Extract range data from symbol."""
        range_data = self._get_safe(symbol, "range", {})
        if not range_data:
            return None
            
        start = self._get_safe(range_data, "start", {})
        end = self._get_safe(range_data, "end", {})
        
        if not start or not end:
            return None
            
        return {
            "start_line": self._get_safe(start, "line", 0),
            "start_col": self._get_safe(start, "character", 0),
            "end_line": self._get_safe(end, "line", 0),
            "end_col": self._get_safe(end, "character", 0)
        }

    def _record_location_data(self, symbol_id, symbol, file_id=None):
        """Record location data for a symbol."""
        if not file_id:
            file_id = self.file_id_map.get(self._get_safe(symbol, "document_path", ""))
        
        if not file_id:
            return
            
        range_data = self._get_range_data(symbol)
        if not range_data:
            return
            
        # Record basic location
        self.db.record_symbol_location(
            symbol_id, 
            file_id,
            range_data["start_line"],
            range_data["start_col"]
        )
        
        # Record scope location
        self.db.record_symbol_scope_location(
            symbol_id,
            file_id,
            range_data["start_line"],
            range_data["start_col"],
            range_data["end_line"],
            range_data["end_col"]
        )
        
        return range_data

    def _process_symbol(self, symbol: Dict[str, Any]) -> Optional[int]:
        """Process a single symbol and record it in the database.
        
        Args:
            symbol: Dictionary containing symbol data
            
        Returns:
            Optional[int]: The symbol ID if successfully recorded, None otherwise
        """
        symbol_str = symbol.get("symbol", "")
        if not symbol_str:
            return None
            
        # Skip local symbols
        if symbol_str.startswith("local "):
            self.skipped_local_symbols += 1
            return None
            
        # Get basic symbol info
        kind = symbol.get("kind", "")
        name = symbol_str.split("/")[-1] if "/" in symbol_str else symbol_str
        
        # Clean up name
        if name.endswith("."): 
            name = name[:-1]
        if name.startswith("`") and name.endswith("`"):
            name = name[1:-1]
            
        # Handle method names
        if "#" in name:
            base_name = name.split("#")[0]
            method_name = name.split("#")[1]
            if "<get>" in method_name or "<set>" in method_name:
                accessor = method_name[method_name.index("<"):method_name.index(">") + 1]
                name = f"{base_name}{accessor}"
            elif "<constructor>" in method_name:
                name = base_name
            else:
                name = method_name.rstrip("().")
        
        # Get parent info if this is a member
        parent_id = None
        if "/" in symbol_str:
            parent_path = "/".join(symbol_str.split("/")[:-1])
            parent_id = self.symbol_id_map.get(parent_path)
        
        # Record symbol based on kind
        symbol_id = None
        if kind == "Class" or kind == "Interface" or (not kind and symbol_str.endswith("Class")):
            symbol_id = self.db.record_class(name=name, parent_id=parent_id)
            self.stats["classes" if kind != "Interface" else "interfaces"] += 1
        elif kind == "Method" or kind == "Constructor":
            symbol_id = self.db.record_method(name=name, parent_id=parent_id)
            if parent_id:
                self.db.record_ref_member(parent_id, symbol_id)
            self.stats["methods"] += 1
        elif kind == "Field" or kind == "Property":
            symbol_id = self.db.record_field(name=name, parent_id=parent_id)
            if parent_id:
                self.db.record_ref_member(parent_id, symbol_id)
            self.stats["fields"] += 1
        elif kind == "Function":
            symbol_id = self.db.record_function(name=name)
            self.stats["functions"] += 1
        elif kind == "Variable":
            symbol_id = self.db.record_global_variable(name=name)
            self.stats["variables"] += 1
        
        # Record location if available
        if symbol_id:
            file_path = self._get_safe(symbol, "document_path", "")
            file_id = self.file_id_map.get(file_path)
            if file_id:
                range_data = symbol.get("range", {})
                if range_data:
                    if isinstance(range_data, list):
                        start_line, start_col, end_col = range_data
                        end_line = start_line
                    else:
                        start = range_data.get("start", {})
                        end = range_data.get("end", start)
                        start_line = start.get("line", 0)
                        start_col = start.get("character", 0)
                        end_line = end.get("line", start_line)
                        end_col = end.get("character", start_col)
                    
                    self.db.record_symbol_location(
                        symbol_id,
                        file_id,
                        start_line,
                        start_col,
                        end_line,
                        end_col
                    )
            
            # Store in symbol map
            self.symbol_id_map[symbol_str] = symbol_id
        
        return symbol_id

    def _record_call_relationships(self, symbol_id: int, symbol: Dict[str, Any], occurrences: List[Dict[str, Any]]) -> None:
        """Record all types of call relationships for a symbol.
        
        Args:
            symbol_id: Sourcetrail ID of the calling symbol
            symbol: SCIP symbol data
            occurrences: List of symbol occurrences
        """
        # Get caller info for stats
        caller_name = self._get_safe(symbol, "display_name", "unknown")
        file_path = self._get_safe(symbol, "document_path", "unknown")
        
        # Process direct method calls from occurrences
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                continue
                
            # Check both relationships and symbol roles
            relationships = occurrence.get("relationships", [])
            symbol_roles = occurrence.get("symbol_roles", 0)
            
            # Process relationships
            for relationship in relationships:
                target_symbol = relationship.get("symbol", "")
                if not target_symbol or target_symbol.startswith("local "):
                    continue
                    
                target_id = self.symbol_id_map.get(target_symbol)
                if target_id:
                    # Record call if it's a method call (has # and ends with .)
                    parts = target_symbol.split("/")
                    if len(parts) >= 2 and "#" in parts[-1]:
                        self.db.record_ref_call(symbol_id, target_id)
                        self.call_stats["direct_calls"] += 1
                        self.call_stats["total_calls"] += 1
                        
                        # Record location if available
                        file_id = self.file_id_map.get(file_path)
                        if file_id and "range" in occurrence:
                            range_data = occurrence["range"]
                            if isinstance(range_data, list):
                                start_line, start_col, end_col = range_data
                                end_line = start_line
                            else:
                                start = range_data.get("start", {})
                                end = range_data.get("end", start)
                                start_line = start.get("line", 0)
                                start_col = start.get("character", 0)
                                end_line = end.get("line", start_line)
                                end_col = end.get("character", start_col)
                            
                            self.db.record_reference_location(
                                symbol_id,
                                file_id,
                                start_line,
                                start_col,
                                end_line,
                                end_col
                            )
            
            # Check symbol roles for method calls
            if symbol_roles & 0x8:  # ReadAccess - often indicates a method call
                target_symbol = occurrence.get("symbol", "")
                if target_symbol and not target_symbol.startswith("local "):
                    target_id = self.symbol_id_map.get(target_symbol)
                    if target_id and "#" in target_symbol:
                        self.db.record_ref_call(symbol_id, target_id)
                        self.call_stats["direct_calls"] += 1
                        self.call_stats["total_calls"] += 1

    def _record_symbols(self, symbols: List[Dict[str, Any]]) -> None:
        """Record symbols in Sourcetrail DB."""
        for symbol in symbols:
            try:
                # Store symbol definition for method call detection
                symbol_str = symbol.get("symbol", "")
                if symbol_str:
                    self.symbol_definitions[symbol_str] = symbol
                
                # Process and record the symbol
                symbol_id = self._process_symbol(symbol)
                if not symbol_id:
                    self.unregistered_symbols.append(symbol_str)
                    continue
                    
                # Record documentation if available
                documentation = self._get_documentation(symbol)
                if documentation:
                    # Use symbol scope location to store documentation
                    file_path = self._get_safe(symbol, "document_path", "")
                    file_id = self.file_id_map.get(file_path)
                    if file_id:
                        range_data = symbol.get("range", {})
                        if range_data:
                            if isinstance(range_data, list):
                                start_line, start_col, end_col = range_data
                                end_line = start_line
                            else:
                                start = range_data.get("start", {})
                                end = range_data.get("end", start)
                                start_line = start.get("line", 0)
                                start_col = start.get("character", 0)
                                end_line = end.get("line", start_line)
                                end_col = end.get("character", start_col)
                            
                            self.db.record_symbol_scope_location(
                                symbol_id,
                                file_id,
                                start_line,
                                start_col,
                                end_line,
                                end_col
                            )
                    
                # Record location data
                self._record_location_data(symbol_id, symbol)
                
                # Record call relationships
                occurrences = symbol.get("occurrences", [])
                if occurrences:
                    self._record_call_relationships(symbol_id, symbol, occurrences)
                    
            except Exception as e:
                print(f"Error processing symbol: {str(e)}")

    def _record_relationships(self, occurrences: List[Dict[str, Any]]) -> None:
        """Record relationships between symbols."""
        for occurrence in occurrences:
            try:
                # Get source symbol
                source_symbol = occurrence.get("symbol", "")
                if not source_symbol or source_symbol.startswith("local "):
                    continue  # Skip local variable sources
                
                source_id = self.symbol_id_map.get(source_symbol)
                if not source_id:
                    continue

                # Record symbol location if available
                file_path = occurrence.get("document_path", "")
                file_id = self.file_id_map.get(file_path)
                range_data = occurrence.get("range", {})
                
                if file_id and range_data:
                    # Handle different range formats
                    if isinstance(range_data, list):
                        start_line, start_col, end_col = range_data
                        end_line = start_line
                    else:
                        start = range_data.get("start", {})
                        end = range_data.get("end", start)
                        start_line = start.get("line", 0)
                        start_col = start.get("character", 0)
                        end_line = end.get("line", start_line)
                        end_col = end.get("character", start_col)
                
                    self.db.record_symbol_location(
                        source_id,
                        file_id,
                        start_line,
                        start_col,
                        end_line,
                        end_col
                    )
                
                # Record relationships
                symbol_roles = occurrence.get("symbol_roles", 0)
                
                # Process both direct relationships and symbol roles
                relationships = occurrence.get("relationships", [])
                for relationship in relationships:
                    target_symbol = relationship.get("symbol", "")
                    if not target_symbol or target_symbol.startswith("local "):
                        continue  # Skip local variable targets
                        
                    target_id = self.symbol_id_map.get(target_symbol)
                    if not target_id:
                        continue

                    # Extract relationship context
                    syntax = occurrence.get("syntax", "").lower()
                    is_mixin = "with" in syntax
                    is_interface = "implements" in syntax
                    is_superclass = "extends" in syntax
                    
                    # Check for method calls in relationships
                    is_reference = relationship.get("is_reference", False)
                    is_implementation = relationship.get("is_implementation", False)
                    is_method_call = (
                        target_symbol.endswith("().") or 
                        target_symbol.endswith(".") or
                        "#" in target_symbol
                    )
                    
                    # Record method calls
                    if is_method_call and (is_reference or is_implementation or symbol_roles & 0x8):
                        self.db.record_ref_call(source_id, target_id)
                        self.call_stats["direct_calls"] += 1
                        self.call_stats["total_calls"] += 1
                        
                        # Record location for the call
                        if file_id and range_data:
                            self.db.record_reference_location(
                                source_id,
                                file_id,
                                start_line,
                                start_col,
                                end_line,
                                end_col
                            )
                        continue
                        
                    # Handle other relationships
                    if symbol_roles & 0x1:  # Definition
                        self.db.record_ref_usage(source_id, target_id)
                    if symbol_roles & 0x2:  # Import
                        self.db.record_ref_import(source_id, target_id)
                    if symbol_roles & 0x4:  # WriteAccess
                        self.db.record_ref_usage(source_id, target_id)
                            
                    # Handle inheritance and implementations
                    if is_interface:
                        self.db.record_ref_implementation(source_id, target_id)
                    elif is_mixin:
                        self.db.record_ref_usage(source_id, target_id)
                        self.db.record_ref_implementation(source_id, target_id)
                    elif is_superclass:
                        self.db.record_ref_inheritance(source_id, target_id)
                        if symbol_roles & 0x1:  # If also a definition, it's an override
                            self.db.record_ref_override(source_id, target_id)
                            
                # Also check the occurrence's own symbol for method calls
                if "#" in source_symbol and (source_symbol.endswith("().") or source_symbol.endswith(".")):
                    # This is a method call occurrence
                    caller_parts = source_symbol.split("#")
                    if len(caller_parts) >= 2:
                        # Get the class/type that contains this method
                        caller_type = caller_parts[0] + "#"
                        caller_id = self.symbol_id_map.get(caller_type)
                        if caller_id:
                            self.db.record_ref_call(source_id, caller_id)
                            self.call_stats["direct_calls"] += 1
                            self.call_stats["total_calls"] += 1
                            
                # Check for method calls in the symbol kind
                symbol_def = self.symbol_definitions.get(source_symbol, {})
                if symbol_def.get("kind") == "Method":
                    # This is a method definition, record any relationships as calls
                    for rel in symbol_def.get("relationships", []):
                        target_symbol = rel.get("symbol", "")
                        if not target_symbol or target_symbol.startswith("local "):
                            continue
                        target_id = self.symbol_id_map.get(target_symbol)
                        if target_id:
                            self.db.record_ref_call(source_id, target_id)
                            self.call_stats["direct_calls"] += 1
                            self.call_stats["total_calls"] += 1
                            
            except Exception as e:
                print(f"Error processing relationship: {str(e)}")