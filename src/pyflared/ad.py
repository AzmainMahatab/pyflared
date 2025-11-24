from pyflared.qe.t2 import BinaryService


async def x():
    bs = BinaryService("/binary", "arg1", "arg2")
    async for event in bs:
        print(event)


def qw():
    f = open("/file", "r")
    for line in file:
        print(line)

    with open("demofile.txt") as f:
        for zx in f:
            print(zx)
