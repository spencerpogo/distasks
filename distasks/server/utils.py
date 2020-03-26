from .app import DistasksServer


def pwd_checker(pwd):
    """A utility to use for verify_client_func. Checks a client's auth password"""
    return (lambda id_data: pwd == id_data.get("pwd"))


def file_appender(fname, write_task=False, write_res=True):
    """A utility to use for on_complete_func. Appends the result to fname"""
    if not write_task and not write_res:
        raise ValueError("at least one of write_task and write_res must be truthy")
    
    async def append_to_file(task, res):
        # trigger any errors *before* we open the file
        data = (str(task) if write_task else '') + (str(res) if write_res else '')
        with open(fname, "a") as f:
            f.write(data)
    return append_to_file


def simple_server(get_job_func, asset_zip_config, 
    verify_client_func=None, on_complete_func=None,
    **kwargs):
    """A utility for easily making a serer without subclassing. 
    """
    class SimpleServer(DistasksServer):
        def get_job(self, num):
            """This is to bypass ABC error, will be replaced"""
            return get_job_func(num)
    
    if verify_client_func:
        SimpleServer.verify_client = staticmethod(verify_client_func)
    if on_complete_func:
        SimpleServer.on_complete = staticmethod(on_complete_func)
    
    return SimpleServer(asset_zip_config, **kwargs)
