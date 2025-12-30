class X:

    async def write(self, data: str | bytes):
        """Helper to write raw data to stdin safely"""
        if not self.process.stdin:
            return

        if isinstance(data, str):
            data = (data + "\n").encode()  # Auto-newline for strings

        self.process.stdin.write(data)
        await self.process.stdin.drain()


class ProcessStream2:
    """
    Handles reading from the subprocess, merging stdout/stderr safely,
    and managing interactive responders.
    """

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self._responders: Iterable[Responder] = []
        # Queue holds (line_bytes, channel) tuples
        self._line_queue: asyncio.Queue[tuple[bytes, OutputChannel] | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    def add_responder(self, responder: Responder):
        """Register a runtime responder (e.g. for passwords)"""
        self._responders.append(responder)

    async def write(self, data: str | bytes):
        """Safe write to stdin"""
        if not self.process.stdin:
            return

        if isinstance(data, str):
            # Auto-append newline if string is passed
            data = (data + "\n").encode()

        try:
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass  # Process might have closed already

    async def _read_stream(self, stream_reader: asyncio.StreamReader, channel: OutputChannel):
        """Background task: Reads a specific stream line-by-line"""
        while True:
            line_bytes = await stream_reader.readline()
            if not line_bytes:
                break

            # 1. Run Responders (Auto-Reply)
            for responder in self._responders:
                try:
                    response = responder(line_bytes, channel)
                    if inspect.isawaitable(response):
                        response = await response

                    if response is not None:
                        await self.write(response)
                except Exception as e:
                    logger.error(f"Responder error: {e}")

            # 2. Enqueue for User
            await self._line_queue.put((line_bytes, channel))

    async def start_watching(self):
        """Starts background readers for both STDOUT and STDERR"""
        if self.process.stdout:
            self._tasks.append(asyncio.create_task(
                self._read_stream(self.process.stdout, OutputChannel.STDOUT)
            ))
        if self.process.stderr:
            self._tasks.append(asyncio.create_task(
                self._read_stream(self.process.stderr, OutputChannel.STDERR)
            ))

        # Wait for both streams to close
        await asyncio.gather(*self._tasks)
        # Signal End of Stream to the iterator
        await self._line_queue.put(None)

    async def __aiter__(self) -> AsyncGenerator[tuple[bytes, OutputChannel], None]:
        """
        Async Iterator.
        Starts watchers lazily when iteration begins.
        Yields: (line_bytes, channel)
        """
        watch_task = asyncio.create_task(self.start_watching())

        try:
            while True:
                item = await self._line_queue.get()
                if item is None:
                    break
                yield item
        finally:
            # Ensure we don't leave zombie tasks if the user breaks the loop
            watch_task.cancel()
            for t in self._tasks: t.cancel()


class ProcessStream3(AsyncIterator[tuple[bytes, OutputChannel]]):
    # def __anext__(self):
    #     pass

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self._responders: list[Responder] = []

    def add_responder(self, responder: Responder):
        """Register a runtime responder (e.g. for passwords)"""
        self._responders.append(responder)

    async def write(self, data: str | bytes):
        """Safe write to stdin"""
        if not self.process.stdin:
            return

        if isinstance(data, str):
            # Auto-append newline if string is passed
            data = (data + "\n").encode()

        try:
            self.process.stdin.write(data)
            await self.process.stdin.drain()
        except BrokenPipeError:
            pass  # Process might have closed already

    async def __anext__(self) -> tuple[bytes, OutputChannel]:
        if self.process.stdout:
            async for line in self.process.stdout:
                for responder in self._responders:
                    response = responder(line, OutputChannel.STDOUT)
                    if inspect.isawaitable(response):
                        response = await response
                    if response is not None:
                        await self.write(response)
                return line, OutputChannel.STDOUT
        if self.process.stderr:
            async for line in self.process.stderr:
                for responder in self._responders:
                    response = responder(line, OutputChannel.STDERR)
                    if inspect.isawaitable(response):
                        response = await response
                    if response is not None:
                        await self.write(response)
                return line, OutputChannel.STDERR
        return None


# @asynccontextmanager
# def fq():
#     pass

# def f1(t: Iterable[str]):
# # def f1(t: tuple[str, ...]):
#     pass
#
# f1(("a", "s"))
# f1(["test", "q"])


class MultiplexStream[T](AsyncIterator[T]):
    def __init__(self, *iterators: AsyncIterator[T]):
        self.iterators = list(iterators)
        # We map the running Task back to its source Iterator
        # So when a Task finishes, we know which iterator to pull from next
        self.pending: dict[Task[T], AsyncIterator[T]] = {}

    def __aiter__(self) -> AsyncIterator[T]:
        # Prime the pump: Create the first "fetch" task for every iterator
        for it in self.iterators:
            task = asyncio.create_task(anext(it))
            self.pending[task] = it
        return self

    async def __anext__(self) -> T:
        # Loop until we get a valid value or run out of iterators
        while self.pending:
            # 1. Check if we already have done tasks (optimization)
            # If not, wait for the FIRST one to finish.
            done_tasks = [t for t in self.pending if t.done()]

            if not done_tasks:
                done_tasks, _ = await asyncio.wait(
                    self.pending.keys(),
                    return_when=asyncio.FIRST_COMPLETED
                )

            # 2. Process the first completed task
            task = list(done_tasks)[0]
            iterator = self.pending.pop(task)

            try:
                result = task.result()

                # 3. SUCCESS: Schedule the NEXT pull for this iterator immediately
                next_task = asyncio.create_task(anext(iterator))
                self.pending[next_task] = iterator

                return result

            except StopAsyncIteration:
                # 4. FINISHED: This specific iterator is empty.
                # We do NOT schedule a new task.
                # We loop again to check the remaining iterators in self.pending.
                continue

        # If we exit the while loop, self.pending is empty -> All iterators done.
        raise StopAsyncIteration
