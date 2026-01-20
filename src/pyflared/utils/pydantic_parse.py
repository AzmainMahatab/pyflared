import inspect
from collections.abc import Callable
from functools import wraps
from typing import Annotated, get_args, get_origin

import typer
from pydantic import BaseModel, ValidationError
from typer.models import ArgumentInfo, OptionInfo


def pydantic_typer_parse(func: Callable) -> Callable:
    """
    Decorator to explode a Pydantic model into Typer CLI arguments.
    Usage:
        @app.command()
        @pydantic_typer_parse
        def my_cmd(config: MyModel): ...
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    # 1. AUTO-DETECT: Find the argument that is a Pydantic Model
    model_arg_name = None
    model_type = None
    model_index = -1

    for i, param in enumerate(params):
        # Unwrap Annotated if present to check type
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

    # Iterate over the model fields to create Typer params
    for field_name, field_info in model_type.model_fields.items():

        # A. Check for Explicit Typer Override (Argument or Option)
        # In Pydantic v2, extra metadata from Annotated ends up in field_info.metadata
        typer_info = next(
            (m for m in field_info.metadata if isinstance(m, (ArgumentInfo, OptionInfo))),
            None
        )

        # B. Resolve Defaults
        # If Pydantic default is Required (PydanticUndefined) or Ellipsis (...), Typer needs ...
        real_default = field_info.default
        if str(real_default) == 'PydanticUndefined':
            real_default = ...

        # Description fallback
        help_text = field_info.description or f"Sets the {field_name}"

        # C. Build or Modify the Typer Info Object
        if typer_info:
            # If user provided Annotated[T, typer.Argument(...)], use it.
            # We only overwrite default if it's currently generic (Empty/Required)
            if typer_info.default == ... or typer_info.default is None:
                # Only override if the Pydantic model actually has a value to offer
                if real_default is not ...:
                    typer_info.default = real_default

            if not typer_info.help:
                typer_info.help = help_text
        else:
            # Default behavior: Map to typer.Option (flags)
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

        # Separate args meant for the model vs the function
        for key, value in kwargs.items():
            if key in model_type.model_fields:
                model_kwargs[key] = value
            else:
                func_kwargs[key] = value

        # 4. INSTANTIATE & VALIDATE
        try:
            # Pydantic validation happens here (including regex)
            model_instance = model_type(**model_kwargs)
        except ValidationError as e:
            # Format Pydantic errors into nice CLI errors
            error_msgs = []
            for err in e.errors():
                loc = " -> ".join(str(l) for l in err['loc'])
                msg = err['msg']
                error_msgs.append(f"{loc}: {msg}")

            # Raise TyperExit or BadParameter to show help nicely
            typer.echo("[Error] Validation failed:\n" + "\n".join(error_msgs), err=True)
            raise typer.Exit(code=1)

        func_kwargs[model_arg_name] = model_instance
        return func(**func_kwargs)

    wrapper.__signature__ = final_sig
    return wrapper

# app = typer.Typer()
# class ConnectionConfig(BaseModel):
#     # 1. Simple Flag (Uses Field)
#     url: str = Field(..., description="The server URL")
#
#     # 2. Positional Argument (Uses Annotated + typer.Argument)
#     mode: Annotated[str, typer.Argument(help="Connection mode (read/write)")]
#
#     # 3. Complex Type (Uses Annotated + typer.Option with parser)
#     # Note: We rely on the USER to provide the parser logic here, exactly as you wanted.
#     token: Annotated[SecretStr | None, typer.Option(
#         "None",
#         envvar="CLOUDFLARE_API_TOKEN",
#         parser=SecretStr,  # <--- User handles the parsing logic
#         help="CF API Token",
#     )]
#
#
# @app.command()
# @pydantic_parse
# def start(config: ConnectionConfig):
#     print(f"Connecting to {config.url}")
#     print(f"Token value: {config.token.get_secret_value()}")
#
#
# if __name__ == "__main__":
#     # Test showing help
#     # app(args=["--help"])
#     app(args=["start", "--url", "https://example.com"])
