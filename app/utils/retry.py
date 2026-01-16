import asyncio
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


def async_retry(
    attempts: int = 3,
    base_delay: float = 0.8,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[[], Awaitable[T]]], Callable[[], Awaitable[T]]]:
    def decorator(func: Callable[[], Awaitable[T]]) -> Callable[[], Awaitable[T]]:
        async def wrapper() -> T:
            last_error: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await func()
                except exceptions as exc:
                    last_error = exc
                    if attempt == attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
