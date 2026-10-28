"""Monthly batch: generate the letters of every client in parallel, unattended.

Run it at month close (a cron job on the server, or the Windows Task Scheduler locally); the
advisor then finds the letters in the platform's review queue. Nothing is sent by e-mail here.

    python -m app.batch            # clients whose letter is missing or failed
    python -m app.batch --all      # every client, again
"""

from __future__ import annotations

import argparse
import time

from core import crm, pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the month's letters for every client")
    parser.add_argument("--all", action="store_true", help="also regenerate letters that already exist")
    parser.add_argument("--workers", type=int, default=pipeline.BATCH_WORKERS)
    args = parser.parse_args()

    pipeline.sync_clients()
    month = pipeline.current_month()
    slugs = [c["slug"] for c in crm.clients(month) if args.all or c["status"] in ("pending", "error")]
    start = time.time()
    results = pipeline.generate_batch(slugs, month, args.workers,
                                      on_done=lambda r: print(f"{r['slug']}: {r['status']} {r.get('error', '')}"))
    ok = sum(r["status"] != "error" for r in results)
    print(f"{ok}/{len(results)} letters in {time.time() - start:.0f}s; review them on the platform")


if __name__ == "__main__":
    main()
