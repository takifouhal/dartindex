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
            print(f"Skipped local symbols: {self.skipped_local_symbols}")
            if self.missing_parent_symbols > 0:
                print(f"Warning: {self.missing_parent_symbols} symbols had missing parents")
            
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

    def _process_symbol(self, symbol):
        """Process a single symbol and record it in the database."""
        symbol_str = self._get_safe(symbol, "symbol", "")
        if not symbol_str:
            return None
            
        # Extract name from symbol string
        name = symbol_str.split("/")[-1] if "/" in symbol_str else symbol_str
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
        
        kind = self._get_safe(symbol, "kind", "")
        
        if kind == "Class" or kind == "Interface" or (not kind and name.endswith("Class")):
            # Record the class/interface
            symbol_id = self.db.record_class(name=name)
            
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
            
            return symbol_id
            
        elif kind == "Method" or (self._get_signature(symbol) and self._get_signature(symbol).endswith("()")):
            parent_id = self._get_safe(symbol, "parent_id")
            if parent_id:
                # For class methods
                is_getter = "<get>" in symbol_str
                is_setter = "<set>" in symbol_str
                is_operator = "operator" in name.lower()
                
                if is_getter or is_setter:
                    # Record accessor method
                    accessor_type = "get" if is_getter else "set"
                    base_name = name[:name.index("<")]
                    # First record the field
                    field_id = self.db.record_field(name=base_name, parent_id=parent_id)
                    # Then record the accessor method
                    symbol_id = self.db.record_method(name=f"{base_name}.{accessor_type}", parent_id=parent_id)
                    # Link accessor to field
                    if field_id and symbol_id:
                        self.db.record_ref_usage(symbol_id, field_id)
                        self._record_location_data(symbol_id, symbol)
                        
                elif is_operator:
                    # Record operator method
                    symbol_id = self.db.record_method(name=f"operator {name}", parent_id=parent_id)
                    self.db.record_ref_member(parent_id, symbol_id)
                    self._record_location_data(symbol_id, symbol)
                    
                else:
                    # Regular method
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                    self.db.record_ref_member(parent_id, symbol_id)
                    
                    # Record location data
                    range_data = self._record_location_data(symbol_id, symbol)
                    if range_data:
                        # Record signature location if we have a signature
                        signature = self._get_signature(symbol)
                        if signature:
                            file_id = self.file_id_map.get(self._get_safe(symbol, "document_path", ""))
                            if file_id:
                                self.db.record_symbol_signature_location(
                                    symbol_id,
                                    file_id,
                                    range_data["start_line"],
                                    range_data["start_col"],
                                    range_data["end_line"],
                                    range_data["end_col"]
                                )
                    
                    # Record method call relationships
                    refs = self._get_safe(symbol, "references", [])
                    if isinstance(refs, list):
                        for ref in refs:
                            if isinstance(ref, dict) and ref.get("type") == "call":
                                target_id = self.symbol_id_map.get(ref.get("target"))
                                if target_id:
                                    self.db.record_ref_call(symbol_id, target_id)
                
                return symbol_id
                
            else:
                # For top-level functions
                file_path = None
                docs = self._get_safe(symbol, "documents", [])
                if isinstance(docs, list):
                    for doc in docs:
                        if isinstance(doc, dict) and doc.get("relative_path"):
                            file_path = doc["relative_path"]
                            break
                
                if file_path:
                    namespace_path = os.path.dirname(file_path).replace("/", ".")
                    if namespace_path:
                        namespace_id = self.symbol_id_map.get(namespace_path)
                        if not namespace_id:
                            namespace_id = self.db.record_namespace(name=namespace_path)
                            self.symbol_id_map[namespace_path] = namespace_id
                        symbol_id = self.db.record_method(name=name, parent_id=namespace_id)
                        self.db.record_ref_member(namespace_id, symbol_id)
                        return symbol_id
                    else:
                        return self.db.record_function(name=name)
                else:
                    return self.db.record_function(name=name)

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
                        self.stats["namespaces"] += 1
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
                    if "<get>" in name or "<set>" in name:
                        accessor = name[name.index("<"):name.index(">") + 1]
                        name = f"{base_name}{accessor}"
                    elif "<constructor>" in name:
                        name = base_name
                    else:
                        name = base_name
                
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

                # Extract relationship context
                is_mixin = "with" in occurrence.get("syntax", "").lower()
                is_interface = "implements" in occurrence.get("syntax", "").lower()
                is_superclass = "extends" in occurrence.get("syntax", "").lower()
                
                # Map SCIP symbol roles to Sourcetrail relationships
                try:
                    # Basic references and definitions
                    if symbol_roles & 0x2:  # Definition
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x4:  # Reference
                        self.db.record_ref_usage(symbol_id, target_id)
                        
                    # Variable access
                    if symbol_roles & 0x8:  # Read
                        self.db.record_ref_usage(symbol_id, target_id)
                    if symbol_roles & 0x10:  # Write
                        self.db.record_ref_usage(symbol_id, target_id)
                        
                    # Method calls and implementations
                    if symbol_roles & 0x20:  # Call
                        self.db.record_ref_call(symbol_id, target_id)
                    if symbol_roles & 0x40:  # Implementation
                        if is_interface:
                            # Interface implementation
                            self.db.record_ref_implementation(symbol_id, target_id)
                        elif is_mixin:
                            # Mixin usage
                            self.db.record_ref_usage(symbol_id, target_id)
                            self.db.record_ref_implementation(symbol_id, target_id)
                        else:
                            # Regular implementation
                            self.db.record_ref_inheritance(symbol_id, target_id)
                            
                    # Inheritance and overrides
                    if symbol_roles & 0x80:  # Override
                        if is_superclass:
                            # Superclass method override
                            self.db.record_ref_override(symbol_id, target_id)
                            self.db.record_ref_inheritance(symbol_id, target_id)
                        else:
                            # Interface or mixin method override
                            self.db.record_ref_override(symbol_id, target_id)
                            
                    # Type relationships
                    if symbol_roles & 0x100:  # TypeDefinition
                        if is_interface:
                            # Interface usage
                            self.db.record_ref_implementation(symbol_id, target_id)
                        elif is_mixin:
                            # Mixin usage
                            self.db.record_ref_usage(symbol_id, target_id)
                        else:
                            # Regular type usage
                            self.db.record_ref_type_usage(symbol_id, target_id)
                            
                    # Additional Dart-specific relationships
                    if symbol_roles & 0x200:  # Type parameter (generic)
                        self.db.record_ref_type_usage(symbol_id, target_id)
                    if symbol_roles & 0x400:  # Type argument
                        self.db.record_ref_type_usage(symbol_id, target_id)
                    if symbol_roles & 0x800:  # Type bound
                        self.db.record_ref_type_usage(symbol_id, target_id)
                        
                except Exception as e:
                    self.failed_relationships.append(f"{symbol} -> {target} (roles: {symbol_roles}) - Error: {str(e)}")
            except Exception as e:
                self.failed_relationships.append(f"Failed to process occurrence - Error: {str(e)}")