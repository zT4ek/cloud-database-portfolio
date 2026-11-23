"""Exercise the deployed guestbook with temporary, isolated test records."""
import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import boto3
from publish import REGION, outputs


def get(url):
    with urlopen(url, timeout=20) as response:
        return response.read()


def verify():
    resources = outputs()
    base = resources["Url"]
    for path in ["/", "/about.html", "/projects.html", "/project.html?id=2122",
                 "/contact.html", "/guestbook.html"]:
        assert b'lang="ko"' in get(base + path), path
    projects = json.loads(get(base + "/projects.json"))
    assert {p["id"] for p in projects} == {"2122", "kaist", "ham", "capstone"}
    for p in projects:
        assert get(base + "/art/" + p["id"] + ".png").startswith(b"\x89PNG")
    assert "dudxor789456@naver.com" in get(base + "/contact.html").decode()
    print("PASS six HTTPS pages, four project illustrations and contact email", flush=True)
    try:
        get(f"https://{resources['Bucket']}.s3.{REGION}.amazonaws.com/index.html")
    except HTTPError as error:
        assert error.code == 403, error.code
    else:
        raise AssertionError("The S3 origin permits anonymous access")
    print("PASS S3 origin denies direct anonymous access", flush=True)
    config = json.loads(get(base + "/config.json"))

    def graph(query, variables=None, token=None):
        header = {"Authorization": token} if token else {"x-api-key": config["readKey"]}
        header["Content-Type"] = "application/json"
        request = Request(config["apiUrl"], headers=header,
                          data=json.dumps(dict(query=query, variables=variables or {})).encode())
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (401, 403):
                raise
            return {"errors": [{"errorType": "Unauthorized"}]}

    read = "{entries{items{key mine nickname message} cursor}}"
    write = "mutation W($n:String!,$m:String!){write(nickname:$n,message:$m){key mine}}"
    remove = "mutation R($k:String!){remove(key:$k)}"
    probe = {"n":"검증용", "m":"배포 동작 확인"}
    public = graph(read)
    assert "errors" not in public, public.get("errors")
    assert "errors" in graph(write, probe)
    print("PASS anonymous read and sign-in requirement for posting", flush=True)
    cognito = boto3.client("cognito-idp", region_name=REGION)
    pool = resources["PoolId"]
    users = []
    owned = []

    def test_user():
        email = "qa-" + uuid4().hex + "@example.invalid"
        password = secrets.token_urlsafe(30) + "aA1!"
        attributes = [dict(Name="email", Value=email), dict(Name="email_verified", Value="true")]
        user = cognito.admin_create_user(UserPoolId=pool, Username=email,
            UserAttributes=attributes, MessageAction="SUPPRESS")["User"]["Username"]
        users.append(user)
        cognito.admin_set_user_password(UserPoolId=pool, Username=user,
                                        Password=password, Permanent=True)
        result = cognito.initiate_auth(ClientId=config["clientId"], AuthFlow="USER_PASSWORD_AUTH",
                                       AuthParameters={"USERNAME": email, "PASSWORD": password})
        return result["AuthenticationResult"]["IdToken"]

    try:
        first, second = test_user(), test_user()
        assert "errors" in graph(write, dict(n="x", m="body"), first)
        posted = graph(write, probe, first)
        assert "errors" not in posted, posted.get("errors")
        row = posted["data"]["write"]
        key = row["key"]
        owned.append(key)
        assert row["mine"] is True
        for token, expected in [(first, True), (second, False), (None, False)]:
            view = graph(read, token=token)
            assert "errors" not in view, view.get("errors")
            matching = [x for x in view["data"]["entries"]["items"] if x["key"] == key]
            assert len(matching) == 1 and matching[0]["mine"] == expected
        assert "errors" in graph(remove, {"k": key}, second)
        assert "errors" in graph(remove, {"k": key})
        deleted = graph(remove, {"k": key}, first)
        assert deleted.get("data", {}).get("remove") is True, deleted.get("errors")
        owned.remove(key)
        assert key not in [x["key"] for x in graph(read)["data"]["entries"]["items"]]
        print("PASS Cognito sign-in, input validation, create, owner-only delete and removal", flush=True)
        for index in range(11):
            result = graph(write, dict(n="쪽확인", m=f"페이지 검증 {index + 1}"), first)
            assert "errors" not in result, result.get("errors")
            owned.append(result["data"]["write"]["key"])
        query_page = "query P($before:String){entries(before:$before){items{key} cursor}}"
        before = None
        seen = []
        while True:
            page = graph(query_page, {"before": before})["data"]["entries"]
            keys = [x["key"] for x in page["items"]]
            assert len(keys) <= 10 and keys == sorted(keys, reverse=True)
            if before:
                assert all(key < before for key in keys)
            seen.extend(keys)
            before = page["cursor"]
            if not before or set(owned).issubset(seen):
                break
            assert len(keys) == 10 and before == keys[-1]
        assert set(owned).issubset(seen) and len(seen) == len(set(seen))
        print("PASS newest-first pagination, ten rows per page, no repeated entry", flush=True)
    finally:
        table = boto3.resource("dynamodb", region_name=REGION).Table(resources["Table"])
        for key in owned:
            table.delete_item(Key={"pk": "GUESTBOOK", "sk": key})
        for user in users:
            cognito.admin_delete_user(UserPoolId=pool, Username=user)
    print("PASS temporary users and test entries removed", flush=True)


if __name__ == "__main__":
    verify()
