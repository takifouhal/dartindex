"""
Module for converting SCIP data to Sourcetrail database format.
"""

from pathlib import Path
from typing import Dict, Any, List
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
        
    def convert(self, scip_json: Dict[str, Any]) -> None:
        """Convert SCIP JSON data to Sourcetrail DB format.
        
        Args:
            scip_json: Dictionary containing SCIP index data
        """
        try:
            print("\nDEBUG: SCIP Data Overview:")
            print(f"Documents: {len(scip_json.get('documents', []))}")
            print(f"Symbols: {len(scip_json.get('symbols', []))}")
            print(f"Occurrences: {len(scip_json.get('occurrences', []))}")
            
            # Debug SCIP data structure
            print("\nDEBUG: SCIP Data Structure:")
            for key in scip_json.keys():
                print(f"Key: {key}")
                if isinstance(scip_json[key], list):
                    print(f"  Length: {len(scip_json[key])}")
                    if scip_json[key]:
                        print(f"  First item keys: {scip_json[key][0].keys() if isinstance(scip_json[key][0], dict) else 'not a dict'}")
            
            # 1. Record source files
            documents = scip_json.get("documents", [])
            print(f"\nDEBUG: First document structure: {documents[0] if documents else 'No documents'}")
            self._record_files(documents)
            
            # 2. Record symbols (classes, methods, fields)
            symbols = []
            # Check if symbols are nested in documents
            for doc in documents:
                doc_symbols = doc.get("symbols", [])
                print(f"\nDEBUG: Document {doc.get('relative_path')} has {len(doc_symbols)} symbols")
                symbols.extend(doc_symbols)
            
            print(f"\nDEBUG: Total symbols found in documents: {len(symbols)}")
            self._record_symbols(symbols)
            
            # 3. Record relationships
            occurrences = []
            # Check if occurrences are nested in documents
            for doc in documents:
                doc_occurrences = doc.get("occurrences", [])
                print(f"\nDEBUG: Document {doc.get('relative_path')} has {len(doc_occurrences)} occurrences")
                occurrences.extend(doc_occurrences)
            
            print(f"\nDEBUG: Total occurrences found in documents: {len(occurrences)}")
            self._record_relationships(occurrences)
            
            # 4. Commit and close
            self.db.commit()
            self.db.close()
            
            print("\nDEBUG: Sourcetrail Recording Summary:")
            print(f"Recorded Files: {len(self.file_id_map)}")
            print(f"Recorded Symbols: {len(self.symbol_id_map)}")
            
        except Exception as e:
            print(f"\nDEBUG: Error details: {str(e)}")
            self.db.close()
            raise e

    def _record_files(self, documents: List[Dict[str, Any]]) -> None:
        """Record source files in Sourcetrail DB."""
        print("\nDEBUG: Recording Files:")
        for doc in documents:
            file_path = Path(doc["relative_path"])
            print(f"Recording file: {file_path}")
            file_id = self.db.record_file(file_path)
            
            # Record language if available
            language = doc.get("language", "unknown")
            print(f"Language: {language}")
            self.db.record_file_language(file_id, language)
            self.file_id_map[str(file_path)] = file_id

    def _record_symbols(self, symbols: List[Dict[str, Any]]) -> None:
        """Record symbols in Sourcetrail DB."""
        print("\nDEBUG: Recording Symbols:")
        for symbol in symbols:
            symbol_id = None
            
            # Extract symbol info
            symbol_str = symbol.get("symbol", "")  # Get the full symbol string
            if not symbol_str or symbol_str.startswith("local "):
                continue  # Skip empty symbols and local variables
                
            # Extract name from symbol string
            name = symbol_str.split("/")[-1]  # Get the last part as name
            if name.endswith("."): 
                name = name[:-1]  # Remove trailing dot
            if name.startswith("`") and name.endswith("`"):
                name = name[1:-1]  # Remove backticks
            if "#" in name:
                name = name.split("#")[0]  # Remove Dart-specific suffixes
                
            kind = symbol.get("kind", "")
            signature = symbol.get("signature_documentation", {}).get("text", "")
            print(f"Processing symbol: {symbol_str} (kind: {kind})")
            
            # Map SCIP kinds to Sourcetrail records
            if kind == "Class" or (not kind and name.endswith("Class")):
                symbol_id = self.db.record_class(name=name)
            elif kind == "Interface":
                symbol_id = self.db.record_interface(name=name)
            elif kind == "Method" or kind == "Function" or (signature and signature.endswith("()")):
                parent_symbol = "/".join(symbol_str.split("/")[:-1])  # Get parent path
                parent_id = self.symbol_id_map.get(parent_symbol)
                print(f"Method parent: {parent_symbol} -> {parent_id}")
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                else:
                    symbol_id = self.db.record_function(name=name)
            elif kind == "Constructor":
                parent_symbol = "/".join(symbol_str.split("/")[:-1])
                parent_id = self.symbol_id_map.get(parent_symbol)
                print(f"Constructor parent: {parent_symbol} -> {parent_id}")
                if parent_id:
                    symbol_id = self.db.record_method(name=name, parent_id=parent_id)
            elif kind == "Field" or kind == "Property":
                parent_symbol = "/".join(symbol_str.split("/")[:-1])
                parent_id = self.symbol_id_map.get(parent_symbol)
                print(f"Field parent: {parent_symbol} -> {parent_id}")
                if parent_id:
                    symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                else:
                    symbol_id = self.db.record_global_variable(name=name)
            elif kind == "Enum":
                symbol_id = self.db.record_enum(name=name)
            elif kind == "EnumConstant":
                parent_symbol = "/".join(symbol_str.split("/")[:-1])
                parent_id = self.symbol_id_map.get(parent_symbol)
                if parent_id:
                    symbol_id = self.db.record_enum_constant(name=name, parent_id=parent_id)
            elif kind == "TypeAlias" or kind == "TypeDef":
                symbol_id = self.db.record_typedef_node(name=name)
            elif kind == "TypeParameter":
                symbol_id = self.db.record_type_parameter_node(name=name)
            elif kind == "Package" or kind == "Module" or kind == "Namespace":
                symbol_id = self.db.record_namespace(name=name)
                    
            if symbol_id:
                print(f"Recorded symbol {name} with ID: {symbol_id}")
                self.symbol_id_map[symbol_str] = symbol_id

    def _record_relationships(self, occurrences: List[Dict[str, Any]]) -> None:
        """Record relationships between symbols."""
        print("\nDEBUG: Recording Relationships:")
        for occurrence in occurrences:
            symbol = occurrence.get("symbol", "")
            if not symbol or symbol.startswith("local "):
                continue  # Skip local variables
                
            symbol_id = self.symbol_id_map.get(symbol)
            if not symbol_id:
                print(f"Warning: Symbol not found for relationship: {symbol}")
                continue
                
            # Record symbol location in source
            file_path = occurrence.get("file_path", "")
            file_id = self.file_id_map.get(file_path)
            range_data = occurrence.get("range", {})
            
            if file_id and range_data:
                print(f"Recording location for symbol {symbol_id} in file {file_id}")
                # Handle different range formats
                if isinstance(range_data, list):
                    # [start_line, start_col, end_line, end_col]
                    start_line, start_col, end_line = range_data[:3]
                    end_col = range_data[3] if len(range_data) > 3 else start_col
                else:
                    # {start: {line, character}, end: {line, character}}
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
                
            print(f"Recording relationship with roles {symbol_roles} from {symbol_id} to {target_id}")
            
            # Map SCIP symbol roles to Sourcetrail relationships
            if symbol_roles & 0x2:  # Definition
                self.db.record_ref_usage(symbol_id, target_id)  # No direct definition in API
            if symbol_roles & 0x4:  # Reference
                self.db.record_ref_usage(symbol_id, target_id)
            if symbol_roles & 0x8:  # Read
                self.db.record_ref_usage(symbol_id, target_id)
            if symbol_roles & 0x10:  # Write
                self.db.record_ref_usage(symbol_id, target_id)
            if symbol_roles & 0x20:  # Call
                self.db.record_ref_call(symbol_id, target_id)
            if symbol_roles & 0x40:  # Implementation
                self.db.record_ref_inheritance(symbol_id, target_id)  # Use inheritance for implementation
            if symbol_roles & 0x80:  # Type Reference
                self.db.record_ref_type_usage(symbol_id, target_id)
            if symbol_roles & 0x100:  # Inheritance
                self.db.record_ref_inheritance(symbol_id, target_id)
            if symbol_roles & 0x200:  # Override
                self.db.record_ref_override(symbol_id, target_id)