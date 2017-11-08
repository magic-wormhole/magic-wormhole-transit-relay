"""Migrate the usage data from the old bundled Transit Relay database.

The magic-wormhole package used to include both servers (Rendezvous and
Transit). "wormhole server" started both of these, and used the
"relay.sqlite" database to store both immediate server state and long-term
usage data.

These were split out to their own packages: version 0.11 omitted the Transit
Relay in favor of the new "magic-wormhole-transit-relay" distribution.

This script reads the long-term Transit usage data from the pre-0.11
wormhole-server relay.sqlite, and copies it into a new "usage.sqlite"
database in the current directory.

It will refuse to touch an existing "usage.sqlite" file.

The resuting "usage.sqlite" should be passed into --usage-db=, e.g. "twist
transitrelay --usage=.../PATH/TO/usage.sqlite".
"""

from __future__ import unicode_literals, print_function
import sys
from wormhole_transit_relay.database import open_existing_db, create_db

source_fn = sys.argv[1]
source_db = open_existing_db(source_fn)
target_db = create_db("usage.sqlite")

num_rows = 0
for row in source_db.execute("SELECT * FROM `transit_usage`"
                             " ORDER BY `started`").fetchall():
    target_db.execute("INSERT INTO `usage`"
                      " (`started`, `total_time`, `waiting_time`,"
                      "  `total_bytes`, `result`)"
                      " VALUES(?,?,?,?,?)",
                      (row["started"], row["total_time"], row["waiting_time"],
                       row["total_bytes"], row["result"]))
    num_rows += 1
target_db.execute("INSERT INTO `current`"
                  " (`rebooted`, `updated`, `connected`, `waiting`,"
                  "  `incomplete_bytes`)"
                  " VALUES(?,?,?,?,?)",
                  (0, 0, 0, 0, 0))
target_db.commit()

print("usage database migrated (%d rows) into 'usage.sqlite'" % num_rows)
sys.exit(0)
