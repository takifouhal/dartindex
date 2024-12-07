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
        
    def convert(self, scip_json: Dict[str, Any]) -> None:
        """Convert SCIP JSON data to Sourcetrail DB format.
        
        Args:
            scip_json: Dictionary containing SCIP index data
        """
        try:
            # 1. Record source files
            documents = scip_json.get("documents", [])
            self._record_files(documents)
            
            # 2. Record symbols (classes, methods, fields)
            symbols = []
            # Check if symbols are nested in documents
            for doc in documents:
                doc_symbols = doc.get("symbols", [])
                symbols.extend(doc_symbols)
            
            self._record_symbols(symbols)
            
            # 3. Record relationships
            occurrences = []
            # Check if occurrences are nested in documents
            for doc in documents:
                doc_occurrences = doc.get("occurrences", [])
                occurrences.extend(doc_occurrences)
            
            self._record_relationships(occurrences)
            
            # 4. Commit and close
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
            
        except Exception as e:
            print(f"\nDEBUG: Error details: {str(e)}")
            self.db.close()
            raise e

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
                
            # Check relationships field first
            relationships = occurrence.get("relationships", [])
            for relationship in relationships:
                target_symbol = relationship.get("symbol", "")
                if not target_symbol or target_symbol.startswith("local "):
                    continue
                    
                # Parse the SCIP symbol to check if it's a method
                parts = target_symbol.split("/")
                if len(parts) >= 2:
                    last_part = parts[-1]
                    # Check for method call pattern in Dart SCIP format
                    if "#" in last_part and last_part.endswith("()."):
                        target_id = self.symbol_id_map.get(target_symbol)
                        if target_id:
                            # Record the call relationship
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
                            
                            # Update stats
                            self.call_stats["calls_by_file"][file_path] = self.call_stats["calls_by_file"].get(file_path, 0) + 1
                            target_name = relationship.get("display_name", target_symbol)
                            self.call_stats["most_called_methods"][target_name] = self.call_stats["most_called_methods"].get(target_name, 0) + 1
                            self.call_stats["most_calling_methods"][caller_name] = self.call_stats["most_calling_methods"].get(caller_name, 0) + 1
            
            # Also check symbol_roles for direct method calls
            symbol_roles = occurrence.get("symbol_roles", 0)
            target_symbol = occurrence.get("symbol", "")
            
            if (symbol_roles & 0x8) and target_symbol and not target_symbol.startswith("local "):
                parts = target_symbol.split("/")
                if len(parts) >= 2:
                    last_part = parts[-1]
                    # Check for method call pattern
                    if "#" in last_part and last_part.endswith("()."):
                        target_id = self.symbol_id_map.get(target_symbol)
                        if target_id:
                            # Record the call relationship if not already recorded
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
                            
                            # Update stats
                            self.call_stats["calls_by_file"][file_path] = self.call_stats["calls_by_file"].get(file_path, 0) + 1
                            target_name = occurrence.get("display_name", target_symbol)
                            self.call_stats["most_called_methods"][target_name] = self.call_stats["most_called_methods"].get(target_name, 0) + 1
                            self.call_stats["most_calling_methods"][caller_name] = self.call_stats["most_calling_methods"].get(caller_name, 0) + 1

    def _record_symbols(self, symbols: List[Dict[str, Any]]) -> None:
        """Record symbols in Sourcetrail DB."""
        print("\nProcessing symbols...")
        # First pass: record all classes and build maps
        class_map = {}  # Map class paths to their IDs
        private_class_map = {}  # Map for private classes
        generated_class_map = {}  # Map for generated classes (freezed, etc.)
        
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            if kind == "Class" or kind == "Interface" or (not kind and symbol_str.endswith("Class")):
                # Record the class/interface
                name = symbol_str.split("/")[-1] if "/" in symbol_str else symbol_str
                if name.endswith("."): 
                    name = name[:-1]
                if name.startswith("`") and name.endswith("`"):
                    name = name[1:-1]
                if "#" in name:
                    base_name = name.split("#")[0]
                    if "<get>" in name or "<set>" in name:
                        accessor = name[name.index("<"):name.index(">") + 1]
                        name = f"{base_name}{accessor}"
                    elif "<constructor>" in name:
                        name = base_name
                    else:
                        name = base_name

                symbol_id = self.db.record_class(name=name)
                self.stats["classes" if kind != "Interface" else "interfaces"] += 1
                
                # Record documentation and location
                documentation = self._get_documentation(symbol)
                signature = self._get_signature(symbol)
                
                file_id = self.file_id_map.get(self._get_safe(symbol, "document_path", ""))
                if file_id:
                    self._record_location_data(symbol_id, symbol, file_id)
                
                # Add to test namespace if test-related
                is_test_related = any(x in name for x in ["test", "mock", "fake", "_Fake", "Mock"])
                if is_test_related:
                    test_namespace_id = self.symbol_id_map.get("test_namespace")
                    if not test_namespace_id:
                        test_namespace_id = self.db.record_namespace(name="Tests")
                        self.symbol_id_map["test_namespace"] = test_namespace_id
                    self.db.record_ref_usage(symbol_id, test_namespace_id)
                
                # Store both full path and simple path
                full_path = symbol_str
                simple_path = symbol_str.split("#")[0] if "#" in symbol_str else symbol_str
                class_name = name
                
                # Store in appropriate map
                if class_name.startswith("_$") or ".freezed." in simple_path:
                    generated_class_map[full_path] = symbol_id
                    generated_class_map[simple_path] = symbol_id
                    if class_name.startswith("_$"):
                        base_name = class_name[2:]
                        base_path = "/".join(simple_path.split("/")[:-1] + [base_name])
                        generated_class_map[base_path] = symbol_id
                elif class_name.startswith("_"):
                    private_class_map[full_path] = symbol_id
                    private_class_map[simple_path] = symbol_id
                    base_name = class_name[1:]
                    base_path = "/".join(simple_path.split("/")[:-1] + [base_name])
                    private_class_map[base_path] = symbol_id
                else:
                    class_map[full_path] = symbol_id
                    class_map[simple_path] = symbol_id

            elif kind in ["Enum", "Package", "Module", "Namespace", "TypeAlias", "TypeDef"]:
                name = symbol_str.split("/")[-1] if "/" in symbol_str else symbol_str
                if name.endswith("."): 
                    name = name[:-1]
                if name.startswith("`") and name.endswith("`"):
                    name = name[1:-1]
                if "#" in name:
                    name = name.split("#")[0]
                
                if kind == "Enum":
                    self.db.record_enum(name=name)
                    self.stats["enums"] += 1
                elif kind in ["Package", "Module", "Namespace"]:
                    self.db.record_namespace(name=name)
                    self.stats["namespaces"] += 1
                else:  # TypeAlias or TypeDef
                    self.db.record_typedef_node(name=name)
                    self.stats["typedefs"] += 1

        print("First pass complete - Processing methods and fields...")
        # Second pass: record methods and fields
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            if kind in ["Method", "Function", "Constructor", "Field", "Property", "EnumConstant"]:
                name = symbol_str.split("/")[-1] if "/" in symbol_str else symbol_str
                if name.endswith("."): 
                    name = name[:-1]
                if name.startswith("`") and name.endswith("`"):
                    name = name[1:-1]
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
                
                # Get parent info
                parent_path = "/".join(symbol_str.split("/")[:-1])
                simple_path = parent_path.split("#")[0] if "#" in parent_path else parent_path
                
                parent_id = None
                if class_map:
                    parent_id = class_map.get(simple_path)
                if parent_id is None and private_class_map:
                    parent_id = private_class_map.get(simple_path)
                if parent_id is None and generated_class_map:
                    parent_id = generated_class_map.get(simple_path)
                
                if parent_id:
                    if kind == "Method" or kind == "Constructor":
                        symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                        self.db.record_ref_member(parent_id, symbol_id)
                        self.stats["methods"] += 1
                    else:  # Field, Property, EnumConstant
                        symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                        self.stats["fields"] += 1
                else:
                    # Top-level function or variable
                    if kind == "Method" or kind == "Function":
                        symbol_id = self.db.record_function(name=name)
                        self.stats["functions"] += 1
                    else:
                        symbol_id = self.db.record_global_variable(name=name)
                        self.stats["variables"] += 1

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
        print(f"Skipped local symbols: {self.skipped_local_symbols}")
        if self.missing_parent_symbols > 0:
            print(f"Warning: {self.missing_parent_symbols} symbols had missing parents")

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
                        start, end = range_data
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
                
                # Get target symbol from relationships
                relationships = occurrence.get("relationships", [])
                for relationship in relationships:
                    target_symbol = relationship.get("symbol", "")
                    if not target_symbol or target_symbol.startswith("local "):
                        continue  # Skip local variable targets
                        
                    target_id = self.symbol_id_map.get(target_symbol)
                    if not target_id:
                        continue

                    # Extract relationship context
                    is_mixin = "with" in occurrence.get("syntax", "").lower()
                    is_interface = "implements" in occurrence.get("syntax", "").lower()
                    is_superclass = "extends" in occurrence.get("syntax", "").lower()
                    
                    # Map SCIP symbol roles to Sourcetrail relationships
                    try:
                        # Basic references and definitions
                        if symbol_roles & 0x1:  # Definition
                            self.db.record_ref_usage(source_id, target_id)
                        if symbol_roles & 0x2:  # Import
                            self.db.record_ref_import(source_id, target_id)
                            
                        # Variable access and method calls
                        if symbol_roles & 0x8:  # ReadAccess
                            # For methods, this indicates a call
                            if "#" in target_symbol and target_symbol.endswith("()."):
                                self.db.record_ref_call(source_id, target_id)
                            else:
                                self.db.record_ref_usage(source_id, target_id)
                                
                        if symbol_roles & 0x4:  # WriteAccess
                            self.db.record_ref_usage(source_id, target_id)
                            
                        # Method calls and implementations
                        if symbol_roles & 0x40:  # ForwardDefinition - often used for interface implementations
                            if is_interface:
                                # Interface implementation
                                self.db.record_ref_implementation(source_id, target_id)
                            elif is_mixin:
                                # Mixin usage
                                self.db.record_ref_usage(source_id, target_id)
                                self.db.record_ref_implementation(source_id, target_id)
                            else:
                                # Regular implementation
                                self.db.record_ref_inheritance(source_id, target_id)
                                
                        # Inheritance and overrides
                        if is_superclass:
                            # Superclass inheritance
                            self.db.record_ref_inheritance(source_id, target_id)
                            if symbol_roles & 0x1:  # If also a definition, it's an override
                                self.db.record_ref_override(source_id, target_id)
                                
                        # Type relationships
                        if symbol_roles & 0x1 and target_symbol.endswith("#"):  # Type definition
                            if is_interface:
                                # Interface usage
                                self.db.record_ref_implementation(source_id, target_id)
                            elif is_mixin:
                                # Mixin usage
                                self.db.record_ref_usage(source_id, target_id)
                            else:
                                # Regular type usage
                                self.db.record_ref_type_usage(source_id, target_id)
                                
                        # Additional Dart-specific relationships
                        if target_symbol.endswith("<>"):  # Type parameter (generic)
                            self.db.record_ref_type_usage(source_id, target_id)
                        if "<" in target_symbol and ">" in target_symbol:  # Type argument
                            self.db.record_ref_type_usage(source_id, target_id)
                            
                    except Exception as e:
                        self.failed_relationships.append(f"{source_symbol} -> {target_symbol} (roles: {symbol_roles}) - Error: {str(e)}")
            except Exception as e:
                self.failed_relationships.append(f"Failed to process occurrence - Error: {str(e)}")