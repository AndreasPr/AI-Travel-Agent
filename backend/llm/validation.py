import json

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from backend.llm.types import InvalidOutput


def schema_dict(schema):
    return schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema


def validate(value, schema):
    if schema is None:
        return value
    try:
        schema = schema_dict(schema)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except (ValidationError, SchemaError) as exc:
        raise InvalidOutput("Output does not satisfy the JSON schema") from exc
    return value


def parse_json(text, schema):
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise InvalidOutput("Provider returned invalid JSON") from exc
    return validate(value, schema)


def tool_definitions(tools):
    return [tool.get("function", tool) for tool in (tools or [])]


def validate_response(response, tools=None, response_schema=None):
    definitions = {tool["name"]: tool for tool in tool_definitions(tools)}
    for call in response.tool_calls:
        if call.name not in definitions:
            raise InvalidOutput("Provider returned an undeclared tool")
        validate(call.arguments, definitions[call.name].get("parameters", {"type": "object"}))
    if response_schema is not None and not response.tool_calls:
        parse_json(response.text, response_schema)
    return response
