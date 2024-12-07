"""
Module for converting SCIP data to Sourcetrail database format.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from numbat import SourcetrailDB


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

    def _record_symbols(self, symbols: List[Dict[str, Any]]) -> None:
        """Record symbols in Sourcetrail DB."""
        # First pass: record all non-dependent symbols and build type parameter map
        type_param_map = {}  # Map to store type parameters and their owners
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            # First pass: handle non-dependent symbols and collect type parameter info
            if kind in ["Class", "Interface", "Enum", "Package", "Module", "Namespace", "TypeAlias", "TypeDef"]:
                symbol_id = self._record_symbol(symbol)
                if symbol_id and kind in ["Class", "Interface"]:
                    # Check if this class/interface has type parameters
                    class_path = symbol_str.split("#")[0] if "#" in symbol_str else symbol_str
                    for s in symbols:
                        if s.get("kind") == "TypeParameter" and s.get("symbol", "").startswith(class_path):
                            type_param_map[s.get("symbol")] = symbol_id

        # Second pass: record symbols that might depend on others
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            # Second pass: handle dependent symbols
            if kind not in ["Class", "Interface", "Enum", "Package", "Module", "Namespace", "TypeAlias", "TypeDef"]:
                if kind == "TypeParameter":
                    # Try to find the owning class/interface from our map
                    owner_id = type_param_map.get(symbol_str)
                    if owner_id:
                        self._record_symbol(symbol, forced_parent_id=owner_id)
                    else:
                        self._record_symbol(symbol)
                else:
                    self._record_symbol(symbol)

    def _record_symbol(self, symbol: Dict[str, Any], forced_parent_id: Optional[int] = None) -> Optional[int]:
        """Record a single symbol."""
        try:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                return None

            # Skip local variables but don't count test-related ones in skipped count
            if symbol_str.startswith("local "):
                if not any(x in symbol_str for x in ["test", "mock", "fake"]):
                    self.skipped_local_symbols += 1
                return None

            # Extract name from symbol string
            name = symbol_str.split("/")[-1]  # Get the last part as name
            if name.endswith("."): 
                name = name[:-1]  # Remove trailing dot
            if name.startswith("`") and name.endswith("`"):
                name = name[1:-1]  # Remove backticks
            if "#" in name:
                base_name = name.split("#")[0]  # Remove Dart-specific suffixes
                # Keep getter/setter info if present
                if "<get>" in name or "<set>" in name:
                    accessor = name[name.index("<"):name.index(">") + 1]
                    name = f"{base_name}{accessor}"
                else:
                    name = base_name

            # Skip empty names
            if not name:
                return None

            kind = symbol.get("kind", "")
            signature = symbol.get("signature_documentation", {}).get("text", "")
            
            # Handle test files specially
            is_test_related = any(x in symbol_str for x in ["test", "mock", "fake", "_Fake", "Mock"])
            
            if is_test_related:
                # For test files, we create a test namespace to group test-related symbols
                test_namespace_id = self.symbol_id_map.get("test_namespace")
                if not test_namespace_id:
                    test_namespace_id = self.db.record_namespace(name="Tests")
                    self.symbol_id_map["test_namespace"] = test_namespace_id

            # Get parent info
            parent_id = forced_parent_id if forced_parent_id is not None else self._resolve_parent(symbol_str, kind, name)

            symbol_id = None

            # Map SCIP kinds to Sourcetrail records
            if kind == "TypeParameter":
                if parent_id:
                    # Create a type node for the parameter
                    type_node_id = self.db.record_type_node(name=name)
                    if type_node_id:
                        # Record the type parameter
                        symbol_id = self.db.record_type_parameter_node(name=name, parent_id=parent_id)
                        if symbol_id:
                            # Link type node to type parameter
                            self.db.record_ref_type_usage(symbol_id, type_node_id)
                else:
                    # Try to find the enclosing type by looking at the path
                    enclosing_type = symbol_str.split("/")[-2] if len(symbol_str.split("/")) > 1 else None
                    if enclosing_type:
                        class_id = self._find_class_by_name(enclosing_type)
                        if class_id:
                            # Create a type node for the parameter
                            type_node_id = self.db.record_type_node(name=name)
                            if type_node_id:
                                # Record the type parameter
                                symbol_id = self.db.record_type_parameter_node(name=name, parent_id=class_id)
                                if symbol_id:
                                    # Link type node to type parameter
                                    self.db.record_ref_type_usage(symbol_id, type_node_id)
                    if not symbol_id and is_test_related and test_namespace_id:
                        symbol_id = self.db.record_type_parameter_node(name=name, parent_id=test_namespace_id)
                    if not symbol_id:
                        self.missing_parent_symbols += 1
            elif kind == "Class" or (not kind and name.endswith("Class")):
                symbol_id = self.db.record_class(name=name)
                if is_test_related and test_namespace_id:
                    self.db.record_ref_usage(symbol_id, test_namespace_id)
            elif kind == "Interface":
                symbol_id = self.db.record_interface(name=name)
                if is_test_related and test_namespace_id:
                    self.db.record_ref_usage(symbol_id, test_namespace_id)
            elif kind == "Method" or kind == "Function" or (signature and signature.endswith("()")):
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                else:
                    if is_test_related and test_namespace_id:
                        symbol_id = self.db.record_method(name=name, parent_id=test_namespace_id)
                    else:
                        self.missing_parent_symbols += 1
                        symbol_id = self.db.record_function(name=name)
            elif kind == "Constructor":
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                else:
                    if is_test_related and test_namespace_id:
                        symbol_id = self.db.record_method(name=name, parent_id=test_namespace_id)
                    else:
                        # Try to find the class this constructor belongs to
                        class_name = name.split("#")[0] if "#" in name else name
                        class_id = self._find_class_by_name(class_name)
                        if class_id:
                            symbol_id = self.db.record_method(name=name, parent_id=class_id)
                        else:
                            self.missing_parent_symbols += 1
            elif kind == "Parameter":
                # For constructor parameters, try to find the constructor's class
                if "#<constructor>" in parent_symbol:
                    class_path = parent_symbol.split("#<constructor>")[0]
                    class_id = self._find_class_by_path(class_path)
                    if class_id:
                        parent_id = class_id

                if parent_id:
                    # Record parameter as a field of its parent
                    symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                    # Also record it as a local symbol to properly track scope
                    local_symbol_id = self.db.record_local_symbol()
                    if local_symbol_id:
                        self.db.record_local_symbol_location(local_symbol_id, parent_id)
                else:
                    if is_test_related and test_namespace_id:
                        symbol_id = self.db.record_field(name=name, parent_id=test_namespace_id)
                    else:
                        self.missing_parent_symbols += 1
            elif kind == "Field" or kind == "Property":
                # Handle getters and setters
                is_accessor = "<get>" in name or "<set>" in name
                if is_accessor:
                    base_name = name[:name.index("<")]
                else:
                    base_name = name

                if parent_id:
                    symbol_id = self.db.record_field(name=base_name, parent_id=parent_id)
                    if is_accessor:
                        # Record accessor as a method
                        accessor_id = self.db.record_method(name=name, parent_id=parent_id)
                        if accessor_id:
                            # Link accessor to field
                            self.db.record_ref_usage(accessor_id, symbol_id)
                else:
                    if is_test_related and test_namespace_id:
                        symbol_id = self.db.record_field(name=base_name, parent_id=test_namespace_id)
                    else:
                        self.missing_parent_symbols += 1
                        symbol_id = self.db.record_global_variable(name=base_name)
            elif kind == "Enum":
                # Create namespace for enum
                enum_namespace_id = self.db.record_namespace(name=name)
                if enum_namespace_id:
                    # Record the enum itself
                    symbol_id = self.db.record_enum(name=name)
                    if symbol_id:
                        # Link enum to its namespace
                        self.db.record_ref_usage(symbol_id, enum_namespace_id)
                        if is_test_related and test_namespace_id:
                            self.db.record_ref_usage(symbol_id, test_namespace_id)
            elif kind == "EnumConstant":
                if parent_id:
                    symbol_id = self.db.record_enum_constant(name=name, parent_id=parent_id)
                else:
                    # Try to find enum by name
                    enum_name = parent_symbol.split("/")[-1].split("#")[0]
                    enum_id = self._find_enum_by_name(enum_name)
                    if enum_id:
                        symbol_id = self.db.record_enum_constant(name=name, parent_id=enum_id)
                    elif is_test_related and test_namespace_id:
                        symbol_id = self.db.record_enum_constant(name=name, parent_id=test_namespace_id)
                    else:
                        self.missing_parent_symbols += 1
            elif kind == "TypeAlias" or kind == "TypeDef":
                symbol_id = self.db.record_typedef_node(name=name)
                if is_test_related and test_namespace_id:
                    self.db.record_ref_usage(symbol_id, test_namespace_id)
            elif kind == "Package" or kind == "Module":
                symbol_id = self.db.record_module(name=name)
            elif kind == "Namespace":
                symbol_id = self.db.record_namespace(name=name)

            if symbol_id:
                self.symbol_id_map[symbol_str] = symbol_id
                return symbol_id
            else:
                # Only track unregistered non-test symbols
                if not is_test_related and not symbol_str.startswith("local "):
                    self.unregistered_symbols.append(f"{kind} {name} ({symbol_str})")
                return None

        except Exception as e:
            # Only track errors for non-test symbols
            if not any(x in symbol_str for x in ["test", "mock", "fake"]):
                self.unregistered_symbols.append(f"{kind} {name} - Error: {str(e)}")
            return None

    def _resolve_parent(self, parent_symbol: str, kind: str, name: str) -> Optional[int]:
        """Resolve parent ID using various strategies."""
        # Direct lookup
        parent_id = self.symbol_id_map.get(parent_symbol)
        if parent_id:
            return parent_id

        # For constructors and their parameters, try to find the class
        if kind in ["Constructor", "Parameter"] and "#<constructor>" in parent_symbol:
            class_path = parent_symbol.split("#<constructor>")[0]
            class_id = self._find_class_by_path(class_path)
            if class_id:
                return class_id

        # Try to find enclosing class/interface
        if "/" in parent_symbol:
            enclosing_class = parent_symbol.split("/")[:-1]
            while enclosing_class:
                potential_parent = "/".join(enclosing_class)
                parent_id = self.symbol_id_map.get(potential_parent)
                if parent_id:
                    return parent_id
                enclosing_class.pop()

        # For parameters, try to find the method they belong to
        if kind == "Parameter" and "(" in parent_symbol:
            method_path = parent_symbol.split("(")[0]
            method_id = self.symbol_id_map.get(method_path)
            if method_id:
                return method_id

        return None

    def _find_class_by_path(self, class_path: str) -> Optional[int]:
        """Find a class ID by its path."""
        # Direct lookup
        class_id = self.symbol_id_map.get(class_path)
        if class_id:
            return class_id

        # Try without any suffixes
        base_path = class_path.split("#")[0]
        return self.symbol_id_map.get(base_path)

    def _find_class_by_name(self, class_name: str) -> Optional[int]:
        """Find a class ID by its name."""
        # Remove any Dart-specific suffixes
        if "#" in class_name:
            class_name = class_name.split("#")[0]
        if class_name.endswith("."):
            class_name = class_name[:-1]
        if class_name.startswith("`") and class_name.endswith("`"):
            class_name = class_name[1:-1]

        # Look through all symbols for matching class name
        for symbol_path, symbol_id in self.symbol_id_map.items():
            path_parts = symbol_path.split("/")
            if path_parts and class_name in path_parts[-1]:
                return symbol_id

        return None

    def _find_enum_by_name(self, enum_name: str) -> Optional[int]:
        """Find an enum ID by its name."""
        # Remove any Dart-specific suffixes
        if "#" in enum_name:
            enum_name = enum_name.split("#")[0]
        if enum_name.endswith("."):
            enum_name = enum_name[:-1]
        if enum_name.startswith("`") and enum_name.endswith("`"):
            enum_name = enum_name[1:-1]

        # Look through all symbols for matching enum name
        for symbol_path, symbol_id in self.symbol_id_map.items():
            path_parts = symbol_path.split("/")
            if path_parts and enum_name in path_parts[-1]:
                return symbol_id

        return None

    def _record_relationships(self, occurrences: List[Dict[str, Any]]) -> None:
        """Record relationships between symbols."""
        for occurrence in occurrences:
            try:
                symbol = occurrence.get("symbol", "")
                if not symbol or symbol.startswith("local "):
                    continue  # Skip local variable targets
                    
                symbol_id = self.symbol_id_map.get(symbol)
                if not symbol_id:
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
                        symbol_id,
                        file_id,
                        start_line,
                        start_col,
                        end_line,
                        end_col
                    )
                
                # Record relationships
                symbol_roles = occurrence.get("symbol_roles", 0)
                target = occurrence.get("target", "")
                if not target or target.startswith("local "):
                    continue  # Skip local variable targets
                    
                target_id = self.symbol_id_map.get(target)
                if not target_id:
                    continue
                    
                # Map SCIP symbol roles to Sourcetrail relationships
                try:
                    if symbol_roles & 0x2:  # Definition
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x4:  # Reference
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x8:  # Read
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x10:  # Write
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x20:  # Call
                        self.db.record_ref_call(symbol_id, target_id)
                    if symbol_roles & 0x40:  # Implementation
                        self.db.record_ref_inheritance(symbol_id, target_id)
                    if symbol_roles & 0x80:  # Override
                        self.db.record_ref_override(symbol_id, target_id)
                    if symbol_roles & 0x100:  # TypeDefinition
                        self.db.record_ref_type_usage(symbol_id, target_id)
                except Exception as e:
                    self.failed_relationships.append(f"{symbol} -> {target} (roles: {symbol_roles}) - Error: {str(e)}")
            except Exception as e:
                self.failed_relationships.append(f"Failed to process occurrence - Error: {str(e)}")