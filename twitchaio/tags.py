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

from enum import IntEnum

class UserLevel(IntEnum):
    Any = 0,
    Regular = 1,
    Subscriber = 2,
    VIP = 3,
    Mod = 4,
    SuperMod = 5,
    Broadcaster = 6

class Tags:
    """ See https://dev.twitch.tv/docs/irc/tags for more information on the various tags """

    type = -1
    def __init__(self, user, data):
        if data.startswith("@"):
            meta = data[1:].split(";")
            self._data = {item[0]: item[1] for obj in meta if len(item := obj.split("=")) == 2}
            self._data["user-name"] = user.split("!", maxsplit=1)[0]
        else: self._data = {}

    @property
    def room_id(self): return self._data.get("room-id", "")
    @property
    def user_name(self): return self._data.get("user-name", "")

    def __str__(self):
        return f"{self.__class__.__name__}[{','.join([f'{key}={value}' for key, value in self._data.items()])}]"
    __repr__ = __str__

class CLEARCHAT(Tags):
    """ Indicates a user has been timed out or banned from the channel """

    type = 1
    @property
    def duration(self): return int(self._data.get("ban-duration", -1))
    @property
    def user_id(self): return self._data.get("target-user-id", "")
    @property
    def user_name(self): return ""

    def __str__(self): return f"CLEARCHAT[duration={self.duration}]"
    __repr__ = __str__

class CLEARMSG(Tags):
    """ Indicates that a message from a user has been deleted in a channel """

    type = 2
    @property
    def message_id(self): return self._data.get("target-msg-id", "")
    @property
    def user_name(self): return self._data.get("login", "")

    def __str__(self): return f"CLEARMSG[login={self.user_name}]"
    __repr__ = __str__

def parse_badges(badges): return [badge.split("/")[0] for badge in badges.split(",")]

class GLOBALUSERSTATE(Tags):
    """ Fired after the user connected to the channel """

    type = 3
    @property
    def badge_info(self): return self._data.get("badge-info", "")
    @property
    def badges(self): return parse_badges(self._data.get("badges", ""))
    @property
    def display_name(self): return self._data.get("display-name", "")
    @property
    def emote_sets(self): return ",".split(self._data.get("emote-sets", ""))
    @property
    def turbo(self): return self._data.get("turbo") == "1"
    @property
    def user_id(self): return self._data.get("user-id", "")

class NOTICE(Tags):
    """ Indicates the outcome of an action """

    type = 4
    @property
    def message_id(self): return self._data.get("msg-id", "")
    @property
    def user_id(self): return self._data.get("target-user-id", "")

class PRIVMSG(Tags):
    """ Indicates a user has sent a message in a channel """

    type = 5
    @property
    def badge_info(self): return self._data.get("badge-info", "")
    @property
    def badges(self): return parse_badges(self._data.get("badges", ""))
    @property
    def bits(self):
        try: return int(self._data.get("bits", 0))
        except ValueError: return 0
    @property
    def display_name(self): return self._data.get("display-name", "")
    @property
    def emote_only(self): return self._data.get("emote-only") == "1"
    @property
    def emotes(self): return [emote for item in self._data.get("emotes", "").split("/") if len(emote := item.split(":")) == 2]
    @property
    def first_message(self): return self._data.get("first-msg", "")
    @property
    def id(self): return self._data.get("id", "")
    @property
    def moderator(self): return self._data.get("mod") == "1"
    @property
    def vip(self): return self._data.get("vip", "") == "1"
    @property
    def subscriber(self): return self._data.get("subscriber") == "1"
    @property
    def user_id(self): return self._data.get("user-id", "")
    @property
    def data(self): return self._data

    @property
    def user_level(self): return UserLevel.Broadcaster if "broadcaster" in self._data.get("badges", "") else UserLevel.Mod if self.moderator else UserLevel.VIP if self.vip else UserLevel.Subscriber if self.subscriber else UserLevel.Any

    def __str__(self): return f"PRIVMSG[moderator={self.moderator}, vip={self.vip}, subscriber={self.subscriber}, name={self.display_name}, user_level={self.user_level.name}]"
    __repr__ = __str__

class ROOMSTATE(Tags):
    """ Indicates the new settings for the current room """

    type = 6
    @property
    def emote_only(self): return self._data.get("emote-only") == "1"
    @property
    def followers_only(self): return self._data.get("followers-only") == "1"
    @property
    def r9k_mode(self): return self._data.get("r9k") == "1"
    @property
    def slow_mode(self): return int(self._data.get("slow", 0))
    @property
    def subscriber_only(self): return self._data.get("subs-only") == "1"

    def __str__(self): return f"ROOMSTATE[emote={self.emote_only}, followers={self.followers_only}, slow={self.slow_mode}, subscribers={self.subscriber_only}]"
    __repr__ = __str__

class USERNOTICE(Tags):
    """ Indicates an event happened in a channel, see message_type for the event type """

    type = 7
    @property
    def display_name(self): return self._data.get("display-name", "")
    @property
    def message_type(self): return self._data.get("msg-id", "")
    @property
    def user_id(self): return self._data.get("user-id", "")

    @property
    def viewer_count(self): return int(self._data.get("msg-param-viewerCount", 0))
    @property
    def months(self): return int(self._data.get("msg-param-cumulative-months", 0))
    @property
    def plan(self): return self._data.get("msg-param-sub-plan")
    @property
    def recipient_id(self): return self._data.get("msg-param-recipient-id")
    @property
    def recipient_name(self): return self._data.get("msg-param-recipient-display-name")
    @property
    def gift_months(self): return int(self._data.get("msg-param-gift-months", 0))
    @property
    def mass_gift_count(self): return int(self._data.get("msg-param-mass-gift-count", 0))
    @property
    def multimonth_duration(self): return int(self._data.get("msg-param-multimonth-duration", 0))
    @property
    def multimonth_tenure(self): return int(self._data.get("msg-param-multimonth=tenure", 0))


tag_types = {key: value for key, value in globals().items()}
def parse_tags(message_type, user, data):
    return tag_types.get(message_type, Tags)(user, data)