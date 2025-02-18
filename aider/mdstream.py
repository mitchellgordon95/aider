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

_text_prefix = """
# Header

Lorem Ipsum is simply dummy text of the printing and typesetting industry.
Lorem Ipsum has been the industry's standard dummy text ever since the 1500s,
when an unknown printer took a galley of type and scrambled it to make a type
specimen book. It has survived not only five centuries, but also the leap into
electronic typesetting, remaining essentially unchanged. It was popularised in
the 1960s with the release of Letraset sheets containing Lorem Ipsum passages,
and more recently with desktop publishing software like Aldus PageMaker
including versions of Lorem Ipsum.



## Sub header

- List 1
- List 2
- List me
- List you



```python
"""

_text_suffix = """
```

## Sub header too

The end.

"""  # noqa: E501


class MarkdownStream:
    """Streaming markdown renderer that progressively displays content with a live updating window.

    Uses rich.console and rich.live to render markdown content with smooth scrolling
    and partial updates. Maintains a sliding window of visible content while streaming
    in new markdown text.
    """

    live = None  # Rich Live display instance
    when = 0  # Timestamp of last update
    min_delay = 1.0 / 20  # Minimum time between updates (20fps)
    live_window = 6  # Number of lines to keep visible at bottom during streaming

    def __init__(self, mdargs=None):
        """Initialize the markdown stream.

        Args:
            mdargs (dict, optional): Additional arguments to pass to rich Markdown renderer
        """
        self.printed = []  # Stores lines that have already been printed

        if mdargs:
            self.mdargs = mdargs
        else:
            self.mdargs = dict()
            
        self.mermaid_pattern = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)

        # Initialize rich Live display with empty text
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

    def _render_markdown_to_lines(self, text):
        """Render markdown text to a list of lines.

        Args:
            text (str): Markdown text to render

        Returns:
            list: List of rendered lines with line endings preserved
        """
        # Render the markdown to a string buffer
        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=True)
        markdown = Markdown(text, **self.mdargs)
        console.print(markdown)
        output = string_io.getvalue()

        # Split rendered output into lines
        return output.splitlines(keepends=True)

    def __del__(self):
        """Destructor to ensure Live display is properly cleaned up."""
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass  # Ignore any errors during cleanup

    def update(self, text, final=False):
        """Update the displayed markdown content.

        Args:
            text (str): The markdown text received so far
            final (bool): If True, this is the final update and we should clean up

        Splits the output into "stable" older lines and the "last few" lines
        which aren't considered stable. They may shift around as new chunks
        are appended to the markdown text.

        The stable lines emit to the console above the Live window.
        The unstable lines emit into the Live window so they can be repainted.

        Markdown going to the console works better in terminal scrollback buffers.
        The live window doesn't play nice with terminal scrollback.
        """
        now = time.time()
        # Throttle updates to maintain smooth rendering
        if not final and now - self.when < self.min_delay:
            return
        self.when = now

        # Measure render time and adjust min_delay to maintain smooth rendering
        start = time.time()
        lines = self._render_markdown_to_lines(text)
        render_time = time.time() - start

        # Set min_delay to render time plus a small buffer
        self.min_delay = min(max(render_time * 10, 1.0 / 20), 2)

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

        num_lines = len(lines)

        # How many lines have "left" the live window and are now considered stable?
        # Or if final, consider all lines to be stable.
        if not final:
            num_lines -= self.live_window

        # If we have stable content to display...
        if final or num_lines > 0:
            # How many stable lines do we need to newly show above the live window?
            num_printed = len(self.printed)
            show = num_lines - num_printed

            # Skip if no new lines to show above live window
            if show <= 0:
                return

            # Get the new lines and display them
            show = lines[num_printed:num_lines]
            show = "".join(show)
            show = Text.from_ansi(show)
            self.live.console.print(show)  # to the console above the live area

            # Update our record of printed lines
            self.printed = lines[:num_lines]

        # Handle final update cleanup
        if final:
            self.live.update(Text(""))
            self.live.stop()
            self.live = None
            return

        # Update the live window with remaining lines
        rest = lines[num_lines:]
        rest = "".join(rest)
        rest = Text.from_ansi(rest)
        self.live.update(rest)

    def find_minimal_suffix(self, text, match_lines=50):
        """
        Splits text into chunks on blank lines "\n\n".
        """


if __name__ == "__main__":
    with open("aider/io.py", "r") as f:
        code = f.read()
    _text = _text_prefix + code + _text_suffix
    _text = _text * 10

    pm = MarkdownStream()
    for i in range(6, len(_text), 5):
        pm.update(_text[:i])
        time.sleep(0.01)

    pm.update(_text, final=True)
