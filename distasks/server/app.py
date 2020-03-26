from aiohttp import web
import asyncio
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
import logging
import os.path
import attr
from types import CoroutineType


logger = logging.getLogger("distasks.server")

with open(os.path.join(os.path.dirname(__file__), "index.html"), "r") as f:
    index_html = f.read()


class Client:
    def __init__(self, ws, name):
        self.ws = ws
        self.name = name
        self.completed = 0
        self.task = None


@attr.s
class Task(object):
    """Data class for tasks"""
    num = attr.ib()
    data = attr.ib()
    runs = attr.ib(init=False, default=0)


@attr.s
class ProgressStore:
    """Represents a mostly linear set of integers in the most efficient way possible: 
        comp_floor: the maximum number where every number below is in the set
        comp_list: every number above comp_floor
    Ex: ProgressStore(2, [4, 5]) => [1, 2, 4, 5]
        ProgressStore(0, [1, 2, 3]) => ProgressStore(3)"""
    comp_floor = attr.ib(default=0)
    comp_list = attr.ib(default=[])
    def __attrs_post_init__(self):
        self.update()
    
    def contains(self, num):
        return num <= self.comp_floor or num in self.comp_list
    
    def update(self):
        self.comp_list = sorted(self.comp_list)
        newlist = []
        for val in self.comp_list:
            if val <= self.comp_floor:
                continue
            if val == self.comp_floor + 1:
                self.comp_floor += 1
                continue
            newlist.append(val)
        self.comp_list = newlist
    
    def get_missing(self):
        self.update()
        if not self.comp_list:
            return []
        list_min = self.comp_list[0]
        if list_min > self.comp_floor:
            miss = []
            for i in range(1, list_min - self.comp_floor):
                miss.append(self.comp_floor + i)
            return miss
        else:
            return []

    def add_num(self, num):
        """Adds a number to the set"""
        if num not in self.comp_list:
            self.comp_list.append(num)
        self.update()

    def __str__(self):
        """Represent the store as {comp_floor}&{comp_list csv}"""
        nums = ','.join(str(i) for i in self.comp_list)
        return f"{self.comp_floor}&{nums}"

    def write_to(self, fname):
        """Writes string of self to file"""
        self.update()
        with open(fname, "w+") as f:
            f.write(str(self))

    @classmethod
    def read_from(cls, fname, exceptions=False):
        """Returns a new instance loaded from fname. 
            If exceptions if False (default), on error the default instance will be returned. Otherwise the exception will be re-raised"""
        try:
            with open(fname, "r") as f:
                data = f.read().strip()
            
            floor, comp_list = data.split("&")
            floor = int(floor)
            comp_list = [int(i) for i in comp_list.split(",") if i]
        except:
            if exceptions:
                raise
            return cls() # let class decide the default
        return cls(comp_floor=floor, comp_list=comp_list)


@attr.s
class DistasksServer(ABC):
    """An abtract base class for a distasks server"""

    # Attr does all the work here
    asset_zip_path = attr.ib()

    version = attr.ib(default="0.0.1")
    save_filename = attr.ib(default=None)
    start_at = attr.ib(default=0)
    progress = attr.ib(default=None)

    @save_filename.validator
    def validate_save_filename(self, attr, save_filename):
        if save_filename:
            # load the file with exceptions=True so we can handle the default
            try:
                self.progress = ProgressStore.read_from(save_filename, exceptions=True)
            except:
                self.progress = ProgressStore(
                    comp_floor=self.start_at - 1
                )
            else: # if it loads successfully
                if self.progress.comp_floor < self.start_at:
                    raise ValueError("Loaded progress file's comp_floor is lower than start_at")
        elif self.progress is None:
            self.progress = ProgressStore(
                comp_floor=self.start_at)
    
    api_enabled = attr.ib(default=True)

    # empty list, set, and a web app
    # TODO: track current tasks and update docstrings
    _repeat_queue = attr.ib(factory=list)
    _clients = attr.ib(factory=set)
    app = attr.ib(factory=web.Application)

    def __attrs_post_init__(self):
        self._task_num = self.progress.comp_floor
    
    @abstractmethod
    def get_job(self, num):
        """Function to """
        pass

    def verify_client(self, client):
        """Default client verifier function to be overrided in subclasses. Accepts every client by default. """
        return True
    
    def on_complete(self, *args):
        """Default on task complete handler to be overrided in subclasses. Does nothing by default. """
        print("complete", args)

    async def index_route(self, req):
        return web.Response(text=index_html, content_type="text/html")
        # Comment above line and uncomment below lines to refresh index.html every time
        #print("REMOVEME FOR DEBUGGING ONLY")
        #return web.FileResponse("./distasks/server/index.html")
    
    async def status_route(self, req):
        if not self.api_enabled:
            return web.json_response({"error": "API disabled"}, status=400)
        data = {
            "progress": self.progress.comp_floor,
            "clients": []
        }
        for c in self._clients:
            if isinstance(c.task, Task):
                tdata = {
                    "num": c.task.num,
                    "data": c.task.data
                }
            else:
                tdata = None
            data["clients"].append({
                "name": c.name,
                "connected": not c.ws.closed,
                "completed": c.completed,
                "current": tdata
            })
        return web.json_response(data)
    
    async def version_route(self, req):
        return web.Response(text=self.version)
    
    async def asset_zip_route(self, req):
        return web.FileResponse(self.asset_zip_path)

    async def _find_next_task(self):
        if self._repeat_queue:
            task = self._repeat_queue[0]
            self._repeat_queue = self._repeat_queue[1:]
            return task
        while self.progress.contains(self._task_num):
            self._task_num += 1
        task = Task(self._task_num, 
            self.get_job(self._task_num))
        self._task_num += 1
        return task

    async def _handle_completion(self, task, res):
        self.progress.add_num(task.num)
        if self.save_filename:
            self.progress.write_to(self.save_filename)
        if self.on_complete:
            # handle both sync and coro
            res = self.on_complete(task, res)
            if type(res) is CoroutineType:
                res = await res
            if res:
                logger.debug("On complete handler returned true, repeating task")
                self._repeat_queue.append(task)

    async def work_ws_route(self, req):
        logger.debug("New worker connection")
        ws = web.WebSocketResponse(heartbeat=5)
        await ws.prepare(req)
        in_progress = False
        try:
            await ws.send_str("ready")

            identify = await ws.receive_json()
            name = identify["name"]
            # handle both sync and coro with
            verify_res = self.verify_client(identify)
            if type(verify_res) is CoroutineType:
                verify_res = await verify_res
            if not verify_res:
                logger.warn("Client verification failed")
                return
            c = Client(ws, name)
            self._clients.add(c)

            while True:
                task = await self._find_next_task()
                await ws.send_json(task.data)
                in_progress = True
                c.task = task
                logger.debug(f"assigned {task.num} to { name}")
                res = await ws.receive_json()
                in_progress = False
                c.completed += 1
                task.runs += 1
                await self._handle_completion(task, res)
        except Exception as e:
            # don't let client caused errors trip up the application, but log them
            # TypeErrors (usually caused by connection closing during a typed receive call) should be debug level
            if not isinstance(e, TypeError):
                logger.exception("Exception in worker websocket: ")
            else:
                logger.debug("Exception in worker websocket:", exc_info=True)
        finally:
            logger.debug("Worker websocket closing")
            if in_progress:
                self._repeat_queue.append(task)
            
            if not ws.closed:
                await ws.close()

    def cleanup_task(self):
        logger.debug("Cleanup thread active")
        import time
        while True:
            missing = self.progress.get_missing()
            if missing:
                repeat_nums = set([t.num for t in self._repeat_queue])
                for i in missing:
                    if i in repeat_nums:
                        continue
                    logger.debug(f"{i} missing, repeating")
                    task = Task(i, 
                        self.get_job(self._task_num))
                    self._repeat_queue.append(task)
            time.sleep(5)

    def add_routes(self):
        self.app.add_routes([
            web.get('/', self.index_route),
            web.get('/ws', self.work_ws_route),
            web.get('/version', self.version_route),
            web.get('/assets.zip', self.asset_zip_route),
            web.get('/api/status', self.status_route)
        ])

    def run(self):
        print("Distasks server starting...")
        self.add_routes()
        loop = asyncio.get_event_loop()
        pool = ThreadPoolExecutor()
        loop.run_in_executor(pool, self.cleanup_task)
        web.run_app(self.app)

    def __bool__(self):
        return True
