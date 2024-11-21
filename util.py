from functools import wraps
from time import perf_counter


def timer(func):
    @wraps(func)  # Preserves the metadata of the original function
    def wrapper(*args, **kwargs):
        start_time = perf_counter()
        result = func(*args, **kwargs)
        end_time = perf_counter()
        print(
            f"Function {func.__name__} took {end_time - start_time:.6f} seconds to run."
        )
        return result

    return wrapper
