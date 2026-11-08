"""jobq: put background jobs in the Job Monitor's queue (for Claude, scripts and you).

Queue a job (the runner starts it when its turn comes and what it waits for is over):
  jobq add --name "Deep analysis, 3 books" --after library -- .venv\\Scripts\\python.exe -u scripts\\deep_analysis.py
  jobq add --name "..." --after previous --cwd "C:\\some\\folder" --log my.log -- script.ps1 arg1
  --after: library | stage2 | main | previous (the last job in the queue) | <job id> | pid:<number>   (repeatable)
  --normal: normal priority instead of below normal

A script that runs itself and only reports (prints its id):
  jobq begin --name "..." --pid <its process id> [--log file] [--after library]
  jobq running <id>          when it starts working
  jobq finish <id> --exit N  when it is done

Other: jobq list | jobq remove <id> | jobq move <id> up|down | jobq run-now <id> | jobq pause | jobq resume
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import planned, runner  # noqa: E402
from monitor.util import when  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        at = argv.index("--")
        argv, command = argv[:at], argv[at + 1:]
    parser = argparse.ArgumentParser(prog="jobq", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--cwd")
    add.add_argument("--log")
    add.add_argument("--after", action="append", default=[])
    add.add_argument("--normal", action="store_true")
    # the command: everything from the first word that isn't an option. Needed because PowerShell removes "--"
    # when it calls a script (& jobq.ps1 add ... -- cmd), so the "--" above never arrives from jobq.ps1.
    add.add_argument("rest", nargs=argparse.REMAINDER)
    begin = sub.add_parser("begin")
    begin.add_argument("--name", required=True)
    begin.add_argument("--pid", type=int, required=True)
    begin.add_argument("--log")
    begin.add_argument("--after", action="append", default=[])
    for name in ("running", "remove", "run-now"):
        sub.add_parser(name).add_argument("id")
    finish = sub.add_parser("finish")
    finish.add_argument("id")
    finish.add_argument("--exit", type=int, default=0)
    move = sub.add_parser("move")
    move.add_argument("id")
    move.add_argument("direction", choices=["up", "down"])
    for name in ("list", "pause", "resume"):
        sub.add_parser(name)
    args = parser.parse_args(argv)

    if args.action == "add":
        command = command or args.rest
        if not command:
            parser.error("give the command after --")
        job_id = planned.add(args.name, command, args.cwd, args.after, args.log, "normal" if args.normal else "below")
        runner.wake()
        print(job_id)
    elif args.action == "begin":
        print(planned.begin(args.name, args.pid, args.log, args.after))
    elif args.action == "running":
        planned.running(args.id)
    elif args.action == "finish":
        planned.finish(args.id, args.exit)
        runner.wake()  # a queued job may have been waiting for this one
    elif args.action == "remove":
        planned.remove(args.id)
    elif args.action == "move":
        planned.move(args.id, -1 if args.direction == "up" else 1)
    elif args.action == "run-now":
        planned.run_now(args.id)
        runner.wake()
    elif args.action == "pause":
        planned.pause_queue(True)
    elif args.action == "resume":
        planned.pause_queue(False)
        runner.wake()
    elif args.action == "list":
        entries = planned.load()
        if not entries:
            print("The queue is empty.")
        for e in entries:
            stamp = when(e.get("finished") or e.get("started") or e.get("added"))
            print(f"{e['id']}  {e['state']:<9} {stamp:>9}  {e['name']}  {e.get('step') or ''}".rstrip())
        if planned.queue_paused():
            print("(the queue is paused: jobq resume)")
        print("runner:", "running" if runner.is_running() else "not running", f"({time.strftime('%H:%M:%S')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
