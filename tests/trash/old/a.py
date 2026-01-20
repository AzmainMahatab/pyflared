# def clean_domain(url: str) -> str:
#     """
#     Removes 'http://' or 'https://' from the start,
#     AND removes a trailing '/' from the end.
#     """
#     # ^https?://  -> Matches http:// or https:// at the START
#     # |           -> OR
#     # /$          -> Matches a / at the END
#     return re.sub(r"^https?://|/$", "", url, flags=re.IGNORECASE)
#
#
# def normalize_if_local_url(url: str) -> str:
#     # 1. Always strip the trailing slash(es) first
#     url = url.rstrip("/")
#
#     # 2. Case: "8000" -> "http://localhost:8000"
#     # Checks if the entire string is just numbers
#     if url.isdigit():
#         return f"http://localhost:{url}"
#
#     # 3. Case: "localhost:8000" -> "http://localhost:8000"
#     if url.startswith("localhost"):
#         return f"http://{url}"
#
#     # 4. Default: Return as is (e.g. already has http://)
#     return url


# def parse_pair(value: str) -> tuple[str, str]:
#     # --- Validator ---
#     if "=" not in value:
#         raise typer.BadParameter(f"Format must be 'domain=service', got: {value}")
#     domain, service = value.split("=", 1)
#     return clean_domain(domain), normalize_if_local_url(service)
