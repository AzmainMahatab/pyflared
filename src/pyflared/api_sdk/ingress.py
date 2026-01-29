from collections.abc import Iterable
from typing import Final

from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import ConfigIngress

default_catch_all: Final[ConfigIngress] = ConfigIngress(
    service="http_status:404")  # type: ignore # pyright: ignore[reportCallIssue]


def get_path_length(rule: ConfigIngress) -> int:
    """Returns path length. Used for sorting longest paths first."""
    return len(rule.get("path", ""))


def get_hostname(rule: ConfigIngress) -> str:
    """Returns hostname. Used for alphabetical stability."""
    return rule.get("hostname", "")


def fix_ingress_order(ingresses: Iterable[ConfigIngress]) -> list[ConfigIngress]:
    """
    Sorts rules by specificity and manages the Catch-All rule.
    Safe against empty strings (hostname="").
    """

    path_rules: list[ConfigIngress] = []
    root_rules: list[ConfigIngress] = []
    catch_all_rules: list[ConfigIngress] = []

    # 1. Bucket the rules (Robust Method)
    for rule in ingresses:
        # Check TRUTHINESS, not just key existence.
        # This handles: missing key, None, and empty string ""
        if rule.get("hostname"):
            if rule.get("path"):
                path_rules.append(rule)
            else:
                root_rules.append(rule)
        else:
            # Goes here if hostname is Missing OR Empty ""
            catch_all_rules.append(rule)

    # 2. Handle Catch-All Logic
    if len(catch_all_rules) == 0:
        # User forgot it -> Add default 404
        catch_all_rules.append(default_catch_all)

    elif len(catch_all_rules) > 1:
        raise ValueError(
            f"Invalid Configuration: Found {len(catch_all_rules)
            } Catch-All rules. Only one global catch-all (service without hostname) is allowed."
        )

    # 3. Sort specific buckets
    path_rules.sort(key=get_path_length, reverse=True)
    root_rules.sort(key=get_hostname)

    # 4. Return final ordered list
    return path_rules + root_rules + catch_all_rules

# --- Usage Examples ---
# Case A: User forgets catch-all (Auto-fix)
# input_a: list[ConfigIngress] = [
#     {"hostname": "example.com", "service": "http://localhost:8080"},
# ]
#
# # Case B: User has messy order (Auto-sort)
# input_b: list[ConfigIngress] = [
#     {"service": "http_status:503"},  # Catch-all provided early
#     {"hostname": "example.com", "path": "/api", "service": "http://localhost:8000"},
#     {"hostname": "example.com", "path": "/api/v2", "service": "http://localhost:9000"},
# ]
#
# # Run them
# result_a = sort_and_validate_ingress(input_a)
# result_b = sort_and_validate_ingress(input_b)
#
# print("--- Result A (Auto-added 404) ---")
# print(result_a)
#
# print("\n--- Result B (Sorted Specificity) ---")
# # Notice /api/v2 comes before /api, and catch-all is last
# for r in result_b:
#     print(f"{r.get('hostname', '*')} {r.get('path', '')} -> {r['service']}")
