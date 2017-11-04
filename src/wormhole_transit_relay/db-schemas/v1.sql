
CREATE TABLE `version` -- contains one row
(
 `version` INTEGER -- set to 1
);


CREATE TABLE `current` -- contains one row
(
 `reboot` INTEGER, -- seconds since epoch of most recent reboot
 `last_update` INTEGER, -- when `current` was last updated
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
CREATE INDEX `transit_usage_idx` ON `transit_usage` (`started`);
CREATE INDEX `transit_usage_result_idx` ON `transit_usage` (`result`);
