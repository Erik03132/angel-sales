
from mcp.bitrix_mcp import BitrixMCP

b = BitrixMCP()
# To get users
data = b._call("user.get", {})
users = data.get("result", [])
for u in users:
    print(f"ID: {u.get('ID')}, NAME: {u.get('NAME')} {u.get('LAST_NAME')}")
