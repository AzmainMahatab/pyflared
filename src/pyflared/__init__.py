import warnings

# Supress Pydantic V1 deprecation warning in cloudflare
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="cloudflare._compat",
)
