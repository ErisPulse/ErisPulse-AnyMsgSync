from ErisPulse import sdk
import asyncio

async def main():
    sdk.init()
    try:
        await sdk.adapter.startup()
        if hasattr(sdk, "AnyMsgSync"):
            await sdk.AnyMsgSync.start()
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await sdk.adapter.shutdown()


if __name__ == "__main__":
    asyncio.run(main())