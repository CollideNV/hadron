import httpx
try:
    raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
except Exception as e:
    exc_type = type(e).__name__
    exc_str = str(e).lower()
    print("Type:", exc_type)
    print("Str:", exc_str)
