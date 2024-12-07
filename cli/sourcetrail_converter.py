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
        
    def convert(self, scip_json: Dict[str, Any]) -> None:
        """Convert SCIP JSON data to Sourcetrail DB format.
        
        Args:
            scip_json: Dictionary containing SCIP index data
        """
        try:
            # 1. Record source files
            self._record_files(scip_json.get("documents", []))
            
            # 2. Record symbols (classes, methods, fields)
            self._record_symbols(scip_json.get("symbols", []))
            
            # 3. Record relationships
            self._record_relationships(scip_json.get("occurrences", []))
            
            # 4. Commit and close
            self.db.commit()
            self.db.close()
            
        except Exception as e:
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

    def _record_symbols(self, symbols: List[Dict[str, Any]]) -> None:
        """Record symbols in Sourcetrail DB."""
        for symbol in symbols:
            symbol_id = None
            
            # Map SCIP symbol kinds to Sourcetrail records
            kind = symbol.get("kind")
            name = symbol.get("name", "")
            
            if kind == "class":
                symbol_id = self.db.record_class(
                    name=name,
                    prefix="class",
                    postfix=":")
            elif kind == "method":
                parent_symbol = symbol.get("parent")
                parent_id = self.symbol_id_map.get(parent_symbol)
                symbol_id = self.db.record_method(
                    name=name,
                    parent_id=parent_id)
            elif kind == "field":
                parent_symbol = symbol.get("parent")
                parent_id = self.symbol_id_map.get(parent_symbol)
                symbol_id = self.db.record_field(
                    name=name,
                    parent_id=parent_id)
                    
            if symbol_id:
                self.symbol_id_map[symbol["id"]] = symbol_id

    def _record_relationships(self, occurrences: List[Dict[str, Any]]) -> None:
        """Record relationships between symbols."""
        for occurrence in occurrences:
            symbol_id = self.symbol_id_map.get(occurrence["symbol"])
            if not symbol_id:
                continue
                
            # Record symbol location in source
            file_id = occurrence.get("file_id")
            range = occurrence.get("range", {})
            if file_id and range:
                self.db.record_symbol_location(
                    symbol_id,
                    file_id,
                    range["start"]["line"],
                    range["start"]["character"],
                    range["end"]["line"], 
                    range["end"]["character"]
                )
            
            # Record relationships
            role = occurrence.get("role", "")
            if role == "reference":
                target_id = self.symbol_id_map.get(occurrence.get("target"))
                if target_id:
                    self.db.record_ref_usage(symbol_id, target_id) 