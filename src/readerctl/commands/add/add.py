from buvis.adapters import cfg, console
from readerctl.adapters import ReaderAPIAdapter


class CommandAdd:

    def __init__(self):
        res = cfg.get_key_value("token")

        if res.is_ok():
            token = res.message
        else:
            console.panic(res.message)
        self.api = ReaderAPIAdapter(token)

    def execute(self, url):
        res = self.api.add_url(url)

        if res.is_ok():
            console.success(res.message)
        else:
            console.failure(res.message)
