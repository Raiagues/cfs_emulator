project(CFE_HAL_TEMP C)

if(CFE_EDS_ENABLED)
  message(FATAL_ERROR "Studio mission extensions require the non-EDS build profile.")
endif()

set(APP_SRC_FILES
  fsw/src/hal_temp.c
  fsw/src/hal_temp_cmds.c
  fsw/src/hal_temp_utils.c
)

if (CFE_EDS_ENABLED)
  list(APPEND APP_SRC_FILES
    fsw/src/hal_temp_eds_dispatch.c
  )
else()
  list(APPEND APP_SRC_FILES
    fsw/src/hal_temp_dispatch.c
  )
endif()

list(APPEND APP_SRC_FILES
# APPGEN BEGIN SOURCES
    fsw/src/hal_temp_components.c
    fsw/src/hal_temp_user.c
    fsw/src/sensors/hal_temp_sample_sensor.c
# APPGEN END SOURCES
)

# Create the app module
add_cfe_app(hal_temp ${APP_SRC_FILES})

target_include_directories(hal_temp PUBLIC fsw/inc)
# Include the public API from sample_lib to demonstrate how
# to call library-provided functions
add_cfe_app_dependency(hal_temp sample_lib)

target_include_directories(hal_temp PRIVATE fsw/src)
# APPGEN BEGIN DEPENDENCIES
add_cfe_app_dependency(hal_temp linux_i2c_lib)
add_cfe_app_dependency(hal_temp tmp105_lib)
# APPGEN END DEPENDENCIES

# Add table
add_cfe_tables(hal_temp fsw/tables/hal_temp_tbl.c)

# If UT is enabled, then add the tests from the subdirectory
# Note that this is an app, and therefore does not provide
# stub functions, as other entities would not typically make
# direct function calls into this application.
if (ENABLE_UNIT_TESTS)
  add_subdirectory(unit-test)
endif (ENABLE_UNIT_TESTS)
