
# For the native builds, include a wrapper script to start cFS on the container.
if (${SIMULATION} MATCHES "^native")
    install(PROGRAMS ${CMAKE_CURRENT_LIST_DIR}/container-start DESTINATION cpu1)
endif()

set(APP_DEFINITION_TABLE_LIST)
set(APP_INCLUDE_TABLE_LIST












)

if (TARGET sbn)
    list(APPEND APP_DEFINITION_TABLE_LIST
        CFS_SBN_ENABLED
    )
    list(APPEND APP_INCLUDE_TABLE_LIST

    )
endif()

# specify extra include dirs for to_lab + sch_lab table builds
list(APPEND APP_DEFINITION_TABLE_LIST APPGEN_ENABLED)
list(APPEND APP_INCLUDE_TABLE_LIST ${MISSION_DEFS}/generated)
foreach(APP IN LISTS APPGEN_APPS)
    if(TARGET ${APP})
        list(APPEND APP_INCLUDE_TABLE_LIST $<TARGET_PROPERTY:${APP},INCLUDE_DIRECTORIES>)
    endif()
endforeach()

set(STUDIO_STARTUP "${MISSION_DEFS}/../cpu1_cfe_es_startup.scr")
if(EXISTS "${STUDIO_STARTUP}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${STUDIO_STARTUP}")
    file(STRINGS "${STUDIO_STARTUP}" STUDIO_ACTIVE_LINES REGEX "^[ \t]*CFE_(APP|LIB),")
    set(STUDIO_LOADED_MODULES)
    foreach(RECORD IN LISTS STUDIO_ACTIVE_LINES)
        string(REGEX REPLACE "^[^,]+,[ \t]*([^, \t]+).*" "\\1" ACTIVE_MODULE "${RECORD}")
        list(APPEND STUDIO_LOADED_MODULES "${ACTIVE_MODULE}")
    endforeach()
endif()
list(APPEND APP_DEFINITION_TABLE_LIST CFS_CPU1_MODULE_SELECTION)
foreach(MODULE IN LISTS ${TGTNAME}_APPLIST)
    if(TARGET ${MODULE})
        string(TOUPPER "${MODULE}" MODULE_SYMBOL)
        if(NOT EXISTS "${STUDIO_STARTUP}" OR MODULE IN_LIST STUDIO_LOADED_MODULES)
            list(APPEND APP_DEFINITION_TABLE_LIST "CFS_MODULE_${MODULE_SYMBOL}")
        endif()
        list(APPEND APP_INCLUDE_TABLE_LIST $<TARGET_PROPERTY:${MODULE},INCLUDE_DIRECTORIES>)
    endif()
endforeach()

if(TARGET to_lab.table)
    target_include_directories(to_lab.table INTERFACE ${APP_INCLUDE_TABLE_LIST})
endif()
if(TARGET to_lab.table)
    target_compile_definitions(to_lab.table INTERFACE ${APP_DEFINITION_TABLE_LIST})
endif()
if(TARGET sch_lab.table)
    target_include_directories(sch_lab.table INTERFACE ${APP_INCLUDE_TABLE_LIST})
endif()
if(TARGET sch_lab.table)
    target_compile_definitions(sch_lab.table INTERFACE ${APP_DEFINITION_TABLE_LIST})
endif()

# An example of an alternate table load file
if(TARGET sample_app)
    add_cfe_tables(sample_app sample_app_alt1.c)
endif()
if(TARGET to_lab)
    add_cfe_tables(to_lab to_lab_sub_alt.c)
endif()
if(TARGET to_lab)
    add_cfe_tables(to_lab to_lab_sub_bad.c)
endif()
if(TARGET lc)
    add_cfe_tables(lc lc_def_adt-test.c)
endif()
if(TARGET sc)
    add_cfe_tables(sc sc_ats2_test.c)
endif()
if(TARGET sc)
    add_cfe_tables(sc sc_append_test.c)
endif()

# This executes the startup script generator
install(SCRIPT ${MISSION_DEFS}/generate_startup.cmake)
install(CODE "generate_cfs_startup_script(\"${TGTNAME}/${INSTALL_SUBDIR}\" ${${TGTNAME}_APPLIST})")
