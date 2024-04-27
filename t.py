#!/usr/bin/env python3

import os

# Get the current user's home directory
home_dir = os.path.expanduser("~")
new_dir = f"{home_dir}"
new_file = f"{new_dir}/new_file.txt"
content = "Hello, World!"
with open(new_file, "a", content=content):
    write(content)
    print(f"File created at {new_file}")
