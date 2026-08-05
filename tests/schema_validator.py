"""Small offline validator for the JSON Schema keywords used by this project."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
from typing import Any


class SchemaValidationError(ValueError):
    """Raised without including the rejected instance value."""


class LocalSchemaValidator:
    def __init__(self, contracts_directory: Path) -> None:
        self.contracts_directory = contracts_directory.resolve()
        self._documents: dict[Path, dict[str, Any]] = {}

    def validate(self, instance: Any, schema_file: str) -> None:
        source = (self.contracts_directory / schema_file).resolve()
        schema = self._load(source)
        self._validate(instance, schema, source, "document")

    def _load(self, source: Path) -> dict[str, Any]:
        if source.parent != self.contracts_directory:
            raise SchemaValidationError("schema reference leaves the contracts directory")
        if source not in self._documents:
            try:
                document = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as error:
                raise SchemaValidationError("schema document could not be loaded") from error
            if not isinstance(document, dict):
                raise SchemaValidationError("schema root must be an object")
            self._documents[source] = document
        return self._documents[source]

    def _resolve(self, reference: str, current: Path) -> tuple[Any, Path]:
        resource, separator, fragment = reference.partition("#")
        source = current if not resource else (current.parent / resource).resolve()
        target: Any = self._load(source)
        if separator and fragment:
            if not fragment.startswith("/"):
                raise SchemaValidationError("schema reference fragment is unsupported")
            for encoded_part in fragment[1:].split("/"):
                part = encoded_part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    raise SchemaValidationError("schema reference could not be resolved")
                target = target[part]
        return target, source

    def _is_valid(self, instance: Any, schema: Any, source: Path, path: str) -> bool:
        try:
            self._validate(instance, schema, source, path)
        except SchemaValidationError:
            return False
        return True

    @staticmethod
    def _matches_type(instance: Any, expected: str) -> bool:
        if expected == "null":
            return instance is None
        if expected == "boolean":
            return isinstance(instance, bool)
        if expected == "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        if expected == "number":
            return (
                isinstance(instance, (int, float))
                and not isinstance(instance, bool)
                and math.isfinite(float(instance))
            )
        if expected == "string":
            return isinstance(instance, str)
        if expected == "array":
            return isinstance(instance, list)
        if expected == "object":
            return isinstance(instance, dict)
        return False

    def _validate(self, instance: Any, schema: Any, source: Path, path: str) -> None:
        if schema is True:
            return
        if schema is False or not isinstance(schema, dict):
            raise SchemaValidationError(f"{path} is rejected by the schema")

        if "$ref" in schema:
            target, target_source = self._resolve(schema["$ref"], source)
            self._validate(instance, target, target_source, path)
            siblings = {key: value for key, value in schema.items() if key != "$ref"}
            if siblings:
                self._validate(instance, siblings, source, path)
            return

        expected_types = schema.get("type")
        if expected_types is not None:
            allowed = [expected_types] if isinstance(expected_types, str) else expected_types
            if not isinstance(allowed, list) or not any(
                isinstance(expected, str) and self._matches_type(instance, expected)
                for expected in allowed
            ):
                raise SchemaValidationError(f"{path} has the wrong JSON type")

        if "const" in schema and instance != schema["const"]:
            raise SchemaValidationError(f"{path} does not match the required constant")
        if "enum" in schema and instance not in schema["enum"]:
            raise SchemaValidationError(f"{path} is outside the allowed values")

        for subschema in schema.get("allOf", []):
            self._validate(instance, subschema, source, path)
        if "oneOf" in schema:
            matches = sum(
                self._is_valid(instance, subschema, source, path)
                for subschema in schema["oneOf"]
            )
            if matches != 1:
                raise SchemaValidationError(f"{path} does not match exactly one contract branch")
        if "not" in schema and self._is_valid(instance, schema["not"], source, path):
            raise SchemaValidationError(f"{path} matches a prohibited contract branch")
        if "if" in schema and self._is_valid(instance, schema["if"], source, path):
            if "then" in schema:
                self._validate(instance, schema["then"], source, path)
        elif "else" in schema:
            self._validate(instance, schema["else"], source, path)

        if isinstance(instance, dict):
            required = schema.get("required", [])
            if any(key not in instance for key in required):
                raise SchemaValidationError(f"{path} is missing a required field")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                if any(key not in properties for key in instance):
                    raise SchemaValidationError(f"{path} contains an unknown field")
            for key, subschema in properties.items():
                if key in instance:
                    self._validate(instance[key], subschema, source, f"{path}.{key}")

        if isinstance(instance, list):
            if len(instance) < schema.get("minItems", 0):
                raise SchemaValidationError(f"{path} contains too few items")
            maximum = schema.get("maxItems")
            if maximum is not None and len(instance) > maximum:
                raise SchemaValidationError(f"{path} contains too many items")
            if schema.get("uniqueItems"):
                rendered = [
                    json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    for item in instance
                ]
                if len(rendered) != len(set(rendered)):
                    raise SchemaValidationError(f"{path} contains duplicate items")
            prefix = schema.get("prefixItems", [])
            for index, subschema in enumerate(prefix):
                if index < len(instance):
                    self._validate(instance[index], subschema, source, f"{path}[{index}]")
            if "items" in schema:
                for index in range(len(prefix), len(instance)):
                    self._validate(instance[index], schema["items"], source, f"{path}[{index}]")

        if isinstance(instance, str):
            if len(instance) < schema.get("minLength", 0):
                raise SchemaValidationError(f"{path} is too short")
            maximum = schema.get("maxLength")
            if maximum is not None and len(instance) > maximum:
                raise SchemaValidationError(f"{path} is too long")
            if "pattern" in schema and re.search(schema["pattern"], instance) is None:
                raise SchemaValidationError(f"{path} does not match the public text pattern")

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                raise SchemaValidationError(f"{path} is below the minimum")
            if "maximum" in schema and instance > schema["maximum"]:
                raise SchemaValidationError(f"{path} is above the maximum")
            if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
                raise SchemaValidationError(f"{path} is not above the exclusive minimum")
            if "multipleOf" in schema:
                try:
                    if Decimal(str(instance)) % Decimal(str(schema["multipleOf"])) != 0:
                        raise SchemaValidationError(f"{path} has unsupported precision")
                except InvalidOperation as error:
                    raise SchemaValidationError(f"{path} has unsupported precision") from error
