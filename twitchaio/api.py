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

import datetime, time
import asyncio
from collections.abc import Iterable

import twitchaio

import logging
import aiohttp

log = logging.getLogger("twitchaio.api")

class APIError(Exception):
    def __init__(self, url: str, content: str, status_code: int):
        Exception.__init__(self)
        self._url = url
        self._content = content
        self._status_code = status_code

    @property
    def url(self): return self._url
    @property
    def content(self): return self._content
    @property
    def status_code(self): return self._status_code

    def __str__(self): return f"Twitch API request to {self.url} failed with code {self.status_code}:\n{self.content}"

class APITokenRefreshFailed(Exception):
    def __str__(self): return "Failed to refresh API token"

class APIArgumentError(Exception):
    def __init__(self, message: str):
        Exception.__init__(self)
        self._message = message

    def __str__(self): return self._message


class API:
    cache_threshold = 60

    def __init__(self, channel_auth : twitchaio.OAuth, user_auth : twitchaio.OAuth=None):
        """
            The main object for interacting with the Twitch API
            Requires authorization for channel operations and user operations, with valid scope depending on the operation
            See https://dev.twitch.tv/docs/api/reference/ for more information
        """
        if user_auth is None: user_auth = channel_auth
        self._channel_auth, self._user_auth = channel_auth, user_auth
        self._headers = {"Content-Type":"application/json"}

        self._cache = {}
        self._session = aiohttp.ClientSession(headers={"Client-ID": self._channel_auth.client_id})

    async def __aenter__(self):
        await self._channel_auth.load()
        await self._user_auth.load()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.sleep(.25) # allow open connections to close
        await self._session.close()

    @staticmethod
    def timestamp_to_datetime(date_string : str):
        """ Convert RFC3339 timestamp to datetime object """
        date_string = date_string[:-1]
        try: return datetime.datetime.fromisoformat(date_string)
        except ValueError: pass
        return datetime.datetime.fromisoformat(date_string + "0")

    @staticmethod
    def timestamp_from_time(date: time.time):
        """ Convert time.time to RFC3339 timestamp """
        return API.timestamp_from_datetime(datetime.datetime.fromtimestamp(date))

    @staticmethod
    def timestamp_from_datetime(date: datetime.datetime):
        """ Convert datetime.datetime to RFC3339 timestamp """
        return date.strftime('%Y-%m-%dT%H:%M:%SZ')

    @staticmethod
    def convert_to_iterable(item):
        if not isinstance(item, Iterable): return item,
        else: return item

    def _check_cache(self, key):
        data = self._cache.get(key)
        if data is not None and time.time() - data[0] < self.cache_threshold:
            log.debug("Cache threshold not expired: providing cached result")
            return data[1]

    def _get_auth_header(self, code: str):
        self._headers["Authorization"] = f"Bearer {code}"
        return self._headers

    async def _get(self, auth: twitchaio.OAuth, url: str, params: dict=None, body: dict=None, cache: bool=True, pagination=False):
        log.debug(f"[GET] {url}: {{parameters={params}, body={body}}}")
        data = await self._perform_action(self._session.get, auth, url, params, body, cache and not pagination)
        while pagination:
            try: cursor = data["pagination"]["cursor"]
            except KeyError: break
            if params is None: params = {"after": cursor}
            else: params["after"] = cursor
            items = data["data"]
            data = await self._perform_action(self._session.get, auth, url, params, body)
            data["data"].extend(items)
        return data

    async def _put(self, auth: twitchaio.OAuth, url: str, params: dict=None, body: dict=None):
        log.debug(f"[PUT] {url}: {{parameters={params}, body={body}}}")
        return await self._perform_action(self._session.put, auth, url, params, body)

    async def _delete(self, auth: twitchaio.OAuth, url: str, params: dict=None, body: dict=None):
        log.debug(f"[DELETE] {url}: {{parameters={params}, body={body}}}")
        return await self._perform_action(self._session.delete, auth, url, params, body)

    async def _patch(self, auth: twitchaio.OAuth, url: str, params: dict=None, body: dict=None):
        log.debug(f"[PATCH] {url}: {{parameters={params}, body={body}}}")
        return await self._perform_action(self._session.patch, auth, url, params, body)

    async def _post(self, auth: twitchaio.OAuth, url: str, params: dict=None, body: dict=None):
        log.debug(f"[POST] {url}: {{parameters={params}, body={body}}}")
        return await self._perform_action(self._session.post, auth, url, params, body)

    async def _perform_action(self, method, auth, url, params, body, cache=False):
        if cache and (cached_data := self._check_cache(url)): return cached_data

        code = await auth.get_code()
        if code is None: raise APITokenRefreshFailed()

        header = self._get_auth_header(code)
        response = await method(url, json=body, params=params, headers=header)
        if response.ok:
            try: body = await response.json()
            except aiohttp.ContentTypeError: body = None
            if cache: self._cache[url] = time.time(), body
            return body
        else: raise APIError(url, await response.json(), response.status)
    # =============================================================================================

    manage_commercial_url = "https://api.twitch.tv/helix/channels/commercial"
    async def start_commercial(self, length: int):
        if length > 180: raise ValueError("Commercial length cannot be longer than 180 seconds")
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "length": length
        }
        return await self._post(self._channel_auth, self.manage_commercial_url, body=data)

    bits_leaderboard_url = "https://api.twitch.tv/helix/bits/leaderboard"
    async def get_bits_leaderboard(self, count=10, period="all", started_at: datetime.datetime=None, user_id=None):
        params = {
            "count": count,
            "period": period
        }

        if started_at: params["started_at"] = self.timestamp_from_datetime(started_at)
        if user_id: params["user_id"] = user_id
        return await self._get(self._channel_auth, self.bits_leaderboard_url, params=params)

    cheermotes_url = "https://api.twitch.tv/helix/bits/cheermotes"
    async def get_cheermotes(self, broadcaster_id: str=None):
        params = {
            "broadcaster_id": broadcaster_id
        }
        return await self._get(self._user_auth, self.cheermotes_url, params=params)

    channel_information_url = "https://api.twitch.tv/helix/channels"
    async def get_channel_information(self, broadcaster_id: str=None):
        params = {
            "broadcaster_id": broadcaster_id if broadcaster_id else self._channel_auth.channel_id
        }
        return await self._get(self._user_auth, self.channel_information_url, params=params)

    async def set_channel_information(self, game_id: str=None, language: str=None, title: str=None, delay: int=None, tags=None):
        params = {
            "broadcaster_id": self._channel_auth.channel_id
        }

        data = {}
        if game_id: data["game_id"] = game_id
        if language: data["broadcaster_language"] = language
        if title: data["title"] = title
        if delay: data["delay"] = delay
        if tags: data["tags"] = self.convert_to_iterable(tags)
        return await self._patch(self._channel_auth, self.channel_information_url, params=params, body=data)

    follow_url = "https://api.twitch.tv/helix/channels/followed"
    async def get_followed_channels(self, broadcaster_id=None, user_id=None, count=10, cache=True, pagination=True):
        params = {
            "broadcaster_id": broadcaster_id if broadcaster_id else self._channel_auth.channel_id,
            "first": count
        }

        if user_id: params["user_id"] = user_id
        return await self._get(self._channel_auth, self.follow_url, params=params, cache=cache, pagination=pagination)

    followers_url = "https://api.twitch.tv/helix/channels/followers"
    async def get_channel_followers(self, user_id=None, count=10, cache=True, pagination=True):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "first": count
        }

        if user_id: params["user_id"] = user_id
        return await self._get(self._user_auth, self.followers_url, params=params, cache=cache, pagination=pagination)

    manage_rewards_url = "https://api.twitch.tv/helix/channel_points/custom_rewards"
    async def add_reward(self, title: str, cost: int, prompt="", enabled=True, background_color: str=None, need_user_input=False,
                         max_per_stream=0, max_per_user=0, cooldown=0, skip_queue=False):
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "title": title,
            "cost": cost,
        }

        if prompt: data["prompt"] = prompt
        if not enabled: data["is_enabled"] = enabled
        if background_color: data["background_color"] = background_color
        if need_user_input: data["is_user_input_required"] = need_user_input
        if max_per_stream > 0:
            data["is_max_per_stream_enabled"] = True
            data["max_per_stream"] = max_per_stream
        if max_per_user > 0:
            data["is_max_per_user_per_stream_enabled"] = True
            data["max_per_user_per_stream"] = max_per_user
        if cooldown > 0:
            data["is_global_cooldown_enabled"] = True
            data["global_cooldown_seconds"] = cooldown
        if skip_queue: data["should_redemptions_skip_request_queue"] = skip_queue
        return await self._post(self._channel_auth, self.manage_rewards_url, body=data)

    async def edit_reward(self, reward_id: str, **kwargs):
        """ See https://dev.twitch.tv/docs/api/reference/#update-custom-reward for options """
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "id": reward_id
        }
        return await self._patch(self._channel_auth, self.manage_rewards_url, params=params, body=kwargs)

    async def delete_reward(self, reward_id: str):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "id": reward_id
        }

        return await self._delete(self._channel_auth, self.manage_rewards_url, params=params)

    async def get_reward(self, reward_id: str=None, only_manageable=False):
        data = {
            "broadcaster_id": self._channel_auth.channel_id
        }

        if reward_id: data["id"] = reward_id
        if only_manageable: data["only_manageable_rewards"] = only_manageable
        return await self._get(self._channel_auth, self.manage_rewards_url, params=data)

    manage_redemptions_url = "https://api.twitch.tv/helix/channel_points/custom_rewards/redemptions"
    async def get_redemptions(self, reward_id: str, status="UNFULFILLED", id: str=None, sort: str=None, count=20):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "reward_id": reward_id,
            "status": status,
            "first": count
        }

        if id: params["id"] = id
        if sort: params["sort"] = sort
        return await self._get(self._channel_auth, self.manage_redemptions_url, params=params)

    async def update_redemption(self, reward_id: str, redemption_id: str, status="FULFILLED"):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "reward_id": reward_id,
            "id": redemption_id
        }

        data = {
            "status": status
        }
        return await self._patch(self._channel_auth, self.manage_redemptions_url, params=params, body=data)

    chatters_url = "https://api.twitch.tv/helix/chat/chatters"
    async def get_chatters(self, count=100, pagination=True):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "moderator_id": self._user_auth.channel_id,
            "first": count
        }
        return await self._get(self._user_auth, self.chatters_url, params=params, pagination=pagination)

    channel_emote_url = "https://api.twitch.tv/helix/chat/emotes"
    async def get_channel_emotes(self, broadcaster_id=None):
        params = { "broadcaster_id": broadcaster_id if broadcaster_id else self._channel_auth.channel_id}
        return await self._get(self._user_auth, self.channel_emote_url, params=params)

    global_emote_url = "https://api.twitch.tv/helix/chat/emotes/global"
    async def get_global_emotes(self):
        return await self._get(self._user_auth, self.global_emote_url)

    emote_set_url = "https://api.twitch.tv/helix/chat/emotes/set"
    async def get_emote_sets(self, set_id: str):
        params = {
            "emote_set_id": set_id
        }

        return await self._get(self._user_auth, self.emote_set_url, params=params)

    channel_badge_url = "https://api.twitch.tv/helix/chat/badges"
    async def get_channel_badges(self):
        params = {
            "broadcaster_id": self._channel_auth.channel_id
        }

        return await self._get(self._user_auth, self.channel_badge_url, params=params)

    global_badge_url = "https://api.twitch.tv/helix/chat/badges/global"
    async def get_global_badges(self):
        return await self._get(self._user_auth, self.global_badge_url)

    chat_settings_url = "https://api.twitch.tv/helix/chat/settings"
    async def get_chat_settings(self, include_mod_options=False):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
        }

        if include_mod_options: params["moderator_id"] = self._user_auth.user_id
        return await self._get(self._user_auth, self.chat_settings_url, params=params)

    async def set_chat_settings(self, emote_only: bool=None, follower_time: int=None, chat_delay: int=None, slow_mode: int=None, subscriber_only: bool=None, unique_chat: bool=None):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "moderator_id": self._user_auth.user_id
        }

        data = {}
        if emote_only is not None: data["emote_only"] = emote_only
        if follower_time is not None:
            data["follower_mode"] = follower_time >= 0
            data["follower_mode_duration"] = max(follower_time, 0)
        if chat_delay is not None:
            data["non_moderator_chat_delay"] = chat_delay > 0
            data["non_moderator_chat_delay_duration"] = chat_delay
        if slow_mode is not None:
            data["slow_mode"] = slow_mode > 0
            data["slow_mode_wait_time"] = slow_mode
        if subscriber_only is not None: data["subscriber_only"] = subscriber_only
        if unique_chat is not None: data["unique_chat_mode"] = unique_chat

        if len(data) == 0: raise ValueError("Must specify at least one option")
        return await self._patch(self._channel_auth, self.chat_settings_url, params=params, body=data)

    announcement_url = "https://api.twitch.tv/helix/chat/announcements"
    async def send_announcement(self, message, color="primary"):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "moderator_id": self._user_auth.channel_id
        }

        data = {
            "message": message,
            "color": color
        }
        return await self._post(self._user_auth, self.announcement_url, params=params, body=data)

    shoutout_url = "https://api.twitch.tv/helix/chat/shoutouts"
    async def send_shoutout(self, channel_id):
        params = {
            "from_broadcaster_id": self._channel_auth.channel_id,
            "to_broadcaster_id": channel_id,
            "moderator_id": self._user_auth.channel_id
        }
        return await self._post(self._user_auth, self.shoutout_url, params=params)

    user_color_url = "https://api.twitch.tv/helix/chat/color"
    async def get_chat_color(self, user_id: str):
        params = {
            "user_id": user_id
        }
        return await self._get(self._user_auth, self.user_color_url, params=params, cache=True)

    async def set_chat_color(self, color: str):
        params = {
            "user_id": self._user_auth.user_id,
            "color": color
        }
        return await self._put(self._user_auth, self.user_color_url, params=params)

    clip_url = "https://api.twitch.tv/helix/clips"
    async def create_clip(self):
        params = { "broadcaster_id": self._channel_auth.channel_id}
        return await self._post(self._channel_auth, self.clip_url, params=params)

    async def get_clip(self, game_id=None, clip_id=None, limit=None, from_date: datetime.datetime=None, to_date: datetime.datetime=None, pagination=False):
        params = { }
        if clip_id is not None: params["id"] = clip_id
        elif game_id is not None: params["game_id"] = game_id
        else: params["broadcaster_id"] = self._channel_auth.channel_id

        if limit is not None: params["first"] = limit
        if from_date is not None: params["started_at"] = self.timestamp_from_datetime(from_date)
        if to_date is not None: params["ended_at"] = self.timestamp_from_datetime(to_date)
        return await self._get(self._user_auth, self.clip_url, params=params, pagination=pagination)

    manage_subscription_url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    async def create_eventsub_subscription(self, event_type: str, event_version: str, condition: str, session_id: str):
        """ Create a subscription on the websocket for event type
                event_type: str, the name of the event as specified in the documentation
                event_version: str, the version of the event as specified in the documentation
                condition: json, the condition to trigger events as specified in the documentation
                session_id: str, the session id from the websocket welcome message
            List of events: https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/
         """
        data = {
            "type": event_type,
            "version": event_version,
            "condition": condition,
            "transport":{
                "method": "websocket",
                "session_id": session_id
            }
        }
        return await self._post(self._channel_auth, self.manage_subscription_url, body=data)

    async def delete_eventsub_subscription(self, event_id: str):
        """ Delete the subscription on the websocket for event type
                event_id: str, the id parameter from the created event in add_subscription
        """
        data = {
            "id": event_id
        }
        return await self._delete(self._channel_auth, self.manage_subscription_url, body=data)

    async def get_eventsub_subscription(self, status: str=None, type: str=None, user_id: str=None, pagination=False):
        params = {}
        if status: params["status"] = status
        if type: params["type"] = type
        if user_id: params['user_id'] = user_id
        return await self._get(self._channel_auth, self.manage_subscription_url, params=params, pagination=pagination)

    game_url = "https://api.twitch.tv/helix/games"
    async def get_game(self, game_id=None, game_name=None, igdb_id=None):
        params = {}
        if game_id: params["id"] = self.convert_to_iterable(game_id)
        if game_name: params["name"] = self.convert_to_iterable(game_name)
        if igdb_id: params["igdb_id"] = self.convert_to_iterable(igdb_id)
        return await self._get(self._user_auth, self.game_url, params=params)

    banned_list_url = "https://api.twitch.tv/helix/moderation/banned"
    async def get_banned_users(self, user_id=None, limit=20, pagination=False):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "first": limit
        }

        if user_id: params["user_id"] = self.convert_to_iterable(user_id)
        return await self._get(self._user_auth, self.banned_list_url, params=params, pagination=pagination)

    ban_user_url = "https://api.twitch.tv/helix/moderation/bans"
    async def ban_user(self, user_id: str, broadcaster_id: str=None, duration: int=None, reason: str=None):
        params = {
            "broadcaster_id": broadcaster_id if broadcaster_id else self._channel_auth.channel_id,
            "moderator_id": self._user_auth.channel_id
        }

        data = {
            "user_id": user_id
        }
        if duration is not None: data["duration"] = duration
        if reason is not None: data["reason"] = reason
        return await self._post(self._user_auth, self.ban_user_url, params=params, body={"data": data})

    async def unban_user(self, user_id: str):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "moderator_id": self._user_auth.user_id,
            "user_id": user_id
        }
        return await self._delete(self._user_auth, self.ban_user_url, params=params)

    manage_message_url = "https://api.twitch.tv/helix/moderation/chat"
    async def delete_message(self, message_id: str):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "user_id": self._user_auth.user_id,
            "message_id": message_id
        }
        return await self._delete(self._user_auth, self.manage_message_url, params=params)

    manage_vip_url = "https://api.twitch.tv/helix/channels/vips"
    async def get_vips(self, user_id=None, first=None, after=None):
        params = {"broadcaster_id": self._channel_auth.channel_id}
        if user_id is not None: params["user_id"] = user_id
        if first is not None: params["first"] = first
        if after is not None: params["after"] = after

        resp = await self._get(self._channel_auth, self.manage_vip_url, params=params)
        return resp["data"]

    async def add_vip(self, user_id):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "user_id": user_id
        }
        await self._post(self._channel_auth, self.manage_vip_url, params=params)

    async def remove_vip(self, user_id):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "user_id": user_id
        }
        await self._delete(self._channel_auth, self.manage_vip_url, params=params)

    manage_poll_url = "https://api.twitch.tv/helix/polls"
    async def get_polls(self, poll_id=None, limit=20, after=None):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "limit": limit
        }
        if poll_id: params["id"] = self.convert_to_iterable(poll_id)
        if after: params["after"] = self.convert_to_iterable(after)
        return await self._get(self._user_auth, self.manage_poll_url, params=params)

    async def add_poll(self, title, choices, duration=240, channel_point_voting=False, channel_point_per_vote=0):
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "title": title,
            "choices": [{"title": choice} for choice in choices],
            "duration": duration
        }
        if channel_point_voting:
            data["channel_points_voting_enabled"] = channel_point_voting
            data["channel_points_per_vote"] = channel_point_per_vote
        return await self._post(self._user_auth, self.manage_poll_url, body=data)

    async def end_poll(self, poll_id, status="TERMINATED"):
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "id": poll_id,
            "status": status
        }
        return await self._patch(self._user_auth, self.manage_poll_url, body=data)

    prediction_url = "https://api.twitch.tv/helix/predictions"
    async def get_prediction(self, prediction_id=None, limit=20, after=None):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "limit": limit
        }

        if prediction_id: params["id"] = self.convert_to_iterable(prediction_id)
        if after: params["after"] = after
        return await self._get(self._channel_auth, self.prediction_url, params=params)

    async def start_prediction(self, title, outcomes, time_window=120):
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "title": title,
            "outcomes": [{"title": outcome} for outcome in outcomes],
            "prediction_window": time_window
        }
        return await self._post(self._channel_auth, self.prediction_url, body=data)

    async def resolve_prediction(self, prediction_id, status, winning_outcome_id=None):
        data = {
            "broadcaster_id": self._channel_auth.channel_id,
            "id": prediction_id,
            "status": status
        }

        if winning_outcome_id is not None: data["winning_outcome_id"] = winning_outcome_id
        return await self._patch(self._channel_auth, self.prediction_url, body=data)

    raid_url = "https://api.twitch.tv/helix/raids"
    async def start_raid(self, to_id):
        params = {
            "from_broadcaster_id": self._channel_auth.channel_id,
            "to_broadcaster_id": to_id
        }
        return await self._post(self._channel_auth, self.raid_url, params=params)

    async def cancel_raid(self):
        params = { "broadcaster_id": self._channel_auth.channel_id}
        return await self._delete(self._channel_auth, self.raid_url, params=params)

    search_category_url = "https://api.twitch.tv/helix/search/categories"
    async def search_category(self, query, limit=20, after=None):
        params = {
            "query": query,
            "first": limit
        }
        if after: params["after"] = after
        return await self._get(self._user_auth, self.search_category_url, params=params)

    search_channel_url = "https://api.twitch.tv/helix/search/channels"
    async def search_channel(self, query, live_only=0, limit=20, after=None):
        params = {
            "query": query,
            "live_only": live_only,
            "limit": limit
        }
        if after: params["after"] = after
        return await self._get(self._user_auth, self.search_channel_url, params=params)

    stream_url = "https://api.twitch.tv/helix/streams"
    async def get_streams(self, user_id=None, user_login=None, game_id=None, type="all", language=None, count=20, pagination=True):
        params = {
            "type": type,
            "limit": count
        }

        if user_id: params["user_id"] = self.convert_to_iterable(user_id)
        if user_login: params["user_login"] = self.convert_to_iterable(user_login)
        if game_id: params["game_id"] = self.convert_to_iterable(game_id)
        if language: params["language"] = self.convert_to_iterable(language)
        return await self._get(self._user_auth, self.stream_url, params=params, pagination=pagination)

    subscription_info = "https://api.twitch.tv/helix/subscriptions"
    async def get_subscriptions(self, user_id=None, limit=20, pagination=False):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "first": limit
        }
        if user_id: params["user_id"] = self.convert_to_iterable(user_id)
        return await self._get(self._channel_auth, self.subscription_info, params=params, pagination=pagination)

    async def get_user_subscription(self, user_id: str):
        params = {
            "broadcaster_id": self._channel_auth.channel_id,
            "user_id": user_id
        }
        return await self._get(self._channel_auth, self.subscription_info + "/user", params=params, cache=True)

    user_url = "https://api.twitch.tv/helix/users"
    async def get_users(self, user_id=None, user_login=None, cache=False):
        params = {}
        if user_id: params["id"] = self.convert_to_iterable(user_id)
        if user_login: params["login"] = self.convert_to_iterable(user_login)
        return await self._get(self._user_auth, self.user_url, params=params, cache=cache)

    video_info = "https://api.twitch.tv/helix/videos"
    async def delete_videos(self, video_id=None):
        params = {}
        if video_id: params["id"] = self.convert_to_iterable(video_id)
        return await self._delete(self._channel_auth, self.video_info, params=params)

    marker_url = "https://api.twitch.tv/helix/streams/markers"
    async def create_marker(self, description : str=None):
        params = { "user_id": self._channel_auth.channel_id }
        if description: params["description"] = description
        return await self._post(self._channel_auth, self.marker_url, params=params)

    async def get_markers(self, user_id: str=None, video_id: str=None, limit=20, pagination=False):
        params = { "first": limit }
        if user_id: params["user_id"] = user_id
        elif video_id: params["video_id"] = video_id
        else: params["user_id"] = self._channel_auth.channel_id
        return await self._get(self._channel_auth, self.marker_url, params=params, pagination=pagination)