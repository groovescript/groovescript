import argparse
import sys
import time
from pathlib import Path

from .compiler import compile_groove, compile_song
from .errors import GrooveScriptError
from .lilypond import emit_lilypond
from .lint import check_notation, check_style
from .midi import emit_midi
from .musicxml import emit_musicxml
from .parser import parse_file


def _fail(err: GrooveScriptError) -> None:
    print(err.render(), file=sys.stderr)
    sys.exit(1)


def _attach_source_context(err: GrooveScriptError, input_path: str) -> None:
    """Fill in ``filename`` and ``source`` on a compile-time error so the
    source line and caret can be rendered. Parser errors already carry these
    fields; compiler errors raised from AST line metadata typically do not.
    """
    if err.filename is None:
        err.filename = input_path
    if err.source is None:
        try:
            err.source = Path(input_path).read_text()
        except OSError:
            pass


def _check_output_not_input(input_path: str, output_path: str) -> int | None:
    """Reject `-o` pointing at the source file to prevent silent data loss."""
    try:
        same = Path(input_path).resolve() == Path(output_path).resolve()
    except OSError:
        return None
    if same:
        err = GrooveScriptError(
            message=f"refusing to overwrite input file: {input_path}",
            hint="choose a different --output path",
        )
        print(err.render(), file=sys.stderr)
        return 1
    return None


def _parse_or_exit(input_path: str):
    try:
        return parse_file(input_path)
    except GrooveScriptError as err:
        _fail(err)
    except FileNotFoundError:
        _fail(GrooveScriptError(message=f"input file not found: {input_path}"))


def _compile_or_exit(song, input_path: str):
    try:
        return compile_song(song) if song.sections else compile_groove(song.grooves[0])
    except GrooveScriptError as err:
        _attach_source_context(err, input_path)
        _fail(err)
    except ValueError as err:
        _fail(GrooveScriptError(message=str(err), filename=input_path))


def _run_lint(input_path: str, with_style: bool) -> int:
    """Run the lint pipeline once. Returns the exit code (0 on success)."""
    try:
        song = parse_file(input_path)
    except GrooveScriptError as err:
        print(err.render(), file=sys.stderr)
        return 1
    except FileNotFoundError:
        err = GrooveScriptError(message=f"input file not found: {input_path}")
        print(err.render(), file=sys.stderr)
        return 1
    style_warnings = []
    if with_style:
        source = Path(input_path).read_text()
        style_warnings = check_style(source, song)
        for w in style_warnings:
            print(w.render(filename=input_path, source=source), file=sys.stderr)
    ir = None
    if song.grooves or song.sections:
        try:
            ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
        except GrooveScriptError as err:
            _attach_source_context(err, input_path)
            print(err.render(), file=sys.stderr)
            return 1
        except ValueError as err:
            print(
                GrooveScriptError(message=str(err), filename=input_path).render(),
                file=sys.stderr,
            )
            return 1
    notation_warnings = check_notation(ir) if ir is not None else []
    if notation_warnings:
        notation_source = Path(input_path).read_text()
        for w in notation_warnings:
            print(
                w.render(filename=input_path, source=notation_source),
                file=sys.stderr,
            )
    if style_warnings:
        noun = "warning" if len(style_warnings) == 1 else "warnings"
        print(f"{len(style_warnings)} style {noun} in {input_path}")
    if notation_warnings:
        noun = "warning" if len(notation_warnings) == 1 else "warnings"
        print(f"{len(notation_warnings)} notation {noun} in {input_path}")
    if style_warnings or notation_warnings:
        return 1
    print(f"OK: {input_path}")
    return 0


def _run_midi(input_path: str, output_path: str) -> int:
    """Run the MIDI export pipeline once. Returns the exit code (0 on success)."""
    rc = _check_output_not_input(input_path, output_path)
    if rc is not None:
        return rc
    try:
        song = parse_file(input_path)
    except GrooveScriptError as err:
        print(err.render(), file=sys.stderr)
        return 1
    except FileNotFoundError:
        err = GrooveScriptError(message=f"input file not found: {input_path}")
        print(err.render(), file=sys.stderr)
        return 1
    if not song.grooves and not song.sections:
        err = GrooveScriptError(
            message="no grooves or sections found in input file",
            filename=input_path,
            hint="add at least one 'groove \"name\":' or 'section \"name\":' block",
        )
        print(err.render(), file=sys.stderr)
        return 1
    try:
        ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    except GrooveScriptError as err:
        _attach_source_context(err, input_path)
        print(err.render(), file=sys.stderr)
        return 1
    except ValueError as err:
        print(
            GrooveScriptError(message=str(err), filename=input_path).render(),
            file=sys.stderr,
        )
        return 1
    midi_bytes = emit_midi(ir)
    Path(output_path).write_bytes(midi_bytes)
    print(f"Wrote {output_path}")
    return 0


def _run_musicxml(input_path: str, output_path: str) -> int:
    """Run the MusicXML export pipeline once. Returns the exit code (0 on success)."""
    rc = _check_output_not_input(input_path, output_path)
    if rc is not None:
        return rc
    try:
        song = parse_file(input_path)
    except GrooveScriptError as err:
        print(err.render(), file=sys.stderr)
        return 1
    except FileNotFoundError:
        err = GrooveScriptError(message=f"input file not found: {input_path}")
        print(err.render(), file=sys.stderr)
        return 1
    if not song.grooves and not song.sections:
        err = GrooveScriptError(
            message="no grooves or sections found in input file",
            filename=input_path,
            hint="add at least one 'groove \"name\":' or 'section \"name\":' block",
        )
        print(err.render(), file=sys.stderr)
        return 1
    try:
        ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    except GrooveScriptError as err:
        _attach_source_context(err, input_path)
        print(err.render(), file=sys.stderr)
        return 1
    except ValueError as err:
        print(
            GrooveScriptError(message=str(err), filename=input_path).render(),
            file=sys.stderr,
        )
        return 1
    xml_bytes = emit_musicxml(ir)
    Path(output_path).write_bytes(xml_bytes)
    print(f"Wrote {output_path}")
    return 0


def _run_compile(input_path: str, output_path: str) -> int:
    """Run the compile pipeline once. Returns the exit code (0 on success)."""
    rc = _check_output_not_input(input_path, output_path)
    if rc is not None:
        return rc
    try:
        song = parse_file(input_path)
    except GrooveScriptError as err:
        print(err.render(), file=sys.stderr)
        return 1
    except FileNotFoundError:
        err = GrooveScriptError(message=f"input file not found: {input_path}")
        print(err.render(), file=sys.stderr)
        return 1
    if not song.grooves and not song.sections:
        err = GrooveScriptError(
            message="no grooves or sections found in input file",
            filename=input_path,
            hint="add at least one 'groove \"name\":' or 'section \"name\":' block",
        )
        print(err.render(), file=sys.stderr)
        return 1
    try:
        ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    except GrooveScriptError as err:
        _attach_source_context(err, input_path)
        print(err.render(), file=sys.stderr)
        return 1
    except ValueError as err:
        print(
            GrooveScriptError(message=str(err), filename=input_path).render(),
            file=sys.stderr,
        )
        return 1
    ly_source = emit_lilypond(ir)
    Path(output_path).write_text(ly_source)
    print(f"Wrote {output_path}")
    notation_warnings = check_notation(ir)
    if notation_warnings:
        notation_source = Path(input_path).read_text()
        for w in notation_warnings:
            print(
                w.render(filename=input_path, source=notation_source),
                file=sys.stderr,
            )
    return 0


def _watch(input_path: str, rerun, poll_interval: float = 0.5) -> None:
    """Poll ``input_path`` for mtime changes and invoke ``rerun`` after each
    save. ``rerun`` is a zero-arg callable that runs the underlying lint or
    compile action once; its exit code is printed but not propagated.
    Watch mode runs until interrupted with Ctrl-C, at which point it exits
    cleanly with status 0.
    """
    path = Path(input_path)
    if not path.exists():
        err = GrooveScriptError(message=f"input file not found: {input_path}")
        print(err.render(), file=sys.stderr)
        sys.exit(1)
    last_mtime = path.stat().st_mtime
    # Run once up front so the user sees current status immediately rather
    # than having to save to trigger the first run.
    rerun()
    print(f"watching {input_path} — press Ctrl-C to stop", file=sys.stderr)
    try:
        while True:
            time.sleep(poll_interval)
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                # File may be briefly missing during atomic-save (editors
                # that rename into place). Skip this tick and try again.
                continue
            if mtime != last_mtime:
                last_mtime = mtime
                print(f"\n--- change detected ({input_path}) ---", file=sys.stderr)
                rerun()
    except KeyboardInterrupt:
        print("\nstopped watching", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="groovescript",
        description="Compile GrooveScript (.gs) files to LilyPond notation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_cmd = subparsers.add_parser("compile", help="Compile a .gs file to LilyPond")
    compile_cmd.add_argument("input", help="Input .gs file")
    compile_cmd.add_argument("-o", "--output", required=True, help="Output .ly file")
    compile_cmd.add_argument(
        "--watch",
        action="store_true",
        help="Re-compile on every save until Ctrl-C",
    )

    midi_cmd = subparsers.add_parser("midi", help="Export a .gs file to MIDI (.mid)")
    midi_cmd.add_argument("input", help="Input .gs file")
    midi_cmd.add_argument("-o", "--output", required=True, help="Output .mid file")
    midi_cmd.add_argument(
        "--watch",
        action="store_true",
        help="Re-export on every save until Ctrl-C",
    )

    musicxml_cmd = subparsers.add_parser("musicxml", help="Export a .gs file to MusicXML (.xml)")
    musicxml_cmd.add_argument("input", help="Input .gs file")
    musicxml_cmd.add_argument("-o", "--output", required=True, help="Output .xml file")
    musicxml_cmd.add_argument(
        "--watch",
        action="store_true",
        help="Re-export on every save until Ctrl-C",
    )

    lint_cmd = subparsers.add_parser("lint", help="Parse and validate a .gs file without compiling")
    lint_cmd.add_argument("input", help="Input .gs file")
    lint_cmd.add_argument(
        "--style",
        action="store_true",
        help=(
            "Also report stylistic issues that do not block compilation "
            "(mixed groove styles, unused grooves/fills, dangling `like:` refs)"
        ),
    )
    lint_cmd.add_argument(
        "--watch",
        action="store_true",
        help="Re-lint on every save until Ctrl-C",
    )

    args = parser.parse_args()

    if args.command == "midi":
        if args.watch:
            _watch(args.input, lambda: _run_midi(args.input, args.output))
            return
        sys.exit(_run_midi(args.input, args.output))

    if args.command == "musicxml":
        if args.watch:
            _watch(args.input, lambda: _run_musicxml(args.input, args.output))
            return
        sys.exit(_run_musicxml(args.input, args.output))

    if args.command == "lint":
        if args.watch:
            _watch(args.input, lambda: _run_lint(args.input, args.style))
            return
        sys.exit(_run_lint(args.input, args.style))

    if args.command == "compile":
        if args.watch:
            _watch(args.input, lambda: _run_compile(args.input, args.output))
            return
        sys.exit(_run_compile(args.input, args.output))


if __name__ == "__main__":
    main()
