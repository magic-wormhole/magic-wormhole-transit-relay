
CREATE TABLE `version` -- contains one row
(
 `version` INTEGER -- set to 1
);


CREATE TABLE `current` -- contains one row
(
 `rebooted` INTEGER, -- seconds since epoch of most recent reboot
 `updated` INTEGER, -- when `current` was last updated
 `connected` INTEGER, -- number of current paired connections
 `waiting` INTEGER, -- number of not-yet-paired connections
 `incomplete_bytes` INTEGER -- bytes sent through not-yet-complete connections
);

CREATE TABLE `usage`
(
 `started` INTEGER, -- seconds since epoch, rounded to "blur time"
 `total_time` INTEGER, -- seconds from open to last close
 `waiting_time` INTEGER, -- seconds from start to 2nd side appearing, or None
 `total_bytes` INTEGER, -- total bytes relayed (both directions)
 `result` VARCHAR -- happy, scary, lonely, errory, pruney
 -- transit moods:
 --  "errory": one side gave the wrong handshake
 --  "lonely": good handshake, but the other side never showed up
 --  "happy": both sides gave correct handshake
);
CREATE INDEX `usage_started_index` ON `usage` (`started`);
CREATE INDEX `usage_result_index` ON `usage` (`result`);
