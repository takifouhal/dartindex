# Public API

`Numbat` provides a class `SourcetrailDB` created to be easily used by external projects to create Sourcetrail projects. It provides methods to:

- [manage the database file](#numbatSourcetrailDBopen)
- [record symbols](#numbatSourcetrailDBrecord_symbol_node) (according to their types)
- [record references](#numbatSourcetrailDBrecord_ref_member) (links) between symbols
- [record a file](#numbatSourcetrailDBrecord_file) and [information related to the source code](#numbatSourcetrailDBrecord_symbol_location)

## numbat.SourcetrailDB

```python
SourcetrailDB(database, path, logger=None)
```

This class implements a wrapper to Sourcetrail internal database. It can create, edit and delete the underlying sqlite3 database used by Sourcetrail.

### numbat.SourcetrailDB.exists

**Signature:**
```python
@classmethod
exists(path)
```

Check if there is a Sourcetrail db at the given path. If the provided path does not end with the sourcetrail db correct suffix, it will be added.

**Parameters:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| path | Path | str | The path to test | required |

**Returns:**

| Type | Description |
| ---- | ----------- |
| bool | a bool |

### numbat.SourcetrailDB.open

**Signature:**
```python
@classmethod
open(path, clear=False)
```

Open an existing sourcetrail database.

**Parameters:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| path | Path or str | The path to the existing database | required |
| clear | bool | If True, the database is cleared | False |

**Returns:**

| Type | Description |
| ---- | ----------- |
| SourcetrailDB | the SourcetrailDB object |

### numbat.SourcetrailDB.create

**Signature:**
```python
@classmethod
create(path)
```

Create a sourcetrail database.

**Parameters:**

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| path | Path or str | The path to the new database | required |

**Returns:**

| Type | Description |
| ---- | ----------- |
| SourcetrailDB | the SourcetrailDB object |

### numbat.SourcetrailDB.commit

**Signature:**
```python
commit()
```

Commit changes made to a sourcetrail database.

**Returns:**

| Type | Description |
| ---- | ----------- |
| None | None |

### numbat.SourcetrailDB.clear

**Signature:**
```python
clear()
```

Clear all elements present in the database.

**Returns:**

| Type | Description |
| ---- | ----------- |
| None | None |

### numbat.SourcetrailDB.close

**Signature:**
```python
close()
```

Close a sourcetrail database to free memory and resources.

**Returns:**

| Type | Description |
| ---- | ----------- |
| None | None |

### numbat.SourcetrailDB.record_symbol_node

**Signature:**
```python
record_symbol_node(
    name="",
    prefix="",
    postfix="",
    delimiter=NameHierarchy.NAME_DELIMITER_CXX,
    parent_id=None,
    is_indexed=True,
)
```

Record a "SYMBOL" symbol into the DB.

**Parameters:**

| Name      | Type | Description                                                                                                                   | Default                                |
|-----------|------|-------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| name      | str  | The name of the element to insert                                                                                            | ''                                     |
| prefix    | str  | The prefix of the element                                                                                                    | ''                                     |
| postfix   | str  | The postfix of the element                                                                                                   | ''                                     |
| delimiter | str  | The delimiter of the element. If the element has a parent, parent's delimiter is used.                                        | NAME_DELIMITER_CXX                     |
| parent_id | int  | The identifier of the parent element.                                                                                        | None                                   |
| is_indexed| bool | If the element is explicit or non-indexed                                                                                     | True                                   |

**Returns:**

| Type      | Description                                                |
|-----------|------------------------------------------------------------|
| int | None | The identifier of the new symbol node or None if not inserted |

*(Note: The following methods `record_type_node`, `record_buitin_type_node`, `record_module`, etc. follow a similar pattern. For brevity, only parameters and returns are listed. The descriptions are analogous, indicating what kind of symbol is recorded.)*

### numbat.SourcetrailDB.record_type_node
Record a TYPE symbol.

Parameters and returns same pattern as `record_symbol_node` but for a TYPE symbol.

### numbat.SourcetrailDB.record_buitin_type_node
Record a BUILTIN_TYPE symbol.

### numbat.SourcetrailDB.record_module
Record a MODULE symbol.

### numbat.SourcetrailDB.record_namespace
Record a NAMESPACE symbol.

### numbat.SourcetrailDB.record_package
Record a PACKAGE symbol.

### numbat.SourcetrailDB.record_struct
Record a STRUCT symbol.

### numbat.SourcetrailDB.record_class
Record a CLASS symbol.

### numbat.SourcetrailDB.record_interface
Record an INTERFACE symbol.

### numbat.SourcetrailDB.record_annotation
Record an ANNOTATION symbol.

### numbat.SourcetrailDB.record_global_variable
Record a GLOBAL_VARIABLE symbol.

### numbat.SourcetrailDB.record_field
Record a FIELD symbol.

### numbat.SourcetrailDB.record_function
Record a FUNCTION symbol.

### numbat.SourcetrailDB.record_method
Record a METHOD symbol.

### numbat.SourcetrailDB.record_enum
Record an ENUM symbol.

### numbat.SourcetrailDB.record_enum_constant
Record an ENUM_CONSTANT symbol.

### numbat.SourcetrailDB.record_typedef_node
Record a TYPEDEF symbol.

### numbat.SourcetrailDB.record_type_parameter_node
Record a TYPE_PARAMETER symbol.

### numbat.SourcetrailDB.record_macro
Record a MACRO symbol.

### numbat.SourcetrailDB.record_union
Record a UNION symbol.

### numbat.SourcetrailDB.record_ref_member
Add a member reference between two elements.

**Parameters:**

| Name     | Type | Description         | Default |
|----------|------|---------------------|---------|
| source_id| int  | The source element  | required|
| dest_id  | int  | The destination elem| required|

**Returns:**

| Type | Description      |
|------|------------------|
| int  | the reference id |

*(Similar pattern for the following `record_ref_...` methods. They describe different types of references between elements: TYPE_USAGE, USAGE, CALL, INHERITANCE, etc.)*

### numbat.SourcetrailDB.record_ref_type_usage
### numbat.SourcetrailDB.record_ref_usage
### numbat.SourcetrailDB.record_ref_call
### numbat.SourcetrailDB.record_ref_inheritance
### numbat.SourcetrailDB.record_ref_override
### numbat.SourcetrailDB.record_ref_type_argument
### numbat.SourcetrailDB.record_ref_template_specialization
### numbat.SourcetrailDB.record_ref_include
### numbat.SourcetrailDB.record_ref_import
### numbat.SourcetrailDB.record_ref_bundled_edges
### numbat.SourcetrailDB.record_ref_macro_usage
### numbat.SourcetrailDB.record_ref_annotation_usage

### numbat.SourcetrailDB.record_reference_to_unsolved_symbol

Record a reference to an unsolved symbol.

**Parameters:**
- symbol_id: int
- reference_type: EdgeType
- file_id: int
- start_line, start_column, end_line, end_column: int

**Returns:**
- int: The new reference id.

### numbat.SourcetrailDB.record_reference_is_ambiguous
Mark a reference as ambiguous.

**Parameters:**
- reference_id: int

**Returns:**
- None

### numbat.SourcetrailDB.record_file
Record a source file in the database.

**Parameters:**
- path (Path): The file path
- indexed (bool): If the file was indexed

**Returns:**
- int: The file id

### numbat.SourcetrailDB.record_file_language
Set the language of an existing file.

**Parameters:**
- id_: int (file id)
- language: str

**Returns:**
- None

### numbat.SourcetrailDB.record_symbol_location
Record a TOKEN source location of a symbol.

Parameters: symbol_id, file_id, start_line, start_column, end_line, end_column

### numbat.SourcetrailDB.record_symbol_scope_location
Record a SCOPE location of a symbol.

Similar parameters as record_symbol_location.

### numbat.SourcetrailDB.record_symbol_signature_location
Record a SIGNATURE location of a symbol.

Similar parameters as above.

### numbat.SourcetrailDB.record_reference_location
Record a TOKEN location of a reference.

### numbat.SourcetrailDB.record_qualifier_location
Record a QUALIFIER location of a symbol.

### numbat.SourcetrailDB.record_local_symbol
Record a local symbol.

**Parameters:**
- name: str (the local symbol name)

**Returns:**
- int: The local symbol id

### numbat.SourcetrailDB.record_local_symbol_location
Record a LOCAL_SYMBOL location.

### numbat.SourcetrailDB.record_atomic_source_range
Record an ATOMIC_RANGE location.

### numbat.SourcetrailDB.record_error
Record an indexer error.

**Parameters:**
- msg: str
- fatal: bool
- file_id: int
- start_line, start_column, end_line, end_column

**Returns:**
- None

---

# Types

**Module:** `numbat.types`

This module defines various internal classes and wrappers around the Sourcetrail database structure.

### numbat.types.Element
Represents an element entry in the database (`element` table).

### numbat.types.ElementComponentType
Represent element component type (used for ambiguity).

### numbat.types.ElementComponent
Wrapper for `element_component` table.

### numbat.types.EdgeType
Represents an edge type inside the sourcetrail database (relationship between nodes).

### numbat.types.Edge
Wrapper for `edge` table.

Parameters: id, type, src, dst.

### numbat.types.NodeType
Represents a node type inside the database.

### numbat.types.Node
Wrapper for `node` table.

Holds `id`, `type`, and `serialized_name` (a `NameHierarchy`).

### numbat.types.SymbolType
Represents a symbol definition type.

### numbat.types.Symbol
Wrapper for `symbol` table. Adds info on elements such as node.

### numbat.types.File
Wrapper for `file` table.

### numbat.types.FileContent
Wrapper for `filecontent` table.

### numbat.types.LocalSymbol
Wrapper for `local_symbol` table. Local variables, etc.

### numbat.types.SourceLocationType
Represents a source location type (token, scope, etc.)

### numbat.types.SourceLocation
Wrapper for `source_location` table (start_line, end_line, etc.)

### numbat.types.Occurrence
Wrapper for `occurrence` table, links elements and source locations.

### numbat.types.ComponentAccessType
Represents a component access type (visibility).

### numbat.types.ComponentAccess
Wrapper for `component_access` table.

### numbat.types.Error
Wrapper for `error` table (indexing/parsing errors).

### numbat.types.NameElement
A basic component of a serialized_name (prefix, name, postfix).

Methods:
- get_prefix(), get_name(), get_postfix()
- set_prefix(prefix), set_name(name), set_postfix(postfix)

### numbat.types.NameHierarchy
Represents the hierarchy relationship stored in `serialized_name`.

Methods:
- extend(element): add a new NameElement
- serialize_range(start, end): partial serialization
- serialize_name(): full serialization
- size(): number of elements
- deserialize_name(serialized_name): staticmethod to parse serialized name into a NameHierarchy.

---


# Numbat

Numbat is an API to create and manipulate Sourcetrail databases. Sourcetrail is a code source explorer allowing navigation through code components.

Numbat aims to provide a Python SDK to create and edit Sourcetrail databases without needing the original SourcetrailDB bindings.

Pyrrha uses Numbat to map firmware structure.

## Installation

Numbat is on PyPI:
```bash
pip install numbat
```

### From sources
```bash
pip install 'numbat @ git+https://github.com/quarkslab/numbat'
```
Or:
```bash
git clone git@github.com:quarkslab/numbat.git
cd numbat
pip install .
```

### Build Documentation
Install with `doc` extras:
```bash
cd NUMBAT_DIR
pip install .[doc]

# or
pip install 'numbat[doc]'

mkdocs serve
```

## Basic Usage

Example:
```python
from pathlib import Path
from numbat import SourcetrailDB

# Create/Open DB
db = SourcetrailDB.open(Path('my_db'), clear=True)

# Record a class with a method 'main'
my_main = db.record_class(name="MyMainClass")
meth_id = db.record_method(name="main", parent_id=my_main)

# Create another class with a field 'first_name'
class_id = db.record_class(name="PersonalInfo")
field_id = db.record_field(name="first_name", parent_id=class_id)

# The method 'main' uses the 'first_name' field
db.record_ref_usage(meth_id, field_id)

# Commit and close
db.commit()
db.close()
```

---
