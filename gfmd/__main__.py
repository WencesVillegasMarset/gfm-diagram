#!/usr/local/bin/python3.8
import argparse
import time
from pathlib import Path

import marko
from marko.helpers import Source
from marko.md_renderer import MarkdownRenderer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from gfmd.elements import (
    RenderableMermaid,
    RenderableMermaidBlock,
    RenderableMermaidBlockRendererMixin,
)

markdown_parser = marko.Markdown(
    renderer=MarkdownRenderer, extensions=[RenderableMermaid]
)


def process_file(filename):
    print(f"Processing {filename}... ", end="")
    fpath = Path(filename)
    new_file = markdown_parser.convert(fpath.read_text())
    # FIXME: This is wrong, it is what it is.
    mermaid_src = RenderableMermaidBlock(new_file).parse(Source(new_file))
    img = RenderableMermaidBlockRendererMixin().make_kroki_image_link(mermaid_src)
    rendered = RenderableMermaidBlockRendererMixin.template.format(
        input_mermaid=mermaid_src, image_link=img
    )
    if rendered not in new_file:
        mermaid_start = new_file.find(RenderableMermaidBlock.CODE_START_TOKEN)
        start, end = (
            new_file[0:mermaid_start],
            new_file[
                mermaid_start
                + len(mermaid_src)
                + len(
                    RenderableMermaidBlock.CODE_START_TOKEN
                    + RenderableMermaidBlock.CODE_END_TOKEN
                )
                + 5 :
            ],
        )
        new_file = start + rendered + end
    if new_file != fpath:
        print("Updated... ", end="")
        fpath.write_text(new_file)
    else:
        print("Skipped... ", end="")
    print("Done.")


class RerenderEventHandler(FileSystemEventHandler):
    """Watchdog handler to re-render when we see a change which GFMD can process."""

    def __init__(self):
        self.debounce_interval = 1  # seconds
        self.debounce_list = {}  # path -> seen time

    def debounce_allow(self, event):
        """Return True if the event is allowed.

        Because GFMD modifies files, we generate new filesystem events when re-writing the updated markdown.
        To counter this, we have to ignore the resulting events.
        """
        current_time = time.monotonic()

        if event.src_path in self.debounce_list:
            if (
                current_time
                < self.debounce_list[event.src_path] + self.debounce_interval
            ):
                return False

        self.debounce_list[event.src_path] = current_time
        return True

    def render(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return
        if not self.debounce_allow(event):
            return
        process_file(event.src_path)

    def on_created(self, event):
        self.render(event)

    def on_modified(self, event):
        self.render(event)


def watch(folders):
    event_handler = RerenderEventHandler()
    observer = Observer()
    for folder in folders:
        observer.schedule(event_handler, str(folder), recursive=True)
    observer.start()
    print("Watching for markdown file changes")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        print("Exiting")


def run():

    # Parse program input
    parser = argparse.ArgumentParser(
        description="Updated embedded mermaid diagrams in markdown."
    )
    parser.add_argument(
        "files",
        metavar="file",
        type=str,
        nargs="*",
        help="The files to render. Parse none to render all files.",
    )
    parser.add_argument(
        "-w",
        "--watch",
        action='store_true',
        help="Watch for changes and re-run on changes.",
    )
    args = parser.parse_args()
    files = args.files

    if args.watch:
        # Run in watch mode.
        if not files:
            files = [Path(".")]

        for folder in files:
            if not Path(folder).is_dir():
                raise Exception("Watching requires that you specify only directories")

        watch(files)

    else:
        # One shot process
        # If no files passed, run on everything
        if not files:
            files = Path(".").rglob("*.md")

        for file in files:
            process_file(file)


if __name__ == "__main__":
    run()
