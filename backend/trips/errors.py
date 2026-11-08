from rest_framework.views import exception_handler


def handler(exc, context):
    """Return every error as {"error": "message"}."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
    elif isinstance(detail, dict):
        message = "; ".join(f"{k}: {' '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in detail.items())
    else:
        message = str(detail)
    response.data = {"error": message}
    return response
