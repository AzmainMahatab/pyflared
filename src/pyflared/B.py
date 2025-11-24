from cloudflare import Cloudflare


class TunnelManager:
    def __init__(self, api_token: str, account_no: int = 0, account_id: str | None = None):
        self.client = Cloudflare(api_token=api_token)
        if account_id:
            self.account_id = account_id
        else:
            self.account_id = self.client.accounts.list().result[account_no].id


