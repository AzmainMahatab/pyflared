import inspect
from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any, get_args, get_origin

import typer
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typer.models import ArgumentInfo, OptionInfo


def _unwrap_annotation(annotation: type[Any] | Any) -> type[Any] | Any:
    """Unwrap Annotated type to get the actual type."""
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        return args[0] if args else annotation
    return annotation


def _is_pydantic_model(annotation: type[Any] | Any) -> bool:
    """Check if annotation is a Pydantic BaseModel subclass."""
    try:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)
    except TypeError:
        return False


def _find_pydantic_model(
        params: list[inspect.Parameter],
) -> tuple[str, type[BaseModel], int] | tuple[None, None, int]:
    """
    Find the first Pydantic model parameter in the signature.

    Returns:
        Tuple of (param_name, model_type, index) if found, else (None, None, -1)
    """
    for i, param in enumerate(params):
        annotation = _unwrap_annotation(param.annotation)
        if _is_pydantic_model(annotation):
            # Type narrowing - we know it's a BaseModel subclass here
            return param.name, annotation, i
    return None, None, -1


def _get_typer_info(field_info: FieldInfo) -> ArgumentInfo | OptionInfo | None:
    """Extract typer info (Argument or Option) from field metadata."""
    return next(
        (m for m in field_info.metadata if isinstance(m, (ArgumentInfo, OptionInfo))),
        None,
    )


def _resolve_default(field_info: FieldInfo) -> Any:
    """
    Resolve the default value for a Pydantic field.

    Returns:
        Ellipsis (...) if field is required, otherwise the default value
    """
    return ... if field_info.default is PydanticUndefined else field_info.default


def _create_typer_info(
        field_info: FieldInfo,
        typer_info: ArgumentInfo | OptionInfo | None,
) -> ArgumentInfo | OptionInfo:
    """
    Create or update typer info object for a field.

    Args:
        field_info: Pydantic field information
        typer_info: Existing typer info if provided in annotations

    Returns:
        ArgumentInfo or OptionInfo with appropriate defaults and help text
    """
    real_default = _resolve_default(field_info)
    help_text = field_info.description or f"Sets the {field_info.alias or 'value'}"

    if typer_info:
        # Update existing typer info if needed
        if typer_info.default in (..., None) and real_default is not ...:
            typer_info.default = real_default
        if not typer_info.help:
            typer_info.help = help_text
        return typer_info

    # Create new Option by default
    return typer.Option(real_default, help=help_text)


def _create_cli_parameter(field_name: str, field_info: FieldInfo) -> inspect.Parameter:
    """
    Create an inspect.Parameter for a Pydantic field.

    Args:
        field_name: Name of the field
        field_info: Pydantic field information

    Returns:
        inspect.Parameter configured for CLI usage
    """
    typer_info = _get_typer_info(field_info)
    typer_info = _create_typer_info(field_info, typer_info)

    return inspect.Parameter(
        field_name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=field_info.annotation,
        default=typer_info,
    )


def _format_validation_errors(error: ValidationError) -> str:
    """
    Format Pydantic validation errors into a readable string.

    Args:
        error: Pydantic ValidationError

    Returns:
        Formatted error message string
    """
    error_msgs = (f"{' -> '.join(map(str, err['loc']))}: {err['msg']}"
                  for err in error.errors())

    return "[Error] Validation failed:\n" + "\n".join(error_msgs)


def pydantic_typer_parse[P, R](func: Callable[P, R]) -> Callable[..., R]:
    """
    Decorator to explode a Pydantic model into Typer CLI arguments.

    This decorator automatically converts Pydantic model fields into Typer CLI
    parameters, preserving validation and type checking.

    Usage:
        @app.command()
        @pydantic_typer_parse
        def my_cmd(config: MyModel) -> None:
            ...

    Args:
        func: Function with a Pydantic model parameter to be transformed

    Returns:
        Wrapped function with exploded CLI parameters

    Note:
        The function must have exactly one Pydantic BaseModel parameter.
        If no model is found, the original function is returned unchanged.
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    # Find the Pydantic model parameter
    model_arg_name, model_type, model_index = _find_pydantic_model(params)

    # Early return if no model found
    if model_type is None or model_arg_name is None:
        return func

    # Replace model parameter with exploded CLI parameters
    new_params = [
        _create_cli_parameter(field_name, field_info)
        for field_name, field_info in model_type.model_fields.items()
    ]

    # Replace the single model param with multiple field params using slice assignment
    params[model_index:model_index + 1] = new_params
    final_sig = sig.replace(parameters=params)

    @wraps(func)
    def wrapper(**kwargs: Any) -> R:

        # Partition kwargs into model and function arguments
        model_field_names = frozenset(model_type.model_fields)
        model_kwargs: dict[str, Any] = {k: v for k, v in kwargs.items() if k in model_field_names}
        func_kwargs: dict[str, Any] = {k: v for k, v in kwargs.items() if k not in model_field_names}

        # Validate and instantiate model
        try:
            model_instance: BaseModel = model_type(**model_kwargs)
        except ValidationError as e:
            typer.echo(_format_validation_errors(e), err=True)
            raise typer.Exit(code=1) from e

        # Call original function with model instance
        func_kwargs[model_arg_name] = model_instance
        return func(**func_kwargs)

    wrapper.__signature__ = final_sig
    return wrapper
