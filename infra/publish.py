"""Publish the portfolio files to the stack and print the public URL."""
import hashlib
import json
import mimetypes
import time
from pathlib import Path

import boto3

REGION = "ap-northeast-2"
STACK = "yt-cloud-db-portfolio"
SITE = Path(__file__).resolve().parents[1] / "site"


def outputs():
    cloud = boto3.client("cloudformation", region_name=REGION)
    stack = cloud.describe_stacks(StackName=STACK)["Stacks"][0]
    if stack["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
        raise RuntimeError("Stack status: " + stack["StackStatus"])
    return {v["OutputKey"]: v["OutputValue"] for v in stack["Outputs"]}


def public_config(resources):
    appsync = boto3.client("appsync", region_name=REGION)
    keys = appsync.list_api_keys(apiId=resources["GraphId"])["apiKeys"]
    current = max(keys, key=lambda key: key["expires"])
    if current["expires"] <= time.time():
        raise RuntimeError("The public read key has expired")
    return dict(apiUrl=resources["GraphUrl"], authUrl=resources["AuthUrl"],
                clientId=resources["ClientId"], readKey=current["id"])


def main():
    resources = outputs()
    s3 = boto3.client("s3", region_name=REGION)
    files = {p.relative_to(SITE).as_posix(): p.read_bytes()
             for p in SITE.rglob("*") if p.is_file() and p.name != "config.json"}
    files["config.json"] = json.dumps(public_config(resources)).encode()
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if name.endswith(".js"):
            mime = "text/javascript"
        if mime.startswith("text/") or mime == "application/json":
            mime += "; charset=utf-8"
        s3.put_object(Bucket=resources["Bucket"], Key=name, Body=data,
                      ContentType=mime, CacheControl="max-age=60, must-revalidate")
        digest.update(name.encode() + hashlib.sha256(data).digest())
    cloudfront = boto3.client("cloudfront")
    cloudfront.create_invalidation(DistributionId=resources["DistributionId"],
        InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]},
                           "CallerReference": digest.hexdigest()})
    print(f"Published {len(files)} files to {resources['Url']}", flush=True)


if __name__ == "__main__":
    main()
