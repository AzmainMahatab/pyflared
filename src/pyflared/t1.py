import asyncio


class TunnelService:
    def __init__(self, config: str):
        self.config = config
        self._process = None

    async def __aenter__(self):
        """
        Called when entering: async with TunnelService() as t:
        Starts the binary but DOES NOT BLOCK execution.
        """
        print(f"Starting tunnel with config: {self.config}")
        self._process = await asyncio.create_subprocess_exec(
            "sleep", "10",  # Replace with actual binary
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Optional: Check if it crashed immediately
        if self._process.returncode is not None:
            raise RuntimeError("Tunnel failed to start")

        return self  # Returns the object to the user

    async def __aexit__(self, exc_type, exc, tb):
        """
        Called when exiting the block (Success, Crash, or Cancellation).
        Guarantees cleanup.
        """
        print("Stopping tunnel...")
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()
        print("Tunnel stopped.")
