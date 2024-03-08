"""
MIT License

Copyright (c) 2024 jespk77

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json, logging, os, time
import aiohttp

def build_parameters(parameters):
    return '&'.join([f"{key}={value}" for key, value in parameters.items()])

def parse_parameters(parameter_uri):
    return {line[0]: line[1] for line in [parameter.split("=") for parameter in parameter_uri.split("&")]}

CLIENT_DATA_FILE = "client.json"
if not os.path.isfile(CLIENT_DATA_FILE): raise ValueError("Missing Twitch application data")

with open(CLIENT_DATA_FILE, "r") as file: client_data = json.load(file)
for key, value in client_data.items():
    # ensure all client data has been filled in
    if "TODO:" in value: raise ValueError(f"'{key}' in {CLIENT_DATA_FILE} needs to be filled in")

logging.getLogger("twitch.auth").setLevel("INFO")
log = logging.getLogger("twitch.auth")

class OAuth:
    client_id = client_data["Client-ID"]
    client_secret = client_data["Client-Secret"]
    client_uri = client_data["RedirectURI"]

    def __init__(self, username, cache_file, scope=None):
        self._username = username
        self._cache_file = cache_file
        self._scope = scope
        self._auth = self._user_data = None

    async def load(self):
        try:
            with open(self._cache_file, "r") as file: data = json.load(file)
            self._auth, self._user_data = data.get("auth"), data.get("user")
            if not self._user_data: await self._get_user_data()
            if self._check_scope(): return
        except FileNotFoundError: pass

        log.info("No valid authorization found, starting (re)authorization process")
        await self._invalidate()
        await self._request_auth()
        await self._get_user_data()

    def _save_file(self):
        data = {
            "auth": self._auth,
            "user": self._user_data
        }

        with open(self._cache_file, "w") as file: json.dump(data, file)

    def _check_scope(self):
        # no scope provided, assume scope is right
        if self._scope is None: return True

        for s in self._scope:
            if s not in self._auth["scope"]:
                log.warning(f"Missing scope: {s}")
                return False
        return True

    auth_request_url = "https://id.twitch.tv/oauth2/authorize?{parameters}&force_verify=true"
    async def _request_auth(self):
        if self._scope is None: raise ValueError("Cannot request authorization when no scope is provided")

        import random, string, webbrowser
        state = ''.join([random.choice(string.ascii_letters) for _ in range(30)])
        parameters = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.client_uri,
            "scope": '+'.join(self._scope),
            "state": state
        }

        url = self.auth_request_url.format(parameters=build_parameters(parameters))
        log.info(f"Opening {url} for signing in...")
        webbrowser.open(url)
        uri = input("Enter the page you were redirected to: ")

        uri = uri.split("?", maxsplit=1)
        if len(uri) == 2 and uri[0] == self.client_uri:
            parameters = parse_parameters(uri[1])
            if parameters["state"] == state:
                parameters["scope"] = self._scope
                log.debug("Authorized, getting token...")
                await self._get_token(parameters["code"])
            else: log.error("Not authorized: invalid state")
        else: log.error("Not authorized: invalid uri")

    auth_get_url = "https://id.twitch.tv/oauth2/token?{parameters}"
    async def _get_token(self, code=None, refresh_token=None):
        parameters = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code" if code else "refresh_token",
            "redirect_uri": self.client_uri,
        }

        if code is not None: parameters["code"] = code
        elif refresh_token is not None: parameters["refresh_token"] = refresh_token
        else: raise ValueError("No code and no refresh token specified")

        async with aiohttp.ClientSession() as session:
            resp = await session.post(self.auth_get_url.format(parameters=build_parameters(parameters)))
            if resp.ok:
                self._auth = await resp.json()
                self._auth["expiration_time"] = time.time() + self._auth["expires_in"]
                self._save_file()
                log.debug("Authorization complete")
                return True

        log.error("Failed to get token:", resp.content)
        return False

    revoke_url = "https://id.twitch.tv/oauth2/revoke?{parameters}"
    async def _invalidate(self):
        parameters = {
            "client_id": self.client_id,
            "token": await self.get_code()
        }

        if not parameters["token"]: return
        async with aiohttp.ClientSession() as session:
            resp = await session.post(self.revoke_url.format(parameters=build_parameters(parameters)))
            if resp.ok:
                log.debug("Authorization invalidated")
                try: os.remove(self._cache_file)
                except FileNotFoundError: pass
                self._auth = None
            else: log.error("Failed to invalidate token:", resp.content)

    async def _check_auth(self):
        if self._auth is not None:
            if time.time() > self._auth["expiration_time"]:
                return await self._get_token(refresh_token=self._auth["refresh_token"])
            return True
        return False

    user_info_url = "https://api.twitch.tv/helix/users?login={username}"
    async def _get_user_data(self):
        if code := await self.get_code():
            async with aiohttp.ClientSession() as session:
                resp = await session.get(self.user_info_url.format(username=self._username),
                                         headers={"Authorization": f"Bearer {code}", "Client-Id": self.client_id})
                if resp.ok:
                    self._user_data = (await resp.json())["data"][0]
                    self._save_file()
                    log.debug("Collecting user information complete")
                    return True
        return False

    @property
    def user_name(self): return self._username
    channel_name = user_name
    @property
    def display_name(self): return self._user_data["display_name"]
    @property
    def user_id(self): return self._user_data["id"]
    channel_id = user_id

    async def get_code(self):
        """
            Get a code to use for making API requests
            Automatically refreshes the code when it expires
        """
        if await self._check_auth(): return self._auth["access_token"]

    async def invalidate(self):
        """
            Invalidate the use of this authorization
            The instance cannot be used to make further requests: the authorization process will restart
        """
        await self._invalidate()