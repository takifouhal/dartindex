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
        for symbol in symbols:
            symbol_id = None
            
            # Extract symbol info
            symbol_str = symbol.get("symbol", "")  # Get the full symbol string
            if not symbol_str or symbol_str.startswith("local "):
                self.skipped_local_symbols += 1
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
            
            # Map SCIP kinds to Sourcetrail records
            try:
                if kind == "Class" or (not kind and name.endswith("Class")):
                    symbol_id = self.db.record_class(name=name)
                elif kind == "Interface":
                    symbol_id = self.db.record_interface(name=name)
                elif kind == "Method" or kind == "Function" or (signature and signature.endswith("()")):
                    parent_symbol = "/".join(symbol_str.split("/")[:-1])  # Get parent path
                    parent_id = self.symbol_id_map.get(parent_symbol)
                    if parent_id:
                        symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                    else:
                        self.missing_parent_symbols += 1
                        symbol_id = self.db.record_function(name=name)
                elif kind == "Constructor":
                    parent_symbol = "/".join(symbol_str.split("/")[:-1])
                    parent_id = self.symbol_id_map.get(parent_symbol)
                    if parent_id:
                        symbol_id = self.db.record_method(name=name, parent_id=parent_id)
                    else:
                        self.missing_parent_symbols += 1
                elif kind == "Field" or kind == "Property":
                    parent_symbol = "/".join(symbol_str.split("/")[:-1])
                    parent_id = self.symbol_id_map.get(parent_symbol)
                    if parent_id:
                        symbol_id = self.db.record_field(name=name, parent_id=parent_id)
                    else:
                        self.missing_parent_symbols += 1
                        symbol_id = self.db.record_global_variable(name=name)
                elif kind == "Enum":
                    symbol_id = self.db.record_enum(name=name)
                elif kind == "EnumConstant":
                    parent_symbol = "/".join(symbol_str.split("/")[:-1])
                    parent_id = self.symbol_id_map.get(parent_symbol)
                    if parent_id:
                        symbol_id = self.db.record_enum_constant(name=name, parent_id=parent_id)
                    else:
                        self.missing_parent_symbols += 1

                if symbol_id:
                    self.symbol_id_map[symbol_str] = symbol_id
                else:
                    self.unregistered_symbols.append(f"{kind} {name} ({symbol_str})")
            except Exception as e:
                self.unregistered_symbols.append(f"{kind} {name} - Error: {str(e)}")

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