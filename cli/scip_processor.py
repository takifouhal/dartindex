"""
SCIP data processing functionality.
This module handles the processing and formatting of SCIP index data.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from google.protobuf import text_format
from google.protobuf.json_format import MessageToDict
from numbat import SourcetrailDB
from cli import scip_pb2
import logging

class SCIPProcessor:
    """Processes SCIP (Source Code Intelligence Protocol) index data."""
    
    def __init__(self):
        self.db = None
        self.file_id_map = {}  # Maps file paths to their Sourcetrail IDs
        self.symbol_id_map = {}  # Maps SCIP symbols to their Sourcetrail IDs
        self.class_id_map = {}  # Maps class paths to their Sourcetrail IDs
        
        # Setup logging with more detailed format
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("SCIPProcessor")
        
    def process_data(self, scip_data: bytes, db_path: Optional[Path] = None, format_type: str = "sourcetrail", symbols_only: bool = False) -> Optional[str]:
        """Process SCIP binary data into the requested format."""
        try:
            # Parse the SCIP data
            index = scip_pb2.Index()
            index.ParseFromString(scip_data)
            
            self.logger.info(f"Processing SCIP data for project: {index.metadata.project_root}")
            self.logger.info(f"Tool info: {index.metadata.tool_info.name} {index.metadata.tool_info.version}")
            self.logger.info(f"Format type: {format_type}")
            
            if format_type == "sourcetrail":
                if db_path is None:
                    raise ValueError("db_path is required for sourcetrail format")
                self._process_to_sourcetrail(index, db_path, symbols_only)
                return None
            else:
                format_handlers = {
                    "json": self._format_json,
                    "text": lambda idx: text_format.MessageToString(idx, as_utf8=True),
                    "summary": self._format_summary
                }
                if format_type not in format_handlers:
                    raise ValueError(f"Unsupported format type: {format_type}")
                return format_handlers[format_type](index)
                
        except Exception as e:
            self.logger.error(f"Failed to process SCIP data: {str(e)}", exc_info=True)
            raise

    def _process_to_sourcetrail(self, index: scip_pb2.Index, db_path: Path, symbols_only: bool = False) -> None:
        """Convert SCIP index to Sourcetrail database."""
        self.logger.info(f"Processing to Sourcetrail database at: {db_path}")
        self.db = SourcetrailDB.open(db_path, clear=True)
        
        try:
            doc_count = len(index.documents)
            self.logger.info(f"Processing {doc_count} documents")
            
            # Process files first
            self._process_documents(index.documents)
            self.logger.info(f"Processed {len(self.file_id_map)} files")
            
            # Process symbols and their relationships
            self._process_symbols(index.documents)
            self.logger.info(f"Processed {len(self.symbol_id_map)} symbols")
            
            # Process occurrences and locations if not symbols_only
            if not symbols_only:
                self._process_occurrences(index.documents)
            
            self.db.commit()
            self.logger.info("Successfully committed all changes to database")
            
        except Exception as e:
            self.logger.error(f"Failed to process to Sourcetrail: {str(e)}", exc_info=True)
            raise
        finally:
            self.db.close()
            self.logger.info("Database connection closed")

    def _process_documents(self, documents: List[scip_pb2.Document]) -> None:
        """Record source files in the database."""
        try:
            for doc in documents:
                if not doc.relative_path:
                    continue  # Skip documents without paths
                    
                self.logger.debug(f"Processing document: {doc.relative_path}")
                file_path = Path(doc.relative_path)
                file_id = self.db.record_file(file_path)
                self.logger.debug(f"Recorded file ID: {file_id}")
                
                if hasattr(doc, 'language'):
                    self.db.record_file_language(file_id, doc.language.lower())
                    self.logger.debug(f"Recorded language: {doc.language.lower()}")
                    
                self.file_id_map[doc.relative_path] = file_id
        except Exception as e:
            self.logger.error(f"Error processing document: {str(e)}")
            raise ValueError(f"Error processing document: {str(e)}")

    def _process_symbols(self, documents: List[scip_pb2.Document]) -> None:
        """Process and record symbols and their relationships."""
        for doc in documents:
            # First pass: Record all symbols
            for symbol in doc.symbols:
                symbol_id = self._record_symbol(symbol)
                
                # Process relationships
                if hasattr(symbol, 'relationships'):
                    for rel in symbol.relationships:
                        self._process_relationship(symbol_id, rel)
            
            # Process occurrences
            for occurrence in doc.occurrences:
                if occurrence.symbol in self.symbol_id_map:
                    self._process_occurrence(occurrence, self.symbol_id_map[occurrence.symbol])

    def _process_relationship(self, symbol_id: int, rel) -> None:
        """Process a single relationship between symbols."""
        # Skip if either symbol is not in the map
        if not symbol_id or rel.symbol not in self.symbol_id_map:
            return
            
        target_id = self.symbol_id_map[rel.symbol]
        # Skip if target_id is None
        if not target_id:
            return
            
        relationship_map = {
            'is_reference': self.db.record_ref_usage,
            'is_implementation': self.db.record_ref_override,
            'is_type_definition': self.db.record_ref_type_usage,
            'is_import': self.db.record_ref_import
        }
        
        for rel_type, record_func in relationship_map.items():
            if getattr(rel, rel_type, False):
                record_func(symbol_id, target_id)

    def _get_location_info(self, occurrence: scip_pb2.Occurrence) -> Optional[tuple]:
        """Extract location information from an occurrence."""
        doc_path = occurrence.document_id if hasattr(occurrence, 'document_id') else None
        if not doc_path or doc_path not in self.file_id_map:
            return None
            
        file_id = self.file_id_map[doc_path]
        start_line = occurrence.range[0] + 1
        start_col = occurrence.range[1] + 1
        end_line = occurrence.range[2] + 1 if len(occurrence.range) > 3 else start_line
        end_col = occurrence.range[3] + 1 if len(occurrence.range) > 3 else occurrence.range[2] + 1
        
        return (file_id, start_line, start_col, end_line, end_col)

    def _handle_definition(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle symbol definition."""
        loc_info = self._get_location_info(occurrence)
        if not loc_info:
            return
            
        try:
            self.db.record_symbol_location(
                symbol_id=symbol_id,
                file_id=loc_info[0],
                start_line=loc_info[1],
                start_column=loc_info[2],
                end_line=loc_info[3],
                end_column=loc_info[4]
            )
        except Exception as e:
            self.logger.warning(f"Failed to record symbol location: {str(e)}")

    def _handle_import(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle symbol import."""
        # Record import relationship
        if occurrence.symbol in self.symbol_id_map:
            target_id = self.symbol_id_map[occurrence.symbol]
            self.db.record_ref_import(symbol_id, target_id)

    def _handle_write_access(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle write access to symbol."""
        # Record usage relationship
        self.db.record_ref_usage(symbol_id, symbol_id)

    def _handle_read_access(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle read access to symbol."""
        # Record usage and potential method call
        if "#" in occurrence.symbol and (
            occurrence.symbol.endswith("().") or 
            occurrence.symbol.endswith(".")
        ):
            if occurrence.symbol in self.symbol_id_map:
                target_id = self.symbol_id_map[occurrence.symbol]
                self.db.record_ref_call(symbol_id, target_id)
                
                # Record call location
                self.db.record_reference_location(
                    symbol_id,
                    file_id,
                    start_line + 1,
                    start_col + 1,
                    end_line + 1,
                    end_col + 1
                )
        else:
            self.db.record_ref_usage(symbol_id, symbol_id)

    def _handle_container(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle container symbol (class, interface, etc)."""
        loc_info = self._get_location_info(occurrence)
        if not loc_info:
            return
            
        try:
            self.db.record_symbol_scope_location(
                symbol_id=symbol_id,
                file_id=loc_info[0],
                start_line=loc_info[1],
                start_column=1,  # Container scope starts at beginning of line
                end_line=loc_info[3],
                end_column=loc_info[4]
            )
        except Exception as e:
            self.logger.warning(f"Failed to record scope location: {str(e)}")

    def _handle_type_usage(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Handle type usage."""
        # Record type relationship
        if occurrence.symbol in self.symbol_id_map:
            target_id = self.symbol_id_map[occurrence.symbol]
            self.db.record_ref_type_usage(symbol_id, target_id)

    def _process_occurrences(self, documents: List[scip_pb2.Document]) -> None:
        """Process symbol occurrences and their locations."""
        for doc in documents:
            if not doc.relative_path or doc.relative_path not in self.file_id_map:
                continue  # Skip if we can't find the document
                
            file_id = self.file_id_map[doc.relative_path]
            
            for occurrence in doc.occurrences:
                if occurrence.symbol not in self.symbol_id_map:
                    continue  # Skip if we can't find the symbol
                    
                symbol_id = self.symbol_id_map[occurrence.symbol]
                
                try:
                    # Record the symbol location
                    start_line = occurrence.range[0]
                    start_col = occurrence.range[1]
                    end_line = occurrence.range[2] if len(occurrence.range) > 3 else start_line
                    end_col = occurrence.range[3] if len(occurrence.range) > 3 else occurrence.range[2]
                    
                    self.db.record_symbol_location(
                        symbol_id=symbol_id,
                        file_id=file_id,
                        start_line=start_line + 1,  # Convert to 1-based indexing
                        start_column=start_col + 1,
                        end_line=end_line + 1,
                        end_column=end_col + 1
                    )
                    
                    # Record scope if this is a container
                    if occurrence.symbol_roles & 0x10:  # Container
                        self.db.record_symbol_scope_location(
                            symbol_id=symbol_id,
                            file_id=file_id,
                            start_line=start_line + 1,
                            start_column=1,  # Scope starts at beginning of line
                            end_line=end_line + 1,
                            end_column=end_col + 1
                        )
                    
                    # Handle method calls
                    if "#" in occurrence.symbol and (
                        occurrence.symbol.endswith("().") or 
                        occurrence.symbol.endswith(".") or 
                        (occurrence.symbol_roles & 0x8)  # ReadAccess often indicates method call
                    ):
                        # Find the target method symbol
                        target_symbol = occurrence.symbol
                        if target_symbol in self.symbol_id_map:
                            target_id = self.symbol_id_map[target_symbol]
                            self.db.record_ref_call(symbol_id, target_id)
                            
                            # Record call location
                            self.db.record_reference_location(
                                symbol_id,
                                file_id,
                                start_line + 1,
                                start_col + 1,
                                end_line + 1,
                                end_col + 1
                            )
                except Exception as e:
                    print(f"Warning: Failed to process occurrence: {str(e)}")

    def _normalize_path(self, path: str) -> str:
        """Normalize a symbol path to ensure consistent lookup."""
        # Remove any trailing dots, hashes, or slashes
        path = path.rstrip('.#/')
        # Remove any backticks
        path = path.replace('`', '')
        return path

    def _record_symbol(self, symbol: scip_pb2.SymbolInformation) -> int:
        """Record a symbol in the database."""
        if symbol.symbol in self.symbol_id_map:
            return self.symbol_id_map[symbol.symbol]
            
        # Map SCIP symbol kinds to Sourcetrail node types
        kind = scip_pb2.SymbolInformation.Kind.Name(symbol.kind)
        
        # Extract symbol components
        name = ""
        parent_id = None
        prefix = ""
        postfix = ""
        
        self.logger.debug(f"Processing symbol: {symbol.symbol}")
        
        # Parse symbol path for parent relationship
        if "/" in symbol.symbol:
            parts = symbol.symbol.split("/")
            
            # Get the parent path without the last component
            parent_path = "/".join(parts[:-1])
            last_part = parts[-1].strip("`")
            
            # Try to find parent ID
            if "#" in last_part:
                # This is a class member (method/field)
                class_name = last_part.split("#")[0]
                class_path = f"{parent_path}/{class_name}"
                normalized_class_path = self._normalize_path(class_path)
                
                # First try class_id_map, then fall back to symbol_id_map
                parent_id = self.class_id_map.get(normalized_class_path)
                if parent_id is None:
                    # Try alternate path formats
                    alt_path = f"{normalized_class_path}#"
                    parent_id = self.class_id_map.get(alt_path)
                    
                self.logger.debug(f"Looking for class parent: {class_path} -> {parent_id} (normalized: {normalized_class_path})")
            else:
                # This might be a class or top-level symbol
                normalized_parent_path = self._normalize_path(parent_path)
                parent_id = self.symbol_id_map.get(normalized_parent_path)
                self.logger.debug(f"Looking for module parent: {parent_path} -> {parent_id} (normalized: {normalized_parent_path})")
            
            # Extract the actual symbol name from the path
            if "#" in last_part:
                class_method = last_part.split("#")
                if len(class_method) > 1:
                    prefix = class_method[0].strip("`")  # Class name
                    name = class_method[1].strip("`").rstrip(".")  # Method/field name
                    if name.endswith("()"):
                        name = name[:-2]  # Remove parentheses
                else:
                    name = class_method[0].strip("`")
            elif "." in last_part:
                module_class = last_part.split(".")
                if len(module_class) > 1:
                    prefix = module_class[0].strip("`")
                    name = module_class[1].strip("`").rstrip(".")
                    if name.endswith("()"):
                        name = name[:-2]
                else:
                    name = module_class[0].strip("`")
            else:
                name = last_part.strip("`")
                
            # Handle special cases in the name
            if "<" in name and ">" in name:
                # Handle generics and special names
                name = name.replace("<constructor>", "__init__")
                name = name.replace("<get>", "get_")
                name = name.replace("<set>", "set_")
            
            # Clean up name
            name = name.strip("`").rstrip(".")
            if name.endswith("()"):
                name = name[:-2]  # Remove parentheses
                
            # If name is still empty, try to extract it from the symbol path
            if not name and len(parts) > 0:
                name = parts[-1].strip("`").rstrip(".")
                if "#" in name:
                    name = name.split("#")[0].strip("`")
                elif "." in name:
                    name = name.split(".")[0].strip("`")
                    
            # If name is still empty and we have a class or method, use the last part of the path
            if not name and kind in ["Class", "Method", "Function"]:
                name = parts[-1].strip("`").rstrip(".")
                if "#" in name:
                    name = name.split("#")[0].strip("`")
                elif "." in name:
                    name = name.split(".")[0].strip("`")
        
        self.logger.debug(f"Extracted name: {name}")
        self.logger.debug(f"Extracted prefix: {prefix}")
        
        # Handle special cases
        if kind == "Constructor":
            name = "__init__"  # Use Python constructor name
            
        # For methods, include parameters in postfix if available
        if kind == "Method" and hasattr(symbol, 'signature'):
            postfix = f"({symbol.signature})"
            
        # For classes and interfaces, include any type parameters
        if kind in ["Class", "Interface"] and hasattr(symbol, 'type_parameters'):
            if symbol.type_parameters:
                postfix = f"<{', '.join(symbol.type_parameters)}>"
                
        # For Parameter or Variable, if name is empty, generate a placeholder name
        if kind in ["Parameter", "Variable"] and not name:
            name = f"local_{kind.lower()}_{len(self.symbol_id_map)}"
            self.logger.debug(f"Generated placeholder name for {kind}: {name}")
                
        self.logger.debug(f"Final name: {name}")
        self.logger.debug(f"Final prefix: {prefix}")
        self.logger.debug(f"Final postfix: {postfix}")
        self.logger.debug(f"Parent ID: {parent_id}")
        
        # Ensure parent exists for symbols that need one
        parent_id = self._ensure_parent_exists(parent_id, kind)
        
        # Map SCIP kinds to Sourcetrail recording methods with proper parameters
        kind_map = {
            'Class': lambda: (
                class_id := self.db.record_class(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                # Store both normalized and original paths
                self.class_id_map.update({
                    self._normalize_path(symbol.symbol): class_id,
                    f"{self._normalize_path(symbol.symbol)}#": class_id
                }),
                class_id
            )[-1],
            'Method': lambda: (
                method_id := self.db.record_method(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.db.record_ref_member(parent_id, method_id) if parent_id else None,
                method_id
            )[-1],
            'Field': lambda: (
                field_id := self.db.record_field(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.db.record_ref_member(parent_id, field_id) if parent_id else None,
                field_id
            )[-1],
            'Interface': lambda: (
                interface_id := self.db.record_interface(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.class_id_map.update({symbol.symbol: interface_id}),
                interface_id
            )[-1],
            'TypeParameter': lambda: self.db.record_type_parameter_node(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Parameter': lambda: self.db.record_local_symbol(name),  # Removed name check
            'Variable': lambda: self.db.record_local_symbol(name),   # Removed name check
            'Namespace': lambda: self.db.record_namespace(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Package': lambda: self.db.record_package(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'TypeAlias': lambda: self.db.record_typedef_node(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Function': lambda: self.db.record_function(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Constructor': lambda: (
                constructor_id := self.db.record_method(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.db.record_ref_member(parent_id, constructor_id) if parent_id else None,
                constructor_id
            )[-1],
            'Enum': lambda: (
                enum_id := self.db.record_enum(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.class_id_map.update({symbol.symbol: enum_id}),
                enum_id
            )[-1],
            'EnumMember': lambda: (
                member_id := self.db.record_enum_constant(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.db.record_ref_member(parent_id, member_id) if parent_id else None,
                member_id
            )[-1],
            'Module': lambda: self.db.record_module(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Struct': lambda: (
                struct_id := self.db.record_struct(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.class_id_map.update({symbol.symbol: struct_id}),
                struct_id
            )[-1],
            'Union': lambda: self.db.record_union(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Macro': lambda: self.db.record_macro(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Type': lambda: self.db.record_type_node(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'BuiltinType': lambda: self.db.record_buitin_type_node(
                name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
            ),
            'Property': lambda: (
                property_id := self.db.record_field(
                    name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
                ),
                self.db.record_ref_member(parent_id, property_id) if parent_id else None,
                property_id
            )[-1],
        }
        
        # Skip recording if we don't have a valid name for non-local symbols
        if not name and kind not in ["Parameter", "Variable", "UnspecifiedKind"]:
            self.logger.warning(f"Skipping non-local symbol with empty name: {symbol.symbol}")
            return None
            
        # Get the appropriate recording function or use symbol_node as fallback
        record_func = kind_map.get(kind, lambda: self.db.record_symbol_node(
            name=name, prefix=prefix, postfix=postfix, parent_id=parent_id
        ) if name else None)
        
        try:
            self.logger.debug(f"Recording symbol - kind: {kind}, name: {name}, prefix: {prefix}, postfix: {postfix}, parent_id: {parent_id}")
            symbol_id = record_func()
            self.logger.debug(f"Recorded symbol ID: {symbol_id}")
            
            if symbol_id is not None:
                # Store both the full symbol path and the class-qualified path
                self.symbol_id_map[symbol.symbol] = symbol_id
                
                # For class members, also store with class-qualified path
                if "#" in symbol.symbol:
                    parts = symbol.symbol.split("#")
                    class_qualified_path = f"{parts[0]}#{name}"
                    if name:  # Only store if we have a valid name
                        self.symbol_id_map[class_qualified_path] = symbol_id
                        self.logger.debug(f"Stored class-qualified path: {class_qualified_path} -> {symbol_id}")
                
                # Handle documentation if available
                if hasattr(symbol, 'documentation') and symbol.documentation:
                    self._record_symbol_documentation(symbol_id, symbol.documentation)
                    
                # Handle signature if available
                if hasattr(symbol, 'signature') and symbol.signature:
                    self._record_symbol_signature(symbol_id, symbol.signature)
            else:
                self.logger.warning(f"Failed to record symbol {name} (kind: {kind})")
                    
            return symbol_id
        except Exception as e:
            self.logger.error(f"Failed to record symbol {name}: {str(e)}")
            return None

    def _ensure_parent_exists(self, parent_id: Optional[int], kind: str) -> Optional[int]:
        """If no parent found but we need one (e.g., for class members), we could create a default namespace."""
        if parent_id is None and kind in ["Method", "Field", "Function"]:
            # Create a fallback namespace if none exists
            ns_id = self.db.record_namespace(name="__global_namespace__")
            self.logger.debug(f"Created fallback namespace {ns_id} for {kind}")
            return ns_id
        return parent_id

    def _record_symbol_documentation(self, symbol_id: int, documentation: str) -> None:
        """Record symbol documentation."""
        try:
            self.db.record_symbol_documentation(symbol_id, documentation)
        except AttributeError:
            self.logger.debug("SourcetrailDB does not support documentation yet.")
            pass

    def _record_symbol_signature(self, symbol_id: int, signature: str) -> None:
        """Record symbol signature."""
        try:
            self.db.record_symbol_signature(symbol_id, signature)
        except AttributeError:
            self.logger.debug("SourcetrailDB does not support signature recording yet.")
            pass

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
                f"- {doc.relative_path} ({doc.language if hasattr(doc, 'language') else 'unknown'})",
                f"  Symbols: {len(doc.symbols)}",
                f"  Occurrences: {len(doc.occurrences)}"
            ])
        
        return "\n".join(lines) 

    def _process_occurrence(self, occurrence: scip_pb2.Occurrence, symbol_id: int) -> None:
        """Process a single occurrence with its roles."""
        roles = occurrence.symbol_roles
        
        # Get location info for the occurrence
        loc_info = self._get_location_info(occurrence)
        if not loc_info:
            return
            
        file_id, start_line, start_col, end_line, end_col = loc_info
        
        # Handle read access and potential calls
        if roles & 0x8:  # ReadAccess
            # Without symbol_kind_map, rely solely on the symbol naming heuristic:
            if (
                occurrence.symbol.endswith("().") or 
                occurrence.symbol.endswith(".") or 
                "#" in occurrence.symbol  # Heuristic for a method call
            ):
                # Treat as a call
                self.db.record_ref_call(symbol_id, symbol_id)
                self.db.record_reference_location(
                    symbol_id,
                    file_id,
                    start_line,
                    start_col,
                    end_line,
                    end_col
                )
            else:
                # Treat as usage
                self.db.record_ref_usage(symbol_id, symbol_id)
                self.db.record_reference_location(
                    symbol_id,
                    file_id,
                    start_line,
                    start_col,
                    end_line,
                    end_col
                )
        
        # Handle other roles
        if roles & 0x1:  # Definition
            self.db.record_symbol_location(
                symbol_id=symbol_id,
                file_id=file_id,
                start_line=start_line,
                start_column=start_col,
                end_line=end_line,
                end_column=end_col
            )
            
        if roles & 0x2:  # Import
            if occurrence.symbol in self.symbol_id_map:
                target_id = self.symbol_id_map[occurrence.symbol]
                self.db.record_ref_import(symbol_id, target_id)
                self.db.record_reference_location(
                    symbol_id,
                    file_id,
                    start_line,
                    start_col,
                    end_line,
                    end_col
                )
                
        if roles & 0x4:  # WriteAccess
            self.db.record_ref_usage(symbol_id, symbol_id)
            self.db.record_reference_location(
                symbol_id,
                file_id,
                start_line,
                start_col,
                end_line,
                end_col
            )
            
        if roles & 0x10:  # Container
            self.db.record_symbol_scope_location(
                symbol_id=symbol_id,
                file_id=file_id,
                start_line=start_line,
                start_column=1,  # Container scope starts at beginning of line
                end_line=end_line,
                end_column=end_col
            )
            
        if roles & 0x20:  # Type
            if occurrence.symbol in self.symbol_id_map:
                target_id = self.symbol_id_map[occurrence.symbol]
                self.db.record_ref_type_usage(symbol_id, target_id)
                self.db.record_reference_location(
                    symbol_id,
                    file_id,
                    start_line,
                    start_col,
                    end_line,
                    end_col
                )
