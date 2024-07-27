import asyncio
import hmac
import hashlib
import random
from urllib.parse import unquote, quote
from time import time

import aiohttp
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers

class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None

    async def get_secret(self, userid):
        key_hash = str("adwawdasfajfklasjglrejnoierjboivrevioreboidwa").encode('utf-8')
        message = str(userid).encode('utf-8')
        hmac_obj = hmac.new(key_hash, message, hashlib.sha256)
        secret = str(hmac_obj.hexdigest())
        return secret

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            while True:
                try:
                    peer = await self.tg_client.resolve_peer('tBTCminer_bot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")

                    await asyncio.sleep(fls + 3)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://electrostations.pages.dev'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

            query_id = tg_web_data.split('query_id=', maxsplit=1)[1].split('&user', maxsplit=1)[0]
            #print(query_id)
            user_data = tg_web_data.split('user=', maxsplit=1)[1].split('&auth_date', maxsplit=1)[0]
            #print(user_data)
            auth_date = tg_web_data.split('auth_date=', maxsplit=1)[1].split('&hash', maxsplit=1)[0]
            tg_hash = tg_web_data.split('hash=', maxsplit=1)[1]
            #print(tg_hash)

            self.user_id = (await self.tg_client.get_me()).id

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data,tg_hash

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=30)


    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")
            await asyncio.sleep(delay=30)

    async def login(self, http_client: aiohttp.ClientSession, tg_web_data: str):
        try:
            json_data = {'init_data' : tg_web_data }
            logger.info(f"{self.session_name} | Login json data: {json_data} ")

            response = await http_client.post(url='https://tonbitcoin.cc/user/auth', json=json_data)
            response_text = await response.text()
            response.raise_for_status()

            logger.info(f"{self.session_name} | Get [login] data")
            access_token = response_text
            return access_token

        except Exception as error:
            logger.error(f"{self.session_name} | Login: {tg_web_data} | Error: {error}")
            await asyncio.sleep(delay=30)

    async def getInfo(self, http_client: aiohttp.ClientSession) :
        try:
            get_url = f"https://tonbitcoin.cc/energizer/getInfo?user_id={self.user_id}"
            response = await http_client.get(url=get_url)
            response.raise_for_status()

            logger.info(f"{self.session_name} | Get [getInfo] data")
            response_json = await response.json()
            return response_json

        except Exception as error:
            logger.error(f"{self.session_name} | GetInfo Error: {error}")
            await asyncio.sleep(delay=30)

    async def task_tap(self, http_client: aiohttp.ClientSession, taps: float):
        try:
            json_data = {'electricity_added' : taps , 'id' : self.user_id}
            logger.info(f"{self.session_name} | Tap json data: {json_data} ")

            response = await http_client.put(url='https://tonbitcoin.cc/energizer/handle_tap', json=json_data)
            response.raise_for_status()

            logger.info(f"{self.session_name} | Get [task_tap] data")
            response_json = await response.json()
            return response_json

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Apply task_mine: {error}")
            await asyncio.sleep(delay=30)

            return False


    async def run(self, proxy: str | None) -> None:
        access_token_created_time = 0
        active_turbo = False
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        tg_web_data,tg_hash = await self.get_tg_web_data(proxy=proxy)
        http_client.headers["Authorization"] = f"Bearer {tg_hash}"

        while True:
            try:
                # Randomize variables
                random_sleep = random.randint(*settings.SLEEP_BY_MIN_ENERGY)
                sleep_between_tap = random.randint(*settings.SLEEP_BETWEEN_TAP)

                if not tg_hash or not tg_web_data:
                    continue

                if time() - access_token_created_time >= 1800:

                    tg_web_data, tg_hash = await self.get_tg_web_data(proxy=proxy)
                    http_client.headers["Authorization"] = f"Bearer {tg_hash}"
                    access_token = await self.login(http_client=http_client, tg_web_data=tg_web_data)
                    logger.info(f"Generate new access_token: {access_token}")
                    access_token_created_time = time()

                    if not access_token:
                        continue

                    player_data = await self.getInfo(http_client=http_client)
                    bot_balance = float(player_data['balance'])
                    bot_storage = float(player_data['storage'])
                    bot_tap_strength = float(player_data['tap_strength'])
                    bot_tap_level = float(player_data['tap_level'])

                    logger.success(f"{self.session_name} | Player data: | "
                                   f"Balance: <c>{bot_balance:,}</c> | Storage: <c> {bot_storage:,}</c> | " 
                                   f"Tap info: Strength <e>{bot_tap_strength:,}</e>, Level: <e>{bot_tap_level:,}</e>")

                taps = (random.randint(*settings.RANDOM_TAPS_COUNT) * bot_tap_strength)

                if taps >= bot_storage:
                    taps = abs(bot_storage // bot_tap_strength - 1)

                # получение свежих данных после тапа для расчета
                status = await self.task_tap(http_client=http_client, taps=taps)
                bot_storage = int(float(status['storage']))
                if status:
                    logger.success(f"{self.session_name} | Bot action: <g>[tap/{taps}]</g> : <c>{status}</c>")
                else:
                    logger.error(f"{self.session_name} | Bot action: <red>[tap/{taps}]</red> : <c>{status}</c>")

                if bot_storage < settings.MIN_AVAILABLE_ENERGY:
                    logger.info(f"{self.session_name} | Minimum energy reached: {bot_storage}")
                    logger.info(f"{self.session_name} | Sleep {random_sleep:,}s")
                    await asyncio.sleep(delay=random_sleep)
                    access_token_created_time = 0

                else:
                    logger.info(f"Sleep between tap: {sleep_between_tap}s")
                    await asyncio.sleep(delay=sleep_between_tap)

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=30)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
