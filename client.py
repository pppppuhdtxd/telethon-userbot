# client.py
from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.network.connection import ConnectionTcpFull
from config import API_ID, API_HASH, SESSION_NAME, PROXY_FILE
import os
from urllib.parse import urlparse, parse_qs
import base64
import asyncio

def extract_proxy_params(proxy_url):
    """
    Extracts server, port, and secret from a Telegram proxy URL.
    Handles both hex secrets and base64 encoded secrets.
    Returns (server, port, secret) or None if invalid.
    """
    parsed = urlparse(proxy_url)
    if parsed.scheme != 'https' or parsed.netloc != 't.me' or parsed.path != '/proxy':
        return None

    query = parse_qs(parsed.query)
    server = query.get('server', [None])[0]
    port_str = query.get('port', [None])[0]
    secret_encoded = query.get('secret', [None])[0]

    if not server or not port_str or not secret_encoded:
        return None

    try:
        port = int(port_str)
    except ValueError:
        return None

    # Decode secret if it's URL-encoded or base64
    if secret_encoded.startswith(('dd', 'ee')) and all(c in '0123456789abcdefABCDEF' for c in secret_encoded):
        secret_bytes = bytes.fromhex(secret_encoded)
    else:
        try:
            secret_decoded_raw = secret_encoded.replace('%3D', '=')
            secret_bytes = base64.urlsafe_b64decode(secret_decoded_raw)
        except Exception:
            return None

    secret = secret_bytes.hex()
    return server, port, secret


async def test_single_proxy(server, port, secret, semaphore):
    """
    Tests a single proxy quietly.
    Uses a semaphore to limit concurrent connections.
    """
    async with semaphore:
        temp_client = TelegramClient(
            SESSION_NAME,
            API_ID,
            API_HASH,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(server, port, secret),
            timeout=3  # کاهش زمان اتصال
        )
        try:
            await temp_client.connect()
            await temp_client.disconnect()
            return server, port, secret
        except Exception:
            return None


async def find_working_proxy_async(proxy_list):
    """
    Takes a list of (server, port, secret) tuples and tests them concurrently.
    Returns the first one that works, or None if all fail.
    """
    semaphore = asyncio.Semaphore(20)  # افزایش تعداد تست همزمان
    tasks = [
        asyncio.create_task(test_single_proxy(server, port, secret, semaphore))
        for server, port, secret in proxy_list
    ]

    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result:
            # Cancel remaining tasks as soon as one succeeds
            pending = [t for t in tasks if not t.done()]
            for p in pending:
                p.cancel()
            return result

    return None


async def load_and_test_proxies_from_file():
    """
    Loads proxy URLs from the specified file, extracts parameters,
    and finds the first working proxy using concurrent testing.
    Returns (server, port, secret) or None.
    """
    if not os.path.exists(PROXY_FILE):
        return None

    with open(PROXY_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    proxy_tuples = []
    for line in lines:
        url = line.strip()
        if not url or not url.startswith('https://t.me/proxy'):
            continue

        proxy_info = extract_proxy_params(url)
        if proxy_info:
            proxy_tuples.append(proxy_info)

    if not proxy_tuples:
        return None

    print(f"[DEBUG] Testing {len(proxy_tuples)} proxies...")
    return await find_working_proxy_async(proxy_tuples)


# --- MAIN SYNC WRAPPER ---
def initialize_client_with_proxy():
    """
    Synchronous wrapper to run the async proxy finder and initialize the client.
    """
    proxy_info = asyncio.run(load_and_test_proxies_from_file())

    # Set up connection based on proxy availability
    if proxy_info:
        server, port, secret = proxy_info
        connection_class = ConnectionTcpMTProxyRandomizedIntermediate
        connection_args = {'proxy': (server, port, secret)}
        print(f"[DEBUG] Using proxy: {server}:{port}")
    else:
        connection_class = ConnectionTcpFull
        connection_args = {}
        print("[DEBUG] No valid proxy found, using direct connection.")

    # Initialize the main client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, connection=connection_class, **connection_args)

    if proxy_info:
        print("[DEBUG] TelegramClient initialized with MTProxy.")
    else:
        print("[DEBUG] TelegramClient initialized with default connection.")

    return client


# --- INITIALIZATION ---
client = initialize_client_with_proxy()