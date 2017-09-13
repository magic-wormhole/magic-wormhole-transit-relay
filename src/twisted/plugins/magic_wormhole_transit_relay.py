from twisted.application.service import ServiceMaker

TransitRelay = ServiceMaker(
    "Magic-Wormhole Transit Relay", # name
    "wormhole_transit_relay.server_tap", # module
    "Provide the Transit Relay server for Magic-Wormhole clients.", # desc
    "transitrelay", # tapname
    )
