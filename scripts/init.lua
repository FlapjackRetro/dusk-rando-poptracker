-- DUSK Archipelago PopTracker pack
ENABLE_DEBUG_LOG = false

ScriptHost:LoadScript("scripts/logic/data.lua")
ScriptHost:LoadScript("scripts/logic/regions.lua")
ScriptHost:LoadScript("scripts/logic/logic.lua")

Tracker:AddItems("items/items.json")
Tracker:AddMaps("maps/maps.json")
Tracker:AddLocations("locations/episode1.json")
Tracker:AddLocations("locations/episode2.json")
Tracker:AddLocations("locations/episode3.json")

Tracker:AddLayouts("layouts/items.json")
Tracker:AddLayouts("layouts/tabs.json")
Tracker:AddLayouts("layouts/tracker.json")
Tracker:AddLayouts("layouts/broadcast.json")

if PopVersion and PopVersion >= "0.18.0" then
    ScriptHost:LoadScript("scripts/autotracking.lua")
end
