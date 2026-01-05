

class ProcessInstance(AsyncIterable[ProcessOutput], Protocol):

    async def stdout_only(self) -> AsyncIterator[bytes]:
        """Yields only stdout, but drains stderr."""
        async for output in self:
            if output.channel == OutputChannel.STDOUT:
                yield output.data

    async def stderr_only(self) -> AsyncIterator[bytes]:
        """Yields only stderr, but drains stdout."""
        async for output in self:
            if output.channel == OutputChannel.STDERR:
                yield output.data

    @abstractmethod
    async def write(self, data: AwaitableMaybe[str | bytes]) -> None:
        ...

    async def write_from_responders(self, chunk: bytes, channel: OutputChannel, responders: Iterable[Responder]):
        for responder in responders:
            response = await safe_awaiter(responder(chunk, channel))
            if response is not None:
                await self.write(response)

    async def pipe_to(self, target: RunningProcess, mutator: Mutator | None = None) -> None:
        async for output in self:
            if mutator:
                await target.write(mutator(output))
            elif output.channel == OutputChannel.STDOUT:
                await target.write(output.data)

    @abstractmethod
    async def drain_wait(self) -> int:
        ...

    @abstractmethod
    @property
    def returncode(self) -> int | None:
        ...