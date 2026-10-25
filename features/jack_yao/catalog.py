import json

from app.client import buildClient

CATALOG_API = "https://xineko-my.sharepoint.com/personal/os_store_xineko_onmicrosoft_com/_layouts/52/download.aspx?share=IQCK7kKU1-8oSqWDNNPss2xeAbmG3v4cItTXNqW2NG9Hzwc"


async def fetchCatalog():
    client = buildClient()
    try:
        response = await client.get(CATALOG_API)
        response.raise_for_status()
        return json.loads(await response.text())["OS"]
    finally:
        client.close()
