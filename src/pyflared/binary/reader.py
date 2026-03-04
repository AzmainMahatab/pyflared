import asyncio
from collections.abc import AsyncIterator

from pyflared.binary.writer import ProcessWriter
from pyflared.shared.types import ProcessOutput, StreamChunker, Responder, OutputChannel, ChunkSignal
from pyflared.utils.asyncio.async_Iterable import yield_from_async
from pyflared.utils.asyncio.merge import merge_async_iterators
from pyflared.utils.asyncio.wait import safe_awaiter
from pyflared.utils.iterable import not_none_generator


async def reader_chunker(
        stream: asyncio.StreamReader, output_channel: OutputChannel,
        chunker: StreamChunker) -> AsyncIterator[bytes]:
    while True:
        chunk = await safe_awaiter(chunker(stream, output_channel))
        match chunk:
            case bytes():
                yield chunk
            case ChunkSignal.SKIP:
                continue
            case ChunkSignal.EOF:
                break


@yield_from_async
async def combined_output(
        process_writer: ProcessWriter,
        initial_input: str | None = None,
        chunker: StreamChunker | None = None,
        responders: list[Responder] | None = None
):
    if initial_input:
        await process_writer.write(initial_input)

    async def channel_tagger(stream: asyncio.StreamReader, channel: OutputChannel):
        chunked_source = chunker and reader_chunker(stream, channel, chunker) or stream
        async for chunk in chunked_source:
            await process_writer.write_from_responders(chunk, channel, responders or [])
            yield ProcessOutput(chunk, channel)

    sources = not_none_generator(
        (sout := process_writer.process.stdout) and channel_tagger(sout, OutputChannel.STDOUT),
        (serr := process_writer.process.stderr) and channel_tagger(serr, OutputChannel.STDERR)
    )
    return merge_async_iterators(*sources)
