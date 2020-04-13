import aiohttp
from aiohttp import web
import asyncio
import json
import os
import shutil
import zipfile
import shlex
import io
import types
import logging
from . import persistant


logger = logging.getLogger("distasks.client")


class DistasksClient:
    def __init__(self, host, name, use_http=False, 
    version_file="version.txt", 
    task_assets_dir="task_assets", identify_payload={},
    always_update=True, web=False):
        self.host = host
        self.name = name
        self.version_file = version_file
        extra = '' if use_http else 's'
        self.update_server = f"http{extra}://{self.host}"
        self.work_ws = f"ws{extra}://{self.host}/ws"
        self.task_assets_dir = task_assets_dir
        self.identify_payload = identify_payload
        self.always_update = always_update
        self.web = web

    async def get_current_version(self):
        try:
            with open(self.version_file, "r") as f:
                return f.read()
        except:
            return None

    async def write_current_version(self, version):
        with open(self.version_file, "w+") as f:
            f.write(version)


    async def get_update_version(self, s):
        logger.info("Checking for update...")
        async with s.get(self.update_server + "/version") as r:
            version = await r.text()
            return version


    async def perform_update(self, s, v):
        if os.path.isdir(self.task_assets_dir):
            logger.info("Removing task_assets...")
            shutil.rmtree(self.task_assets_dir)
        os.mkdir(self.task_assets_dir)
        logger.info(f"Downloading update version {v!r}...")
        async with s.get(self.update_server + "/assets.zip") as r:
            if r.status != 200:
                raise ValueError("Update zip status is not 200")
            zf = zipfile.ZipFile(
                io.BytesIO(await r.read())
            )
        logger.info("Extracting update...")
        zf.extractall(path="task_assets")
        await self.write_current_version(v)
        logger.info(f"Updated to version {v!r}")


    async def run_task(self, data):
        logger.info(f"Running task with data {data}")
        if os.path.exists(os.path.join(".", "task_assets", "task.sh")):
            # make an asynchronous subprocess
            proc = await asyncio.create_subprocess_shell(
                shlex.join([os.path.join(".", "task.sh"), data]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            return stdout.decode()
        elif os.path.exists(os.path.join(".", "task_assets", "task.py")):
            from task_assets import task as task_module
            data = json.loads(data)
            res = task_module.main(data)
            if type(res) is types.CoroutineType:
                res = await res
            return res
        else:
            raise ValueError("No entrypoint found for task: neither task.sh nor task.py exists in task_assets")

    async def do_work_forever(self, s):
        async with s.ws_connect(self.work_ws) as ws:
            await ws.receive()
            
            await ws.send_json({
                "name": self.name,
                **self.identify_payload
            })
            while True:
                logger.info("Getting new task...")
                task_data = await ws.receive_str()
                logger.info("Running task...")
                res = await self.run_task(task_data)
                logger.info(f"Submitting result: {res!r}")
                await ws.send_json(res)

    async def _main(self):
        async with aiohttp.ClientSession() as s:
            update_version = await self.get_update_version(s)
            if self.always_update or (await self.get_current_version()) != update_version:
                await self.perform_update(s, update_version)
            else:
                logger.info("Up to date. ")
            logger.info(f"Client starting...")
            while True:
                await self.do_work_forever(s)

    async def main(self):
        while True:
            try:
                await self._main()
            except Exception as e:
                if isinstance(e, KeyboardInterrupt):
                    break
                logger.exception("Error occurred in client")
                await asyncio.sleep(5)

    def run(self):
        loop = asyncio.get_event_loop()
        if self.web:
            app = web.Application()
            app.add_routes([
                aiohttp.web.get('/', 
                    (lambda req: 
                        web.Response(text='Hello world!')))
                ])
            loop.create_task(self.main())
            web.run_app(app)
        else:
            loop.run_until_complete(self.main())
