"""Issue a private, expiring Spotify invitation. Never commit or log the generated URL."""
import argparse
import hashlib
import re
import secrets
import time
from urllib.parse import urlencode

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="short id without spaces, e.g. alice")
    parser.add_argument("--name", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--table", default="sfw-dev-connect")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", args.user_id):
        parser.error("--user-id must use 2-40 lowercase letters, digits or hyphens")
    token = secrets.token_urlsafe(32)
    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    table.put_item(Item={"id": "INVITE#" + hashlib.sha256(token.encode()).hexdigest(),
                         "user_id": args.user_id, "display_name": args.name,
                         "expires_at": int(time.time()) + 7 * 86400})
    print(args.base_url.rstrip("/") + "/connect?" + urlencode({"invite": token}))


if __name__ == "__main__":
    main()
