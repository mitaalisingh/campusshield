"""AWS Lambda entry point behind a Function URL: serves the dashboard at / and the API under /api/."""
import json
import os

import api

HERE = os.path.dirname(__file__)


def handler(event, context):
    path = event.get("rawPath", "/")
    if path.startswith("/api/"):
        code, body = api.handle(path, event.get("queryStringParameters") or {})
        return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}
    with open(os.path.join(HERE, "web", "index.html"), encoding="utf-8") as f:
        return {"statusCode": 200, "headers": {"Content-Type": "text/html; charset=utf-8"}, "body": f.read()}
