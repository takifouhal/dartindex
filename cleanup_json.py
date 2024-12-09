import json

def is_unwanted_symbol(symbol_data):
    # Define conditions for what is considered a local variable detail
    # For this example, we assume symbols with kind "Parameter" are local details
    # Adjust this logic based on your dataset.
    if symbol_data.get("kind") == "Parameter":
        return True
    return False

with open('db.json', 'r') as f:
    data = json.load(f)

# Remove large fields from symbols in documents
for doc in data.get("documents", []):
    # Remove language field if present
    doc.pop("language", None)

    if "symbols" in doc:
        new_symbols = []
        for sym in doc["symbols"]:
            # Remove documentation fields
            sym.pop("documentation", None)
            sym.pop("signature_documentation", None)
            # Remove language fields if present
            sym.pop("language", None)

            # Check if this symbol is unwanted (like a local variable)
            if not is_unwanted_symbol(sym):
                new_symbols.append(sym)
        doc["symbols"] = new_symbols

    if "occurrences" in doc:
        for occ in doc["occurrences"]:
            # Remove syntax-specific fields
            occ.pop("syntax_kind", None)
            # If local variable details appear here, remove them as well
            # (If you know the key representing local details in occurrences, remove them here)
            # Example: occ.pop("local_var_detail", None)

# Remove large fields and unwanted details from external_symbols
if "external_symbols" in data:
    new_external_symbols = []
    for sym in data["external_symbols"]:
        # Remove documentation fields
        sym.pop("documentation", None)
        sym.pop("signature_documentation", None)
        # Remove language fields if present
        sym.pop("language", None)

        # Check if this symbol is unwanted
        if not is_unwanted_symbol(sym):
            new_external_symbols.append(sym)
    data["external_symbols"] = new_external_symbols

# Further simplify metadata if needed
if "metadata" in data:
    # Keep only essential fields. For example, just text_document_encoding
    data["metadata"] = {
        "text_document_encoding": data["metadata"].get("text_document_encoding", "UTF8")
    }

with open('db_minimized.json', 'w') as f:
    json.dump(data, f, indent=2)
