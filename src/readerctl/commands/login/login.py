from pathlib import Path

from buvis.adapters import cfg, console
from readerctl.adapters import ReaderAPIAdapter


class CommandLogin:

    def __init__(self) -> None:
        pass

    def execute(self):
        try:
            with open(
                    Path(Path.home(), ".config", "scripts",
                         "readwise-token"), ) as f:
                token = f.read()
        except FileNotFoundError:
            token = ""

        if token:
            cfg.set_key_value("token", token)
            token_check = ReaderAPIAdapter.check_token(token)

            if token_check.is_ok():
                console.success("API token valid")
            else:
                console.panic(
                    f"Token check failed: {token_check.code} - {token_check.message}",
                )
        else:
            token = console.input_password("Enter Readwise API token: ")
            with open(
                    Path(Path.home(), ".config", "scripts", "readwise-token"),
                    "w",
            ) as f:
                f.write(token)
            cfg.set_key_value("token", token)
            token_check = ReaderAPIAdapter.check_token(token)

            if token_check.is_ok():
                console.success("API token stored for future use")
            else:
                console.panic(
                    f"Token check failed: {token_check.code} - {token_check.message}",
                )
