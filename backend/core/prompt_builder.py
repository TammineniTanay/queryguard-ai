def build_table_picker_prompt(question, available_tables):
    tables_list = ", ".join(available_tables)
    system = (
        "You are a data analyst. Given a question, return only the table names "
        "needed to answer it. Return a comma-separated list. Nothing else."
    )
    user = f"Available tables: {tables_list}\n\nQuestion: {question}\n\nTables needed:"
    return system, user


def build_sql_prompt(question, schema, join_clauses):
    # build a readable schema description for the LLM
    schema_text = ""
    for table, info in schema.items():
        cols = ", ".join(f"{c['name']} ({c['type']})" for c in info["columns"])
        schema_text += f"\nTable: {table}\nColumns: {cols}\n"

    system = f"""You are a SQLite SQL expert. Write accurate SQL for the question below.

Rules:
- Only use tables and columns listed in the schema
- Only use the approved joins provided
- Never write SELECT *
- Never write DELETE, UPDATE, INSERT, or DROP
- If you cannot answer with this schema, write exactly: CANNOT_ANSWER
- Return only the SQL query, no explanation

Schema:
{schema_text}
Approved joins:
{join_clauses}"""

    user = f"Question: {question}\n\nSQL:"
    return system, user
