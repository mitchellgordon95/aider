#!/usr/bin/env python

import io
import time
import base64
import json
import zlib
import re

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from aider.dump import dump  # noqa: F401

_text = """
# Header

Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.



## Sub header

- List 1
- List 2
- List me
- List you



```python
import sys

def greeting():
    print("Hello world!")
```

## Sub header too

The end.

"""  # noqa: E501


class MarkdownStream:
    live = None
    when = 0
    min_delay = 0.050
    live_window = 6

    def __init__(self, mdargs=None):
        self.printed = []

        if mdargs:
            self.mdargs = mdargs
        else:
            self.mdargs = dict()
            
        self.mermaid_pattern = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)
        self.live = Live(Text(""), refresh_per_second=1.0 / self.min_delay)
        self.live.start()

    def _generate_mermaid_link(self, graph_markdown):
        """Generate a mermaid.live link for the given graph markdown"""
        def js_string_to_byte(data):
            return bytes(data, 'ascii')

        def js_bytes_to_string(data):
            return data.decode('ascii')

        def js_btoa(data):
            return base64.b64encode(data)

        def pako_deflate(data):
            compress = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY)
            compressed_data = compress.compress(data)
            compressed_data += compress.flush()
            return compressed_data

        j_graph = {
            "code": graph_markdown,
            "mermaid": {"theme": "default"}
        }
        byte_str = js_string_to_byte(json.dumps(j_graph))
        deflated = pako_deflate(byte_str)
        d_encode = js_btoa(deflated)
        link = 'http://mermaid.live/view#pako:' + js_bytes_to_string(d_encode)
        return link

    def __del__(self):
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass

    def update(self, text, final=False):
        now = time.time()
        if not final and now - self.when < self.min_delay:
            return
        self.when = now

        # Process mermaid diagrams
        processed_text = text
        for match in self.mermaid_pattern.finditer(text):
            mermaid_code = match.group(1)
            link = self._generate_mermaid_link(mermaid_code)
            # Add the link after the mermaid block
            diagram_end = match.end()
            processed_text = (
                processed_text[:diagram_end] + 
                f"\n\n[View diagram]({link})\n" +
                processed_text[diagram_end:]
            )

        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=True)

        markdown = Markdown(processed_text, **self.mdargs)

        console.print(markdown)
        output = string_io.getvalue()

        lines = output.splitlines(keepends=True)
        num_lines = len(lines)

        if not final:
            num_lines -= self.live_window

        if final or num_lines > 0:
            num_printed = len(self.printed)

            show = num_lines - num_printed

            if show <= 0:
                return

            show = lines[num_printed:num_lines]
            show = "".join(show)
            show = Text.from_ansi(show)
            self.live.console.print(show)

            self.printed = lines[:num_lines]

        if final:
            self.live.update(Text(""))
            self.live.stop()
            self.live = None
        else:
            rest = lines[num_lines:]
            rest = "".join(rest)
            # rest = '...\n' + rest
            rest = Text.from_ansi(rest)
            self.live.update(rest)


if __name__ == "__main__":
    _text = 5 * _text

    pm = MarkdownStream()
    for i in range(6, len(_text)):
        pm.update(_text[:i])
        time.sleep(0.01)

    pm.update(_text, final=True)
