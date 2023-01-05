#!/usr/bin/env python3
# slugren.py

# This is my file renamer. It slugifies, extracts timestamp from emails, etc.
# to get the filename compliant with my conventions.
# It can be called automatically by Hazel as embedded script:
# fname=$1
# /Users/bob/.asdf/shims/python3 ~/bin/slugren.py -p "${fname//[ ]/\\ }"

import os
import platform
import re
from argparse import ArgumentParser
from datetime import datetime, timezone
from email import message_from_file, policy
from email.parser import BytesParser
from email.utils import mktime_tz, parsedate_tz
from pathlib import Path

import unidecode
from bs4 import BeautifulSoup
from slugify import slugify

parser = ArgumentParser()
parser.add_argument(
    "-p",
    "--path",
    dest="path",
    help="path directory or \
                    file to slugify",
)
args = parser.parse_args()


def normalize(text):
    # remove non-necessary whitespace
    normalized_text = text.lstrip().rstrip()
    # replace invalid charactes by -
    normalized_text = slugify(normalized_text)
    normalized_text = normalized_text.replace("_", "-")
    # collapse multiple - to single one
    normalized_text = re.sub("-{2,}", "-", normalized_text)
    # remove extra characters
    normalized_text = normalized_text.lstrip(".-").rstrip(".-")
    # remove diacritics
    normalized_text = unidecode.unidecode(normalized_text)

    return normalized_text


if args.path:
    paths = args.path.replace("\ ", "!@#")
    paths = paths.split(" ")

    for path in paths:
        path = path.replace("!@#", " ")

        if platform.system() != "Windows":
            path = path.replace("\\", "")
        old = Path(path)

        if old.suffix:
            renamed = f"{normalize(old.stem)}.{normalize(old.suffix)}"
        else:
            renamed = f"{normalize(old.stem)}"

        # add received timestamp for emails

        if old.suffix == ".eml":
            email = message_from_file(open(path))
            date = email["date"].strip()
            local = datetime.fromtimestamp(mktime_tz(parsedate_tz(date)))
            utc = local.astimezone(timezone.utc)
            received = utc.strftime("%Y%m%d%H%M%S")
            filename_time = re.match("20\d+", old.stem)

            if filename_time:
                remainder = old.stem[filename_time.end(0):]
            else:
                remainder = old.stem

            remainder = normalize(remainder)
            remainder = re.sub("^(re-)+", "", remainder)
            remainder = re.sub("^(fw-)+", "", remainder)
            remainder = re.sub("^(fwd-)+", "", remainder)

            with open(path, "rb") as email_file:
                msg = BytesParser(policy=policy.default).parse(email_file)

                if msg.is_multipart():
                    text = ""

                    for part in msg.get_payload():
                        if part.get_content_type() in [
                                "text/plain",
                                "text/html",
                        ]:
                            add_text_raw = part.get_body().get_content()
                            add_text = " ".join(
                                BeautifulSoup(add_text_raw,
                                              "html.parser").stripped_strings)
                        else:
                            continue
                        text = text + "\n" + add_text
                else:
                    raw_text = msg.get_body().get_content()
                    text = " ".join(
                        BeautifulSoup(raw_text,
                                      "html.parser").stripped_strings)
                print(text)

            if received != "":
                renamed = f"{received}-{remainder}{old.suffix}"
        os.rename(path, os.path.join(old.parent, renamed))
