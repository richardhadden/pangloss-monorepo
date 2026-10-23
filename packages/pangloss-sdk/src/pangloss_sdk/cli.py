"""`pangloss-sdk`: log in to a Pangloss server and keep the login, log out, and see where you are.

    pangloss-sdk login https://pangloss.example.org     # asks for a username and password
    pangloss-sdk login URL --token                      # keeps a personal access token instead
    pangloss-sdk status [URL]
    pangloss-sdk logout [URL]

The password is never kept: a **refresh token** is (see `pangloss_sdk.credentials` for where).
"""

import argparse
import getpass
import os
import sys
from typing import Any

import httpx2 as httpx

from pangloss_sdk import credentials
from pangloss_sdk.auth import terminal_prompt

DEFAULT_ENV = "PANGLOSS_URL"


def server_url(given: str | None) -> str:
    url = given or os.environ.get(DEFAULT_ENV)
    if not url:
        raise SystemExit(f"Which server? Give its URL, or set {DEFAULT_ENV}")
    return url.rstrip("/")


def client_for(url: str, transport: Any = None) -> httpx.Client:
    return httpx.Client(base_url=url, timeout=30, transport=transport)


def login(args: argparse.Namespace, transport: Any, prompt: Any, out: Any) -> int:
    url = server_url(args.url)
    with client_for(url, transport) as http:
        if args.token:
            token = getpass.getpass("Personal access token: ").strip()
            me = http.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
            if me.status_code != 200:
                print("That token was not accepted", file=sys.stderr)
                return 1
            username = me.json()["username"]
            where = credentials.save(url, {"token": token, "username": username})
            print(f"Logged in to {url} as {username} with a token; kept in {where}", file=out)
            return 0

        username = args.username
        for _ in range(3):
            username, password = (prompt or terminal_prompt)(url, username)
            response = http.post(
                "/api/users/token", data={"username": username, "password": password}
            )
            if response.status_code == 200:
                break
            if response.status_code != 401:
                print(f"The server answered {response.status_code}", file=sys.stderr)
                return 1
            print("Incorrect username or password", file=sys.stderr)
        else:
            return 1
        where = credentials.save(
            url, {"refresh_token": response.json()["refresh_token"], "username": username}
        )
        print(f"Logged in to {url} as {username}; kept in {where}", file=out)
        print("(the password is not kept: only a token that `logout` revokes)", file=out)
    return 0


def logout(args: argparse.Namespace, transport: Any, prompt: Any, out: Any) -> int:
    url = server_url(args.url)
    stored = credentials.load(url)
    if stored is None:
        print(f"There is no login kept for {url}", file=out)
        return 0
    if "refresh_token" in stored:
        try:
            with client_for(url, transport) as http:
                http.post("/api/users/token/revoke", json={"refresh_token": stored["refresh_token"]})
            revoked = "revoked on the server, and "
        except httpx.TransportError:
            revoked = "NOT revoked on the server (it could not be reached), but "
    else:
        revoked = "(a personal access token is revoked where it was made: `DELETE /api/users/me/tokens/<id>`) "
    credentials.forget(url)
    print(f"Logged out of {url}: {revoked}forgotten here", file=out)
    return 0


def status(args: argparse.Namespace, transport: Any, prompt: Any, out: Any) -> int:
    url = server_url(args.url)
    stored = credentials.load(url)
    print(f"Server: {url}", file=out)
    if stored is None:
        print("Login: none kept (a login is asked for when needed)", file=out)
    else:
        kind = "a personal access token" if "token" in stored else "a refresh token"
        print(f"Login: {stored.get('username', '?')}, with {kind}", file=out)
    try:
        with client_for(url, transport) as http:
            version = http.get("/api/sdk/version")
            if version.status_code == 200:
                body = version.json()
                print(f"SDK on the server: {body['distribution']} {body['version']}", file=out)
            else:
                print("SDK on the server: none built", file=out)
            if stored and "token" in stored:
                headers = {"Authorization": f"Bearer {stored['token']}"}
                me = http.get("/api/users/me", headers=headers)
                print("Token: " + ("accepted" if me.status_code == 200 else "NOT accepted"), file=out)
            elif stored and "refresh_token" in stored:
                refreshed = http.post(
                    "/api/users/token/refresh", json={"refresh_token": stored["refresh_token"]}
                )
                print("Login: " + ("still good" if refreshed.status_code == 200 else "NOT good any more (log in again)"), file=out)
    except httpx.TransportError as error:
        print(f"The server could not be reached: {error}", file=sys.stderr)
        return 1
    return 0


def parser() -> argparse.ArgumentParser:
    main_parser = argparse.ArgumentParser(prog="pangloss-sdk", description=__doc__.split("\n\n")[0])
    commands = main_parser.add_subparsers(dest="command", required=True)

    login_parser = commands.add_parser("login", help="Log in and keep the login")
    login_parser.add_argument("url", nargs="?", help=f"The server (or set {DEFAULT_ENV})")
    login_parser.add_argument("--username", help="A username to suggest")
    login_parser.add_argument("--token", action="store_true", help="Keep a personal access token")
    login_parser.set_defaults(run=login)

    logout_parser = commands.add_parser("logout", help="Revoke the kept login and forget it")
    logout_parser.add_argument("url", nargs="?")
    logout_parser.set_defaults(run=logout)

    status_parser = commands.add_parser("status", help="Where you are logged in, and the SDK there")
    status_parser.add_argument("url", nargs="?")
    status_parser.set_defaults(run=status)
    return main_parser


def main(argv: list[str] | None = None, transport: Any = None, prompt: Any = None, out: Any = None) -> int:
    args = parser().parse_args(argv)
    return args.run(args, transport, prompt, out or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
