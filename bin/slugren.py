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
import unidecode
from argparse import ArgumentParser
from datetime import datetime, timezone
from email.utils import mktime_tz, parsedate_tz
from pathlib import Path

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
        renamed = normalize(old.stem) + old.suffix
        # add received timestamp for emails

        if old.suffix == ".eml":
            with open(path, "rt", encoding="utf8") as email:
                pt_received = re.compile(r"Date: (.*)")
                received = ""

                for line in email:
                    match = pt_received.match(line)

                    if match:
                        local = datetime.fromtimestamp(
                            mktime_tz(parsedate_tz(match.group(1))))
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

                if received != "":
                    renamed = f"{received}-{remainder}{old.suffix}"
        os.rename(path, os.path.join(old.parent, renamed))
