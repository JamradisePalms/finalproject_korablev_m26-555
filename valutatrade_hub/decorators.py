from functools import wraps

from valutatrade_hub.logging_config import get_logger


def log_action(verbose: bool = False):
    def decorator(func):
        @wraps(func)
        def wrapper(user, currency_code, amount):
            logger = get_logger()
            action = func.__name__.upper()
            user_id = user.user_id if user is not None else None
            context = (
                f"{action} user_id={user_id!r} currency={currency_code!r} "
                f"amount={amount!r}"
            )
            try:
                result = func(user, currency_code, amount)
            except Exception as error:
                logger.info(
                    "%s rate=None base='USD' result=ERROR error_type=%s error_message=%r",
                    context,
                    type(error).__name__,
                    str(error),
                )
                raise

            details = ""
            if verbose:
                details = f" before={result['before']} after={result['after']}"
            logger.info(
                "%s rate=%s base=%r result=OK%s",
                context,
                result["rate"],
                result["base"],
                details,
            )
            return result

        return wrapper

    return decorator
