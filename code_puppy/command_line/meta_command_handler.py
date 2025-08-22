import os
from difflib import unified_diff

from rich.console import Console

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    update_model_in_input,
)
from code_puppy.config import get_config_keys
from code_puppy.command_line.utils import make_directory_table
from code_puppy.command_line.motd import print_motd
from code_puppy.version_store import (
    list_versions,
    get_changes_for_version,
    get_response_by_version,
    list_all_versions,
    get_response_by_id,
    get_changes_for_response_id,
    compute_snapshot_as_of_response_id,
    get_response_id_for_prompt_version,
    get_db_path,
)

META_COMMANDS_HELP = """
[bold magenta]Meta Commands Help[/bold magenta]
~help, ~h             Show this help message
~cd <dir>             Change directory or show directories
~m <model>            Set active model
~motd                 Show the latest message of the day (MOTD)
~show                 Show puppy config key-values
~set                  Set puppy config key-values
~versions [<prompt>]  List recent versions globally (optionally filter by prompt)
~show-version <prompt> <version>
                      Show the saved output for a specific version
~show-id <response_id>
                      Show the saved output by response ID
~changes <prompt> <version> [--patch]
                      List files changed in a version (and show diffs with --patch)
~changes-id <response_id> [--patch]
                      List files changed for a response ID (and show diffs)
~checkout-version <prompt> <version>
                      Restore codebase files to the saved state for that version
~checkout-id <response_id>
                      Restore files to AFTER state recorded for that response ID
~checkout-snapshot-id <response_id> [--patch]
                      Restore tracked files to the snapshot as-of that response ID
~checkout-snapshot-version <prompt> <version> [--patch]
                      Restore tracked files to the snapshot resolved via prompt/version
~undo-last <prompt>   Revert files touched in the latest version for the prompt
~undo-id <response_id>
                      Revert files to BEFORE state recorded for that response ID
~redo                 Re-run last prompt (handled inside interactive REPL)
~db-path              Show the SQLite DB path used for versioning
~<unknown>            Show unknown meta command warning
"""


def handle_meta_command(command: str, console: Console) -> bool:
    """
    Handle meta/config commands prefixed with '~'.
    Returns True if the command was handled (even if just an error/help), False if not.
    """
    command = command.strip()

    if command.strip().startswith("~motd"):
        print_motd(console, force=True)
        return True

    if command.strip() == "~db-path":
        try:
            console.print(f"[dim]Version store DB:[/dim] {get_db_path()}")
        except Exception as e:
            console.print(f"[red]Error resolving DB path:[/red] {e}")
        return True

    if command.startswith("~show-id"):
        # Syntax: ~show-id <response_id>
        args_str = command[len("~show-id") :].strip()
        if not args_str:
            console.print("[yellow]Usage:[/yellow] ~show-id <response_id>")
            return True
        try:
            rid = int(args_str.split()[0])
        except ValueError:
            console.print("[yellow]Response ID must be an integer.[/yellow]")
            return True
        try:
            resp = get_response_by_id(rid)
            if not resp:
                console.print("[dim]No saved output for that ID.[/dim]")
                return True
            output = resp.get("output_text", "")
            ts = resp.get("timestamp", "")
            ver = resp.get("version", "")
            console.print(
                f"[bold magenta]Output for id={rid} v{ver} at {ts}[/bold magenta]"
            )
            console.print(output)
        except Exception as e:
            console.print(f"[red]Error loading output:[/red] {e}")
        return True

    # --- Versioning meta commands ---
    if command.startswith("~versions"):
        arg = command[len("~versions") :].strip()
        try:
            if arg:
                rows = list(list_versions(arg))
                if not rows:
                    console.print("[dim]No versions found for that prompt.[/dim]")
                    return True
                console.print("[bold magenta]Saved Versions[/bold magenta]")
                for rid, ver, ts in rows:
                    console.print(f"- id={rid}  v{ver}  at {ts}")
            else:
                rows = list(list_all_versions(limit=20))
                if not rows:
                    console.print("[dim]No versions recorded yet.[/dim]")
                    return True
                console.print("[bold magenta]Recent Versions (global)[/bold magenta]")
                for rid, ptext, ver, ts in rows:
                    pshort = (ptext[:80] + "…") if len(ptext) > 80 else ptext
                    console.print(f"- id={rid}  v{ver}  at {ts}\n  prompt: {pshort}")
        except Exception as e:
            console.print(f"[red]Error listing versions:[/red] {e}")
        return True

    if command.startswith("~show-version"):
        # Syntax: ~show-version <prompt> <version>
        args_str = command[len("~show-version") :].strip()
        if not args_str:
            console.print("[yellow]Usage:[/yellow] ~show-version <prompt> <version>")
            return True
        tokens = args_str.split()
        if not tokens:
            console.print("[yellow]Usage:[/yellow] ~show-version <prompt> <version>")
            return True
        try:
            version = int(tokens[-1])
        except ValueError:
            console.print("[yellow]Version must be an integer.[/yellow]")
            return True
        prompt_text = args_str[: args_str.rfind(str(version))].strip()
        if not prompt_text:
            console.print("[yellow]Please provide the full prompt text.[/yellow]")
            return True
        try:
            resp = get_response_by_version(prompt_text, version)
            if not resp:
                console.print("[dim]No saved output for that prompt/version.[/dim]")
                return True
            output = resp.get("output_text", "")
            ts = resp.get("timestamp", "")
            console.print(f"[bold magenta]Output for v{version} at {ts}[/bold magenta]")
            console.print(output)
        except Exception as e:
            console.print(f"[red]Error loading version output:[/red] {e}")
        return True

    if command.startswith("~changes"):
        # Syntax: ~changes <prompt> <version> [--patch]
        args_str = command[len("~changes") :].strip()
        if not args_str:
            console.print(
                "[yellow]Usage:[/yellow] ~changes <prompt> <version> [--patch]"
            )
            return True
        show_patch = "--patch" in args_str
        if show_patch:
            args_str = args_str.replace("--patch", "").strip()
        # last token must be version
        tokens = args_str.split()
        if not tokens:
            console.print(
                "[yellow]Usage:[/yellow] ~changes <prompt> <version> [--patch]"
            )
            return True
        try:
            version = int(tokens[-1])
        except ValueError:
            console.print("[yellow]Version must be an integer.[/yellow]")
            return True
        prompt_text = args_str[: args_str.rfind(str(version))].strip()
        if not prompt_text:
            console.print("[yellow]Please provide the full prompt text.[/yellow]")
            return True
        try:
            changes = list(get_changes_for_version(prompt_text, version))
            if not changes:
                console.print("[dim]No recorded changes for that version.[/dim]")
                return True
            console.print(
                f"[bold magenta]Changes for version v{version}[/bold magenta]"
            )
            for ch in changes:
                fp = ch.get("file_path", "")
                ctype = ch.get("change_type", "")
                console.print(f"- [{ctype}] {fp}")
                if show_patch:
                    diff = ch.get("diff") or ""
                    if isinstance(diff, (bytes, bytearray)):
                        diff = diff.decode("utf-8", errors="replace")
                    if diff.strip():
                        console.print("[dim]\n--- diff ---[/dim]")
                        for line in str(diff).splitlines():
                            if line.startswith("+") and not line.startswith("+++"):
                                console.print(f"[green]{line}[/green]")
                            elif line.startswith("-") and not line.startswith("---"):
                                console.print(f"[red]{line}[/red]")
                            else:
                                console.print(line)
        except Exception as e:
            console.print(f"[red]Error loading changes:[/red] {e}")
        return True

    if command.startswith("~changes-id"):
        # Syntax: ~changes-id <response_id> [--patch]
        args_str = command[len("~changes-id") :].strip()
        if not args_str:
            console.print("[yellow]Usage:[/yellow] ~changes-id <response_id> [--patch]")
            return True
        show_patch = "--patch" in args_str
        if show_patch:
            args_str = args_str.replace("--patch", "").strip()
        try:
            rid = int(args_str.split()[0])
        except ValueError:
            console.print("[yellow]Response ID must be an integer.[/yellow]")
            return True
        try:
            changes = list(get_changes_for_response_id(rid))
            if not changes:
                console.print("[dim]No recorded changes for that response ID.[/dim]")
                return True
            console.print(f"[bold magenta]Changes for id={rid}[/bold magenta]")
            for ch in changes:
                fp = ch.get("file_path", "")
                ctype = ch.get("change_type", "")
                console.print(f"- [{ctype}] {fp}")
                if show_patch:
                    diff = ch.get("diff") or ""
                    if isinstance(diff, (bytes, bytearray)):
                        diff = diff.decode("utf-8", errors="replace")
                    if str(diff).strip():
                        console.print("[dim]\n--- diff ---[/dim]")
                        for line in str(diff).splitlines():
                            if line.startswith("+") and not line.startswith("+++"):
                                console.print(f"[green]{line}[/green]")
                            elif line.startswith("-") and not line.startswith("---"):
                                console.print(f"[red]{line}[/red]")
                            else:
                                console.print(line)
        except Exception as e:
            console.print(f"[red]Error loading changes:[/red] {e}")
        return True

    if command.startswith("~checkout-version"):
        # Syntax: ~checkout-version <prompt> <version>
        args_str = command[len("~checkout-version") :].strip()
        tokens = args_str.split()
        if not tokens or len(tokens) < 2:
            console.print(
                "[yellow]Usage:[/yellow] ~checkout-version <prompt> <version>"
            )
            return True
        try:
            version = int(tokens[-1])
        except ValueError:
            console.print("[yellow]Version must be an integer.[/yellow]")
            return True
        prompt_text = args_str[: args_str.rfind(str(version))].strip()
        if not prompt_text:
            console.print("[yellow]Please provide the full prompt text.[/yellow]")
            return True
        # Confirm
        try:
            ans = input(
                "[confirm] Restore files to recorded AFTER state for this version? (y/N): "
            ).strip()
        except Exception:
            ans = "n"
        if ans.lower() not in ("y", "yes"):
            console.print("[dim]Checkout cancelled.[/dim]")
            return True
        try:
            count = 0
            for ch in get_changes_for_version(prompt_text, version):
                fp = ch.get("file_path")
                after = ch.get("after_content")
                ctype = (ch.get("change_type") or "").lower()
                # Normalize content to str
                if isinstance(after, (bytes, bytearray)):
                    after = after.decode("utf-8", errors="replace")
                try:
                    if after is None or ctype == "delete":
                        if fp and os.path.exists(fp):
                            os.remove(fp)
                            count += 1
                    else:
                        if fp:
                            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(after)
                            count += 1
                except Exception as fe:
                    console.print(f"[red]Failed applying {fp}: {fe}[/red]")
            console.print(f"[green]Checkout completed.[/green] Files touched: {count}")
        except Exception as e:
            console.print(f"[red]Checkout failed:[/red] {e}")
        return True

    if command.startswith("~checkout-snapshot-id"):
        # Syntax: ~checkout-snapshot-id <response_id> [--patch]
        args_str = command[len("~checkout-snapshot-id") :].strip()
        if not args_str:
            console.print(
                "[yellow]Usage:[/yellow] ~checkout-snapshot-id <response_id> [--patch]"
            )
            return True
        show_patch = "--patch" in args_str
        if show_patch:
            args_str = args_str.replace("--patch", "").strip()
        try:
            rid = int(args_str.split()[0])
        except ValueError:
            console.print("[yellow]Response ID must be an integer.[/yellow]")
            return True
        try:
            snapshot = list(compute_snapshot_as_of_response_id(rid))
            if not snapshot:
                console.print("[dim]No tracked files yet; nothing to do.[/dim]")
                return True
            # Determine operations
            ops = []  # {op: 'write'|'delete', file_path, new_content, current}
            write_count = 0
            delete_count = 0
            for item in snapshot:
                fp = item.get("file_path")
                desired = item.get("content")
                current = None
                exists = os.path.exists(fp) if fp else False
                if exists and fp:
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            current = f.read()
                    except Exception:
                        current = None
                if desired is None:
                    if exists:
                        ops.append(
                            {"op": "delete", "file_path": fp, "current": current}
                        )
                        delete_count += 1
                    # else: file doesn't exist and should not exist => noop
                else:
                    if current != desired:
                        ops.append(
                            {
                                "op": "write",
                                "file_path": fp,
                                "new_content": desired,
                                "current": current or "",
                            }
                        )
                        write_count += 1
            console.print(
                f"[bold magenta]Snapshot checkout[/bold magenta] for id={rid}: will [green]write {write_count}[/green], [red]delete {delete_count}[/red]"
            )
            if show_patch and ops:
                console.print("[dim]\n--- Planned changes (unified diff) ---[/dim]")
                for op in ops:
                    fp = op["file_path"]
                    if op["op"] == "delete":
                        before = (op.get("current") or "").splitlines(keepends=True)
                        after = []
                    else:
                        before = (op.get("current") or "").splitlines(keepends=True)
                        after = (op.get("new_content") or "").splitlines(keepends=True)
                    diff = "".join(
                        unified_diff(
                            before,
                            after,
                            fromfile=f"a/{fp}",
                            tofile=f"b/{fp}",
                        )
                    )
                    if diff.strip():
                        console.print(diff, highlight=False)
            # Confirm
            try:
                ans = input(
                    f"[confirm] Apply snapshot? Writes: {write_count}, Deletes: {delete_count} (y/N): "
                ).strip()
            except Exception:
                ans = "n"
            if ans.lower() not in ("y", "yes"):
                console.print("[dim]Snapshot checkout cancelled.[/dim]")
                return True
            # Apply
            applied = 0
            for op in ops:
                fp = op["file_path"]
                try:
                    if op["op"] == "delete":
                        if fp and os.path.exists(fp):
                            os.remove(fp)
                            applied += 1
                    else:  # write
                        content = op.get("new_content") or ""
                        if fp:
                            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(content)
                            applied += 1
                except Exception as fe:
                    console.print(f"[red]Failed applying {fp}: {fe}[/red]")
            console.print(
                f"[green]Snapshot checkout complete.[/green] Files changed: {applied}"
            )
        except Exception as e:
            console.print(f"[red]Snapshot checkout failed:[/red] {e}")
        return True

    if command.startswith("~checkout-snapshot-version"):
        # Syntax: ~checkout-snapshot-version <prompt> <version> [--patch]
        args_str = command[len("~checkout-snapshot-version") :].strip()
        if not args_str:
            console.print(
                "[yellow]Usage:[/yellow] ~checkout-snapshot-version <prompt> <version> [--patch]"
            )
            return True
        show_patch = "--patch" in args_str
        if show_patch:
            args_str = args_str.replace("--patch", "").strip()
        tokens = args_str.split()
        if not tokens or len(tokens) < 2:
            console.print(
                "[yellow]Usage:[/yellow] ~checkout-snapshot-version <prompt> <version> [--patch]"
            )
            return True
        try:
            version = int(tokens[-1])
        except ValueError:
            console.print("[yellow]Version must be an integer.[/yellow]")
            return True
        prompt_text = args_str[: args_str.rfind(str(version))].strip()
        if not prompt_text:
            console.print("[yellow]Please provide the full prompt text.[/yellow]")
            return True
        try:
            rid = get_response_id_for_prompt_version(prompt_text, version)
            if rid is None:
                console.print("[dim]No response found for that prompt/version.[/dim]")
                return True
            # Reuse the same logic by constructing a synthetic command body
            internal = (
                f"~checkout-snapshot-id {rid} {'--patch' if show_patch else ''}".strip()
            )
            # Recursively handle using this same function
            return handle_meta_command(internal, console)
        except Exception as e:
            console.print(f"[red]Snapshot checkout failed:[/red] {e}")
        return True

    if command.startswith("~checkout-id"):
        # Syntax: ~checkout-id <response_id>
        args_str = command[len("~checkout-id") :].strip()
        if not args_str:
            console.print("[yellow]Usage:[/yellow] ~checkout-id <response_id>")
            return True
        try:
            rid = int(args_str.split()[0])
        except ValueError:
            console.print("[yellow]Response ID must be an integer.[/yellow]")
            return True
        # Confirm
        try:
            ans = input(
                "[confirm] Restore files to recorded AFTER state for this response? (y/N): "
            ).strip()
        except Exception:
            ans = "n"
        if ans.lower() not in ("y", "yes"):
            console.print("[dim]Checkout cancelled.[/dim]")
            return True
        try:
            count = 0
            for ch in get_changes_for_response_id(rid):
                fp = ch.get("file_path")
                after = ch.get("after_content")
                ctype = (ch.get("change_type") or "").lower()
                if isinstance(after, (bytes, bytearray)):
                    after = after.decode("utf-8", errors="replace")
                try:
                    if after is None or ctype == "delete":
                        if fp and os.path.exists(fp):
                            os.remove(fp)
                            count += 1
                    else:
                        if fp:
                            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(after)
                            count += 1
                except Exception as fe:
                    console.print(f"[red]Failed applying {fp}: {fe}[/red]")
            console.print(f"[green]Checkout completed.[/green] Files touched: {count}")
        except Exception as e:
            console.print(f"[red]Checkout failed:[/red] {e}")
        return True

    if command.startswith("~undo-last"):
        # Syntax: ~undo-last <prompt>
        prompt_text = command[len("~undo-last") :].strip()
        if not prompt_text:
            console.print("[yellow]Usage:[/yellow] ~undo-last <prompt>")
            return True
        try:
            vers = list(list_versions(prompt_text))
            if not vers:
                console.print("[dim]No versions to undo for that prompt.[/dim]")
                return True
            last_id, last_ver, _ = vers[-1]
        except Exception as e:
            console.print(f"[red]Error resolving last version:[/red] {e}")
            return True
        # Confirm
        try:
            ans = input(
                f"[confirm] Revert files to BEFORE state for version v{last_ver}? (y/N): "
            ).strip()
        except Exception:
            ans = "n"
        if ans.lower() not in ("y", "yes"):
            console.print("[dim]Undo cancelled.[/dim]")
            return True
        try:
            count = 0
            for ch in get_changes_for_version(prompt_text, last_ver):
                fp = ch.get("file_path")
                before = ch.get("before_content")
                ctype = (ch.get("change_type") or "").lower()
                if isinstance(before, (bytes, bytearray)):
                    before = before.decode("utf-8", errors="replace")
                try:
                    if before is None or (ctype == "create"):
                        if fp and os.path.exists(fp):
                            os.remove(fp)
                            count += 1
                    else:
                        if fp:
                            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(before)
                            count += 1
                except Exception as fe:
                    console.print(f"[red]Failed applying {fp}: {fe}[/red]")
            console.print(
                f"[green]Undo completed.[/green] Files reverted from v{last_ver}: {count}"
            )
        except Exception as e:
            console.print(f"[red]Undo failed:[/red] {e}")
        return True

    if command.startswith("~undo-id"):
        # Syntax: ~undo-id <response_id>
        args_str = command[len("~undo-id") :].strip()
        if not args_str:
            console.print("[yellow]Usage:[/yellow] ~undo-id <response_id>")
            return True
        try:
            rid = int(args_str.split()[0])
        except ValueError:
            console.print("[yellow]Response ID must be an integer.[/yellow]")
            return True
        # Confirm
        try:
            ans = input(
                "[confirm] Revert files to BEFORE state for this response? (y/N): "
            ).strip()
        except Exception:
            ans = "n"
        if ans.lower() not in ("y", "yes"):
            console.print("[dim]Undo cancelled.[/dim]")
            return True
        try:
            count = 0
            for ch in get_changes_for_response_id(rid):
                fp = ch.get("file_path")
                before = ch.get("before_content")
                ctype = (ch.get("change_type") or "").lower()
                if isinstance(before, (bytes, bytearray)):
                    before = before.decode("utf-8", errors="replace")
                try:
                    if before is None or (ctype == "create"):
                        if fp and os.path.exists(fp):
                            os.remove(fp)
                            count += 1
                    else:
                        if fp:
                            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(before)
                            count += 1
                except Exception as fe:
                    console.print(f"[red]Failed applying {fp}: {fe}[/red]")
            console.print(f"[green]Undo completed.[/green] Files reverted: {count}")
        except Exception as e:
            console.print(f"[red]Undo failed:[/red] {e}")
        return True

    if command.startswith("~cd"):
        tokens = command.split()
        if len(tokens) == 1:
            try:
                table = make_directory_table()
                console.print(table)
            except Exception as e:
                console.print(f"[red]Error listing directory:[/red] {e}")
            return True
        elif len(tokens) == 2:
            dirname = tokens[1]
            target = os.path.expanduser(dirname)
            if not os.path.isabs(target):
                target = os.path.join(os.getcwd(), target)
            if os.path.isdir(target):
                os.chdir(target)
                console.print(
                    f"[bold green]Changed directory to:[/bold green] [cyan]{target}[/cyan]"
                )
            else:
                console.print(f"[red]Not a directory:[/red] [bold]{dirname}[/bold]")
            return True

    if command.strip().startswith("~show"):
        from code_puppy.command_line.model_picker_completion import get_active_model
        from code_puppy.config import (
            get_owner_name,
            get_puppy_name,
            get_yolo_mode,
            get_message_history_limit,
        )

        puppy_name = get_puppy_name()
        owner_name = get_owner_name()
        model = get_active_model()
        yolo_mode = get_yolo_mode()
        msg_limit = get_message_history_limit()
        console.print(f"""[bold magenta]🐶 Puppy Status[/bold magenta]

[bold]puppy_name:[/bold]     [cyan]{puppy_name}[/cyan]
[bold]owner_name:[/bold]     [cyan]{owner_name}[/cyan]
[bold]model:[/bold]          [green]{model}[/green]
[bold]YOLO_MODE:[/bold]      {"[red]ON[/red]" if yolo_mode else "[yellow]off[/yellow]"}
[bold]message_history_limit:[/bold]   Keeping last [cyan]{msg_limit}[/cyan] messages in context
""")
        return True

    if command.startswith("~set"):
        # Syntax: ~set KEY=VALUE or ~set KEY VALUE
        from code_puppy.config import set_config_value

        tokens = command.split(None, 2)
        argstr = command[len("~set") :].strip()
        key = None
        value = None
        if "=" in argstr:
            key, value = argstr.split("=", 1)
            key = key.strip()
            value = value.strip()
        elif len(tokens) >= 3:
            key = tokens[1]
            value = tokens[2]
        elif len(tokens) == 2:
            key = tokens[1]
            value = ""
        else:
            console.print(
                f"[yellow]Usage:[/yellow] ~set KEY=VALUE or ~set KEY VALUE\nConfig keys: {', '.join(get_config_keys())}"
            )
            return True
        if key:
            set_config_value(key, value)
            console.print(
                f'[green]🌶 Set[/green] [cyan]{key}[/cyan] = "{value}" in puppy.cfg!'
            )
        else:
            console.print("[red]You must supply a key.[/red]")
        return True

    if command.startswith("~m"):
        # Try setting model and show confirmation
        new_input = update_model_in_input(command)
        if new_input is not None:
            from code_puppy.command_line.model_picker_completion import get_active_model
            from code_puppy.agent import get_code_generation_agent

            model = get_active_model()
            # Make sure this is called for the test
            get_code_generation_agent(force_reload=True)
            console.print(
                f"[bold green]Active model set and loaded:[/bold green] [cyan]{model}[/cyan]"
            )
            return True
        # If no model matched, show available models
        model_names = load_model_names()
        console.print("[yellow]Usage:[/yellow] ~m <model-name>")
        console.print(f"[yellow]Available models:[/yellow] {', '.join(model_names)}")
        return True
    if command in ("~help", "~h"):
        console.print(META_COMMANDS_HELP)
        return True
    if command.startswith("~"):
        name = command[1:].split()[0] if len(command) > 1 else ""
        if name:
            console.print(
                f"[yellow]Unknown meta command:[/yellow] {command}\n[dim]Type ~help for options.[/dim]"
            )
        else:
            # Show current model ONLY here
            from code_puppy.command_line.model_picker_completion import get_active_model

            current_model = get_active_model()
            console.print(
                f"[bold green]Current Model:[/bold green] [cyan]{current_model}[/cyan]"
            )
        return True
    return False
