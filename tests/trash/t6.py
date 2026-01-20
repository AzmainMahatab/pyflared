import inspect
from collections.abc import Callable
from functools import wraps
from typing import Annotated, get_args, get_origin

import typer
from pydantic import BaseModel, Field, SecretStr
from typer.models import ArgumentInfo, OptionInfo


def pydantic_command(func: Callable) -> Callable:
    """
    Decorator to explode a Pydantic model into Typer CLI arguments.
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    # 1. AUTO-DETECT: Find the argument that is a Pydantic Model
    model_arg_name = None
    model_type = None
    model_index = -1

    for i, param in enumerate(params):
        annotation = param.annotation
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            model_arg_name = param.name
            model_type = annotation
            model_index = i
            break

    if not model_type:
        return func

    # 2. PREPARE NEW PARAMETERS
    del params[model_index]

    new_params = []
    for field_name, field_info in model_type.model_fields.items():

        # A. Check for Explicit Typer Override
        typer_info = next(
            (m for m in field_info.metadata if isinstance(m, (ArgumentInfo, OptionInfo))),
            None
        )

        # B. Resolve Pydantic Default
        real_default = field_info.default
        if str(real_default) == 'PydanticUndefined':
            real_default = ...

        help_text = field_info.description or f"Sets the {field_name}"

        # C. Build the Typer Info Object
        if typer_info:
            # FIX: Only overwrite if Typer thinks it's Required (...).
            # If it is None, the user explicitly passed None, so we KEEP it.
            if typer_info.default == ...:
                typer_info.default = real_default

            if not typer_info.help:
                typer_info.help = help_text
        else:
            typer_info = typer.Option(real_default, help=help_text)

        # D. Create the Parameter
        param = inspect.Parameter(
            field_name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=field_info.annotation,
            default=typer_info,
        )
        new_params.append(param)

    # 3. Insert and Wrap
    for p in reversed(new_params):
        params.insert(model_index, p)

    final_sig = sig.replace(parameters=params)

    @wraps(func)
    def wrapper(**kwargs):
        model_kwargs = {}
        func_kwargs = {}
        for key, value in kwargs.items():
            if key in model_type.model_fields:
                model_kwargs[key] = value
            else:
                func_kwargs[key] = value

        func_kwargs[model_arg_name] = model_type(**model_kwargs)
        return func(**func_kwargs)

    wrapper.__signature__ = final_sig
    return wrapper


app = typer.Typer()


class ConnectionConfig(BaseModel):
    # 1. Simple Flag (Uses Field)
    url: str = Field(..., description="The server URL")
    # url: Annotated[str, typer.Option(help="The server URL")]

    # 2. Positional Argument (Uses Annotated + typer.Argument)
    mode: Annotated[str, typer.Argument(help="Connection mode (read/write)")]

    # 3. Complex Type (Uses Annotated + typer.Option with parser)
    # Note: We rely on the USER to provide the parser logic here, exactly as you wanted.
    token: Annotated[SecretStr | None, typer.Option(
        None,
        envvar="CLOUDFLARE_API_TOKEN",
        parser=SecretStr,  # <--- User handles the parsing logic
        help="CF API Token",
    )]


@app.command()
@pydantic_command
def start(config: ConnectionConfig):
    print(f"Connecting to {config.url}")
    print(f"Token value: {config.token.get_secret_value()}")


if __name__ == "__main__":
    # Test showing help
    app(args=["--help"])
    # app(args=["start", "--url", "https://example.com"])
    # app(args=["start", "--mode", "xa", "--url", "https://example.com"])
    # app(args=["--mode", "xa", "--url", "https://example.com"])
    # app(args=["start", "--url", "https://example.com"])
