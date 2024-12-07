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
        # First pass: record all classes and build maps
        class_map = {}  # Map class paths to their IDs
        private_class_map = {}  # Map for private classes
        generated_class_map = {}  # Map for generated classes (freezed, etc.)
        
        # First pass: record classes and build maps
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            if kind == "Class" or kind == "Interface":
                # Record the class/interface
                symbol_id = self._record_symbol(symbol)
                if symbol_id:
                    # Store both full path and simple path
                    full_path = symbol_str
                    simple_path = symbol_str.split("#")[0] if "#" in symbol_str else symbol_str
                    class_name = simple_path.split("/")[-1]
                    
                    # Store in appropriate map
                    if class_name.startswith("_$") or ".freezed." in simple_path:
                        # Generated class
                        generated_class_map[full_path] = symbol_id
                        generated_class_map[simple_path] = symbol_id
                        # Also store without _$ prefix
                        if class_name.startswith("_$"):
                            base_name = class_name[2:]
                            base_path = "/".join(simple_path.split("/")[:-1] + [base_name])
                            generated_class_map[base_path] = symbol_id
                    elif class_name.startswith("_"):
                        # Private class
                        private_class_map[full_path] = symbol_id
                        private_class_map[simple_path] = symbol_id
                        # Also store without _ prefix
                        base_name = class_name[1:]
                        base_path = "/".join(simple_path.split("/")[:-1] + [base_name])
                        private_class_map[base_path] = symbol_id
                    else:
                        # Regular class
                        class_map[full_path] = symbol_id
                        class_map[simple_path] = symbol_id
            elif kind in ["Enum", "Package", "Module", "Namespace", "TypeAlias", "TypeDef"]:
                self._record_symbol(symbol)

        # Second pass: record methods and fields
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            if kind in ["Method", "Function", "Constructor", "Field", "Property", "EnumConstant"]:
                self._record_symbol(symbol, class_map=class_map, private_class_map=private_class_map, generated_class_map=generated_class_map)

        # Third pass: record remaining symbols
        for symbol in symbols:
            symbol_str = symbol.get("symbol", "")
            if not symbol_str:
                continue

            kind = symbol.get("kind", "")
            if kind not in ["Class", "Interface", "Enum", "Package", "Module", "Namespace", "TypeAlias", "TypeDef", 
                          "Method", "Function", "Constructor", "Field", "Property", "EnumConstant"]:
                self._record_symbol(symbol, class_map=class_map, private_class_map=private_class_map, generated_class_map=generated_class_map)

    def _record_symbol(self, symbol: Dict[str, Any], forced_parent_id: Optional[int] = None, 
                      class_map: Optional[Dict[str, int]] = None, 
                      private_class_map: Optional[Dict[str, int]] = None,
                      generated_class_map: Optional[Dict[str, int]] = None) -> Optional[int]:
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
                elif "<constructor>" in name:
                    # For constructors, use the class name
                    name = base_name
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
            parent_id = forced_parent_id
            if parent_id is None:
                parent_path = "/".join(symbol_str.split("/")[:-1])
                simple_path = parent_path.split("#")[0] if "#" in parent_path else parent_path
                
                # Try to find parent in appropriate map
                if class_map is not None:
                    parent_id = class_map.get(simple_path)
                if parent_id is None and private_class_map is not None:
                    parent_id = private_class_map.get(simple_path)
                if parent_id is None and generated_class_map is not None:
                    parent_id = generated_class_map.get(simple_path)

                # If still no parent found, try to extract class name from constructor
                if parent_id is None and "<constructor>" in symbol_str:
                    class_path = symbol_str.split("#<constructor>")[0]
                    class_name = class_path.split("/")[-1]
                    if class_map is not None:
                        parent_id = class_map.get(class_path)
                    if parent_id is None and private_class_map is not None:
                        parent_id = private_class_map.get(class_path)
                    if parent_id is None and generated_class_map is not None:
                        parent_id = generated_class_map.get(class_path)

            symbol_id = None

            # Map SCIP kinds to Sourcetrail records
            if kind == "Constructor" or "<constructor>" in symbol_str:
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                else:
                    # Try to find or create the parent class
                    class_path = symbol_str.split("#<constructor>")[0] if "#<constructor>" in symbol_str else symbol_str.split("#")[0]
                    class_name = class_path.split("/")[-1]
                    
                    # Create the class if it doesn't exist
                    class_id = None
                    if class_map is not None:
                        class_id = class_map.get(class_path)
                    if class_id is None and private_class_map is not None:
                        class_id = private_class_map.get(class_path)
                    if class_id is None and generated_class_map is not None:
                        class_id = generated_class_map.get(class_path)
                    
                    if class_id is None:
                        # Create the class
                        class_id = self.db.record_class(name=class_name)
                        if class_map is not None:
                            class_map[class_path] = class_id
                    
                    if class_id:
                        symbol_id = self.db.record_method(name=name, parent_id=class_id)
                    else:
                        self.missing_parent_symbols += 1

            elif kind == "Class" or kind == "Interface" or (not kind and name.endswith("Class")):
                symbol_id = self.db.record_class(name=name)
                if is_test_related and test_namespace_id:
                    self.db.record_ref_usage(symbol_id, test_namespace_id)
            elif kind == "Method" or kind == "Function" or (signature and signature.endswith("()")):
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                else:
                    # For top-level functions
                    symbol_id = self.db.record_function(name=name)
            elif kind == "TypeParameter":
                # Handle type parameters (generics)
                if parent_id:
                    symbol_id = self.db.record_type_parameter_node(name=name, parent_id=parent_id)
                else:
                    # Try to find parent from the symbol path
                    type_param_parts = symbol_str.split("#")
                    if len(type_param_parts) > 1:
                        parent_path = type_param_parts[0]
                        # Look for parent in all maps
                        parent_id = None
                        if class_map:
                            parent_id = class_map.get(parent_path)
                        if parent_id is None and private_class_map:
                            parent_id = private_class_map.get(parent_path)
                        if parent_id is None and generated_class_map:
                            parent_id = generated_class_map.get(parent_path)
                        
                        if parent_id:
                            symbol_id = self.db.record_type_parameter_node(name=name, parent_id=parent_id)
                        else:
                            # Create a type alias for the generic type
                            symbol_id = self.db.record_typedef_node(name=name)
                    else:
                        # Standalone type parameter
                        symbol_id = self.db.record_typedef_node(name=name)
            elif kind == "Variable" or kind == "Field" or kind == "Property":
                if parent_id:
                    # For class members
                    symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                else:
                    # For top-level variables, try to find or create a namespace
                    file_path = None
                    for doc in symbol.get("documents", []):
                        if doc.get("relative_path"):
                            file_path = doc["relative_path"]
                            break
                    
                    if file_path:
                        # Create a namespace based on the file path
                        namespace_path = os.path.dirname(file_path).replace("/", ".")
                        if namespace_path:
                            namespace_id = self.symbol_id_map.get(namespace_path)
                            if not namespace_id:
                                namespace_id = self.db.record_namespace(name=namespace_path)
                                self.symbol_id_map[namespace_path] = namespace_id
                            symbol_id = self.db.record_field(name=name, parent_id=namespace_id)
                        else:
                            # Global variable
                            symbol_id = self.db.record_global_variable(name=name)
                    else:
                        # Global variable
                        symbol_id = self.db.record_global_variable(name=name)
            elif kind == "Enum":
                symbol_id = self.db.record_enum(name=name)
            elif kind == "EnumConstant":
                if parent_id:
                    symbol_id = self.db.record_enum_constant(name=name, parent_id=parent_id)
                else:
                    self.missing_parent_symbols += 1
            elif kind in ["Module", "Package", "Namespace"]:
                symbol_id = self.db.record_namespace(name=name)
            elif kind == "TypeAlias" or kind == "TypeDef":
                symbol_id = self.db.record_typedef_node(name=name)
            else:
                # For unknown kinds, try to infer from the name and context
                if name.endswith("Type") or name.startswith("Type"):
                    symbol_id = self.db.record_typedef_node(name=name)
                elif name.endswith("Enum"):
                    symbol_id = self.db.record_enum(name=name)
                elif name.endswith("Const"):
                    symbol_id = self.db.record_global_variable(name=name)
                elif parent_id:
                    # If we have a parent, assume it's a member
                    symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                else:
                    # Default to global variable
                    symbol_id = self.db.record_global_variable(name=name)

            if symbol_id:
                self.symbol_id_map[symbol_str] = symbol_id
            else:
                self.unregistered_symbols.append(f"{kind} {name} ({symbol_str})")

            return symbol_id

        except Exception as e:
            print(f"Error recording symbol {symbol_str}: {str(e)}")
            self.unregistered_symbols.append(f"{kind} {name} ({symbol_str})")
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