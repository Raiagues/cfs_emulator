# CPU1 module selection. Startup controls which installed modules are loaded.
set(MISSION_CPU1_ADDED_MODULES )
set(MISSION_CPU1_REMOVED_MODULES )

# Preserve each CPU's global modules before changing CPU1 membership.
foreach(CPU IN LISTS MISSION_CPUNAMES)
    list(APPEND ${CPU}_APPLIST ${MISSION_GLOBAL_APPLIST})
endforeach()
set(MISSION_GLOBAL_APPLIST)
list(APPEND cpu1_APPLIST ${MISSION_CPU1_ADDED_MODULES})
if(MISSION_CPU1_REMOVED_MODULES)
    list(REMOVE_ITEM cpu1_APPLIST ${MISSION_CPU1_REMOVED_MODULES})
endif()
list(REMOVE_DUPLICATES cpu1_APPLIST)
